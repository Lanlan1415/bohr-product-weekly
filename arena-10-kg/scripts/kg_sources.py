"""Build a locator/quote registry from the actual two-paper JATS-derived JSON inputs.

The root DOI/title/authors of primary material is never inherited by secondary
material.  Locator records are accepted only from the file or its own document/paragraph
context.  Presence-only checks are explicitly reported as unverified when no source
directory is supplied.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


TEXT_KEYS = ("text", "paragraph_text", "raw_text", "content", "plain_text")
ID_KEYS = ("paragraph_id", "jats_paragraph_id", "pid", "id")
SOURCE_KEYS = ("source_id", "paper_id", "document_id")
FILES = ("primary-material.json", "secondary-material.json", "material.json")


def norm_ws(text):
    return " ".join(str(text or "").split())


def short_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default_source(path):
    if path.name == "primary-material.json":
        return "S1"
    if path.name == "secondary-material.json":
        return "S2"
    return None


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _source_id(node, inherited):
    for key in SOURCE_KEYS:
        if node.get(key) not in (None, ""):
            return str(node[key])
    return inherited


def collect_node(node, inherited, path, passages, register, seen_ids=set()):
    """Context-aware walk; repeated list/dict traversal is bounded by depth and node IDs."""
    if isinstance(node, list):
        for child in node:
            collect_node(child, inherited, path, passages, register)
        return
    if not isinstance(node, dict):
        return
    current = _source_id(node, inherited)
    text = None
    for key in TEXT_KEYS:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            text = value
            break
    paragraph_id = next((str(node[k]) for k in ID_KEYS if node.get(k) not in (None, "")), None)
    if text is not None and paragraph_id and current:
        key = (str(current), paragraph_id)
        if key in passages and passages[key]["text"] != text:
            raise ValueError("locator collision for %s:%s in %s" % (current, paragraph_id, path.name))
        passages[key] = {"source_id": str(current), "paragraph_id": paragraph_id, "text": text,
                         "source_file": str(path)}
        register.setdefault(str(current), {"source_id": str(current), "file": str(path),
                                          "doi": node.get("doi"), "title": node.get("title"),
                                          "authors": node.get("authors"),
                                          "paragraphs": 0})
        register[str(current)]["paragraphs"] = max(register[str(current)]["paragraphs"],
                                                   sum(1 for k in passages if k[0] == str(current)))
        for field in ("sha256", "source_sha256", "content_sha256", "license", "doi", "title", "authors"):
            if node.get(field) not in (None, "") and field in ("license", "doi", "title", "authors"):
                register[str(current)][field] = node[field]
    # Documents/sections in which IDs and text live contribute their own local context.
    # At no point do root DOI/title/authors propagate to a sibling secondary document.
    for value in node.values():
        if isinstance(value, (dict, list)):
            collect_node(value, current, path, passages, register)


def build_registry(directory):
    root = Path(directory)
    passages, register, errors = {}, {}, []
    candidates = [root / f for f in FILES if (root / f).is_file()]
    if not candidates:
        candidates = sorted(root.glob("*material*.json"))
    for path in candidates:
        try:
            obj = _load(path)
            fallback = default_source(path)
            before = len(passages)
            collect_node(obj, fallback, path, passages, register)
            if len(passages) == before:
                errors.append("no source_id/paragraph_id/text records recovered from " + path.name)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(str(path.name) + ": " + str(exc)[:200])
    # The corpus manifest is evidence about each file, not a source to delete/reassign.
    manifest = root / "corpus-manifest.json"
    if manifest.is_file():
        try:
            obj = _load(manifest)
            verify_manifest(obj, root, register)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append("corpus-manifest: " + str(exc)[:200])
    registry = {"passages": passages, "sources": register, "errors": errors,
                "directory": str(root), "verified_directory": True}
    return registry


def verify_manifest(obj, root, register):
    """Verify any explicitly declared hash; absent hashes stay unverified, never invented."""
    records = []
    if isinstance(obj, dict):
        for key in ("documents", "papers", "sources", "materials", "files", "items"):
            if isinstance(obj.get(key), list):
                records = obj[key]
                break
    elif isinstance(obj, list):
        records = obj
    for i, rec in enumerate(records or []):
        if not isinstance(rec, dict):
            continue
        filename = rec.get("file") or rec.get("path") or rec.get("filename")
        if filename:
            path = (root / str(filename)).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError:
                raise ValueError("manifest file escapes input directory")
            if not path.is_file():
                raise ValueError("manifest declares missing file: " + str(filename))
            actual = short_hash(path)
        else:
            actual = None
        expected = rec.get("sha256") or rec.get("source_sha256") or rec.get("hash")
        if expected and actual and str(expected).lower().removeprefix("sha256:") != actual:
            raise ValueError("source hash mismatch for " + str(rec.get("source_id") or filename))
        sid = rec.get("source_id") or rec.get("paper_id")
        if sid is not None:
            sid = str(sid)
            r = register.setdefault(sid, {"source_id": sid, "file": rec.get("file"), "paragraphs": 0})
            for key in ("doi", "title", "authors", "license"):
                if rec.get(key) not in (None, ""):
                    r[key] = rec[key]
            if actual:
                r["sha256"] = actual
                r["hash_verified"] = bool(expected)


def registry_status(registry):
    if not registry:
        return {"verified_against_actual_material": False,
                "note": "No --sources directory; presence check is not quote verification."}
    return {"verified_against_actual_material": bool(registry["passages"]),
            "passages": len(registry["passages"]), "papers": len(registry["sources"]),
            "errors": registry["errors"],
            "sources": [{"source_id": k, "doi": v.get("doi"), "title": v.get("title"),
                         "paragraphs": v.get("paragraphs", 0), "hash_verified": v.get("hash_verified")}
                        for k, v in sorted(registry["sources"].items())]}


def check_evidence(evidence, registry, schema):
    """Check locator presence and, when supplied, exact quote in actual source slice."""
    if not isinstance(evidence, dict):
        return False, "evidence is not an object"
    sid = str(evidence.get("source_id") or "").strip()
    pid = str(evidence.get("paragraph_id") or "").strip()
    quote = str(evidence.get("quote") or "").strip()
    if not sid or not pid or not quote:
        return False, "source_id + paragraph_id + verbatim quote are all required"
    max_chars = int(schema.get("max_quote_chars", 40)) if schema else 160
    if len(quote) > max_chars:
        return False, "quote exceeds %d characters (%d)" % (max_chars, len(quote))
    if registry:
        if registry.get("errors"):
            # Specific source errors do not make independent valid passages impossible.
            # Return those messages only when the requested source itself has not loaded.
            pass
        passage = registry["passages"].get((sid, pid))
        if not passage:
            return False, "locator %s:%s is absent from the actual registered material (no fabricated PDF page fallback)" % (sid, pid)
        actual_text = passage["text"]
        # Exact paragraph content is the primary comparison; whitespace-normalisation only
        # accommodates line wrapping and is explicitly recorded, not fuzzy semantic matching.
        if quote not in actual_text and norm_ws(quote) not in norm_ws(actual_text):
            return False, "quote does not occur at %s:%s" % (sid, pid)
    return True, "verified" if registry else "locator fields present; quote not verified against material"


def query(graph, request):
    """Run a directed graph query; return only actual edges and source slices.

    Unsupported predicates/fields cannot smuggle Python or SQL into the graph.  No reverse
    edge is invented: incoming search merely finds declared edges ending at the entity and
    returns them in their original direction.
    """
    if not isinstance(request, dict):
        return {"status": "undetermined", "reason": "query must be a JSON object"}
    kind = str(request.get("type") or request.get("kind") or "neighbors")
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if kind in {"neighbors", "neighbor", "entity"}:
        entity = str(request.get("node_id") or request.get("id") or "")
        direction = str(request.get("direction") or "outgoing")
        if not any(str(n.get("node_id")) == entity for n in nodes if isinstance(n, dict)):
            return {"status": "undetermined", "reason": "node not present in graph", "query": request}
        if direction not in {"outgoing", "incoming", "both"}:
            return {"status": "undetermined", "reason": "direction must be outgoing/incoming/both", "query": request}
        selected = [e for e in edges if isinstance(e, dict) and (
            (direction in {"outgoing", "both"} and e.get("subject") == entity) or
            (direction in {"incoming", "both"} and e.get("object") == entity))]
    elif kind in {"predicate", "relation", "relationship"}:
        predicate = str(request.get("predicate") or "")
        selected = [e for e in edges if isinstance(e, dict) and e.get("predicate") == predicate]
    elif kind in {"conflicts", "conflict"}:
        selected = [e for e in edges if isinstance(e, dict) and e.get("status") == "conflict"]
    elif kind in {"qualified", "condition"}:
        selected = [e for e in edges if isinstance(e, dict) and e.get("condition")]
    else:
        return {"status": "undetermined", "reason": "unsupported query type; graph-only queries supported"}
    wanted_source = request.get("source_id")
    if wanted_source:
        selected = [e for e in selected if any(str(ev.get("source_id")) == str(wanted_source)
                                              for ev in e.get("evidence") or [] if isinstance(ev, dict))]
    edge_ids = [e.get("edge_id") for e in selected]
    node_ids = sorted({str(x) for e in selected for x in (e.get("subject"), e.get("object"))})
    status = "success" if selected or request.get("empty_is_valid", True) is not False else "undetermined"
    return {"status": status, "query": request, "answer_edge_ids": edge_ids,
            "result_subgraph": {"nodes": node_ids, "edges": edge_ids},
            "edges": selected,
            "uncertain": bool(request.get("note") or not selected),
            "empty_reason": None if selected else "The graph contains no matching directed assertion; outside facts are not inferred."}
