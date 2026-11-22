"""Nomenclature audit for biological mechanism diagrams.

The layout audit in `schematic.py` answers "is this drawn correctly". This module
answers a different question: "is each label a well-formed biological entity, and
is the figure consistent about it".

The failures it targets are the ones that make a mechanism figure wrong while
looking polished:

- a human gene written in mouse casing (``Tp53`` where the paper means human
  ``TP53``), or the reverse
- a gene symbol set in roman when convention requires italic, so a reader cannot
  tell the gene from its protein
- two nodes that are aliases of the same gene, drawn as two separate entities, so
  a two-step pathway is invented out of one actor
- an entity with no accession, so nobody can tell which of several genes called
  ``PCNA`` is meant

Conventions are checkable from the text. Whether a symbol names a real gene needs
a database this module does not ship, and it does not pretend otherwise: an
unrecognised symbol is not an error.
"""

from __future__ import annotations

import re

# Casing conventions. Human symbols are upper case (TP53, BRCA1); rodent symbols
# are title case (Tp53, Brca1). A figure that is explicit about its species can be
# checked strictly; without a declared species, only mixed conventions are flagged.
CASE_RULES = {
    "human": re.compile(r"^[A-Z][A-Z0-9]*(?:[-.][A-Z0-9]+)*$"),
    "mouse": re.compile(r"^[A-Z][a-z0-9]*(?:[-.][a-z0-9]+)*$"),
    "rat": re.compile(r"^[A-Z][a-z0-9]*(?:[-.][a-z0-9]+)*$"),
    "zebrafish": re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$"),
    "yeast": re.compile(r"^[A-Z][A-Z0-9]*$"),
}

# Words that name a process, not an actor. Drawing them as a node turns a verb
# into an entity and makes the figure claim something the source did not.
VAGUE_ENTITIES = {
    "signaling", "signalling", "pathway", "cascade", "mechanism", "response",
    "regulation", "activation", "inhibition", "process", "network", "system",
    "通路", "信号", "级联", "机制", "调控", "激活", "抑制", "过程", "网络",
}

ACCESSIONS = {
    "hgnc": re.compile(r"^HGNC:\d+$"),
    "uniprot": re.compile(r"^[A-NR-Z][0-9][A-Z0-9]{3}[0-9]$|^[OPQ][0-9][A-Z0-9]{3}[0-9]$"),
    "ensembl": re.compile(r"^ENS[A-Z]*[GTP]\d{6,}$"),
    "ncbi_gene": re.compile(r"^\d+$"),
    "chebi": re.compile(r"^CHEBI:\d+$"),
}


def looks_like_gene_symbol(text: str) -> bool:
    """A short token containing at least one letter, no spaces.

    Deliberately loose: this decides whether casing is worth checking, not
    whether the symbol is real.
    """
    t = text.strip()
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9\-.]{0,15}", t)) and any(c.isalpha() for c in t)


def check_casing(symbol: str, species: str | None) -> dict:
    """Return a violation when the symbol's casing contradicts the species."""
    if not species:
        return {"ok": True}
    rule = CASE_RULES.get(species.lower())
    if rule is None:
        return {"ok": True, "note": f"no casing convention known for '{species}'"}
    if rule.match(symbol):
        return {"ok": True}
    return {"ok": False, "expected": species.lower(), "pattern": rule.pattern,
            "message": f"'{symbol}' does not follow the {species} symbol casing convention"}


def audit_nomenclature(spec: dict, svg_path) -> dict:
    """Check entity labels, styling, aliases and accessions."""
    from pathlib import Path

    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    species = spec.get("species")
    aliases = spec.get("aliases") or {}          # canonical -> [alias, ...]
    nodes = spec.get("nodes") or []

    # --- 1. styling actually present in the exported SVG ------------------
    # Reading the SVG rather than the spec is what makes this an audit: a
    # renderer that silently drops italics passes on the spec and fails here.
    svg = Path(svg_path).read_text(encoding="utf-8", errors="replace")
    text_els = re.findall(r"<text\b([^>]*)>(.*?)</text>", svg, flags=re.S)
    styled: dict[str, bool] = {}
    for attrs, content in text_els:
        plain = re.sub(r"<[^>]+>", "", content).strip()
        italic = ("font-style:italic" in attrs.replace(" ", "")
                  or 'font-style="italic"' in attrs
                  or 'font-style: italic' in attrs)
        styled[plain] = italic

    # --- 2. per-entity checks ---------------------------------------------
    for n in nodes:
        label = n.get("label") or n.get("id", "")
        kind = (n.get("kind") or "").lower()

        if label.strip().lower() in VAGUE_ENTITIES:
            add("nomenclature.vague_entity", "low",
                "label names a process rather than an actor; a process drawn as a node "
                "claims an entity the source may not have", node=n["id"], label=label)

        if kind == "gene" and looks_like_gene_symbol(label):
            v = check_casing(label, species)
            if not v["ok"]:
                add("nomenclature.gene_casing", "high", v["message"],
                    node=n["id"], label=label, species=species)
            drawn_italic = styled.get(label.strip())
            if drawn_italic is False:
                add("nomenclature.gene_not_italic", "medium",
                    "a gene symbol is set in roman; convention requires italic so the gene "
                    "can be told from its protein", node=n["id"], label=label)
        elif kind == "protein":
            if styled.get(label.strip()) is True:
                add("nomenclature.protein_italic", "medium",
                    "a protein name is set in italic; convention sets protein names in roman",
                    node=n["id"], label=label)

        if kind in ("gene", "protein") and not n.get("accession"):
            add("nomenclature.missing_accession", "medium",
                "entity carries no accession, so it cannot be resolved to one specific record",
                node=n["id"], label=label)

    # --- 3. accessions must be well-formed when present --------------------
    for n in nodes:
        acc = n.get("accession")
        if not acc:
            continue
        src = (n.get("accession_source") or "").lower()
        pat = ACCESSIONS.get(src)
        if pat and not pat.match(str(acc)):
            add("nomenclature.accession_malformed", "medium",
                f"accession '{acc}' does not match the {src} format", node=n["id"])

    # --- 4. alias collisions ----------------------------------------------
    canonical_of: dict[str, str] = {}
    for canon, alist in aliases.items():
        canonical_of[canon.strip().lower()] = canon
        for a in alist:
            canonical_of[str(a).strip().lower()] = canon
    seen: dict[str, str] = {}
    for n in nodes:
        label = (n.get("label") or "").strip().lower()
        canon = canonical_of.get(label)
        if not canon:
            continue
        if canon in seen and seen[canon] != n["id"]:
            add("nomenclature.alias_collision", "high",
                "two nodes are the same entity under different names, so the figure shows "
                "a two-step relationship that may be one actor", canonical=canon,
                nodes=[seen[canon], n["id"]])
        else:
            seen[canon] = n["id"]

    # --- 5. mixed species conventions without a declared species ----------
    if not species:
        styles = set()
        for n in nodes:
            label = n.get("label") or ""
            if (n.get("kind") or "").lower() != "gene" or not looks_like_gene_symbol(label):
                continue
            if CASE_RULES["human"].match(label):
                styles.add("human")
            elif CASE_RULES["mouse"].match(label) and label != label.upper():
                styles.add("mouse")
        if len(styles) > 1:
            add("nomenclature.species_ambiguous", "medium",
                "the figure mixes human and rodent gene-casing conventions but declares no "
                "species, so a reader cannot tell which organism each symbol refers to",
                detected=sorted(styles))

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "nomenclature/v1",
        "species": species,
        "fonts_checked": len(text_els),
        "findings": findings,
        "severity_counts": counts,
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
    }
