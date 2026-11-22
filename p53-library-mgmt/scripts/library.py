"""A research library as a runnable store: ingest, folder taxonomy, duplicates,
version siblings, retrieval and a handover inventory.

The organising brief names the ways file management breaks: files are moved with
no list, hash or log; same-named files overwrite each other until the version
chain snaps; metadata is guessed from filenames; a duplicate is quietly merged
or a preprint and its published version are treated as one. This store is built
against those failures:

  版本不串味     re-ingesting a doc_id with changed content never overwrites: the
                previous entry stays untouched and the new content becomes
                doc_id@v2, with supersedes / superseded_by links recorded both
                ways; two files with the same folded title but different
                content are version siblings and both stay
  重复不静默合并 identical content under two doc_ids is reported as a duplicate
                set and both copies are kept; the store never drops or merges a
                copy silently, and it never merges two files because their
                titles match
  清单可交接     the export is library.json (machine view: content, sha256,
                folders, versions) plus inventory.md (human handover view),
                where declared-but-missing metadata fields are marked as
                missing — recorded, never invented

Folder assignment comes from the declared structure rules (cue match, first
rule wins, matched cues recorded); a document no rule matches lands in 未归类
and is counted, and a declared folder no document lands in is named
(lib.folder_empty) so a dead cue cannot hide. Metadata is stored verbatim and
carries its provenance: every present field is marked meta_src (where it came
from — a declared record field), declared-but-absent fields are listed as
missing, never guessed. The export is library.json + inventory.md plus
manifest.tsv (one line per document: doc_id, folder, full 64-hex sha256, byte
length, title) — the archive manifest a hand-over can be verified against;
verify_store() recomputes every hash and reports any mismatch. Retrieval ranks
documents against a query by shared content terms (CJK bigrams + latin words)
and returns an honest empty list when nothing matches. No wall-clock fields are
written, so the same batch re-runs byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = "library/v1"
UNFILED = "未归类"

_STOP = {"the", "and", "for", "with", "this", "that", "from", "are", "was",
         "他们的", "我们", "因此", "但是", "然后"}


def _refusal(rule: str, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
            "refusal": {"rule": rule, "message": message},
            "limits": ["nothing was ingested into the library"]}


def key_terms(text: str, min_len: int = 2) -> list:
    """Content terms of a text, for retrieval. CJK bigrams + latin words."""
    s = str(text or "")
    latin = re.findall(r"[A-Za-z][A-Za-z0-9_-]{%d,}" % (min_len - 1), s)
    cjk = re.findall(r"[\u4e00-\u9fff]{%d,}" % max(min_len, 2), s)
    grams: set = set(latin)
    for run in cjk:
        n = max(min_len, 2)
        grams.update(run[i:i + n] for i in range(len(run) - n + 1))
    return sorted(g for g in grams if g.lower() not in _STOP)


def text_sha(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def safe_doc_id(doc_id: str) -> bool:
    """A doc_id must not carry folder semantics: path separators would corrupt
    the folder taxonomy, "." / ".." would corrupt sorted listings."""
    s = str(doc_id or "")
    return bool(s) and s not in (".", "..") and "/" not in s and "\\" not in s


def verify_store(path) -> dict:
    """Re-read a written library.json and recompute every hash: the archive
    self-check a hand-over can run without trusting the writer."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return {"ok": False, "checked": 0, "mismatched": [],
                "reason": "library.json is not readable: " + str(exc)}
    docs = data.get("documents")
    if not isinstance(docs, dict):
        return {"ok": False, "checked": 0, "mismatched": [],
                "reason": "library.json has no documents map"}
    mismatched = []
    checked = 0
    for doc_id, doc in sorted(docs.items()):
        if not isinstance(doc, dict) or not isinstance(doc.get("text"), str):
            mismatched.append(str(doc_id))
            continue
        checked += 1
        if text_sha(doc["text"]) != doc.get("sha256"):
            mismatched.append(str(doc_id))
    return {"ok": not mismatched, "checked": checked, "mismatched": mismatched,
            "reason": "" if not mismatched else
                      "sha256 recompute does not match the stored hash for: "
                      + ", ".join(mismatched)}


def norm_title(title: str) -> str:
    """Fold a title for version-sibling comparison: case, whitespace, hyphens
    and underscores are folded; letters and digits are kept (a v2 is not a v1,
    and 2023 is not 2024)."""
    t = str(title or "").strip().lower()
    t = t.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    t = re.sub(r"[\s_\-]+", "", t)
    return t


def valid_structure(structure):
    """Split the declared folder taxonomy into usable rules and named skips."""
    ok: list = []
    skipped: list = []
    if not isinstance(structure, list):
        return ok, [{"index": 0,
                     "reason": "structure is not a list; the folder taxonomy is skipped"}]
    for i, rule in enumerate(structure):
        if not isinstance(rule, dict) or not str(rule.get("folder") or "").strip():
            skipped.append({"index": i,
                            "reason": "structure entry is not an object with a folder name"})
            continue
        ok.append({"folder": str(rule["folder"]).strip(),
                   "cues": [str(c).strip() for c in (rule.get("cues") or [])
                            if str(c).strip()]})
    return ok, skipped


class Library:
    """The persisted store: documents keyed by doc_id, an event log, no silent
    writes. Adapted from the reading-annotate workspace: content + sha256 per
    entry, and re-ingest is a version, never an overwrite."""

    def __init__(self):
        self.data = {"version": 1, "documents": {}, "events": []}

    def add(self, doc_id: str, text: str, title=None, meta=None) -> dict:
        sha = text_sha(text)
        # Metadata provenance: every present field is marked with where it came
        # from — a declared record field ("record"). Fields are never extracted
        # from filenames here, so "record" is the only honest source marking.
        meta_src = {str(k): "record" for k in (meta or {})}
        docs = self.data["documents"]
        if doc_id in docs:
            if docs[doc_id]["sha256"] == sha:
                self.data["events"].append({"kind": "reingest", "doc_id": doc_id,
                                            "result": "unchanged"})
                return {"status": "unchanged", "doc_id": doc_id}
            # Same id, different content: the old entry is immutable. The new
            # content becomes the next version and both links are recorded —
            # this is the overwrite that breaks version chains, refused.
            n = 2
            new_id = doc_id + "@v" + str(n)
            while new_id in docs:
                n += 1
                new_id = doc_id + "@v" + str(n)
            docs[new_id] = {"doc_id": new_id, "title": str(title or "").strip(),
                            "sha256": sha, "text": str(text or ""),
                            "bytes": len(str(text or "").encode("utf-8")),
                            "meta": dict(meta or {}), "meta_src": meta_src,
                            "terms": key_terms(str(title or "") + " " + str(text or ""))[:80],
                            "supersedes": doc_id}
            docs[doc_id]["superseded_by"] = new_id
            self.data["events"].append({"kind": "version", "doc_id": new_id,
                                        "supersedes": doc_id})
            return {"status": "versioned", "doc_id": new_id, "supersedes": doc_id}
        docs[doc_id] = {"doc_id": doc_id, "title": str(title or "").strip(),
                        "sha256": sha, "text": str(text or ""),
                        "bytes": len(str(text or "").encode("utf-8")),
                        "meta": dict(meta or {}), "meta_src": meta_src,
                        "terms": key_terms(str(title or "") + " " + str(text or ""))[:80]}
        self.data["events"].append({"kind": "ingest", "doc_id": doc_id})
        return {"status": "stored", "doc_id": doc_id}

    def documents(self) -> list:
        return [self.data["documents"][k] for k in sorted(self.data["documents"])]

    def assign_folders(self, structure) -> dict:
        """First matching structure rule wins; the matched cues are recorded on
        the document, so the filing is explainable. No rule matched → 未归类."""
        for doc in self.data["documents"].values():
            low = (doc["title"] + "\n" + doc["text"]).lower()
            folder, cues = UNFILED, []
            for rule in structure:
                matched = [c for c in rule["cues"] if c.lower() in low]
                if matched:
                    folder, cues = rule["folder"], matched
                    break
            doc["folder"] = folder
            doc["folder_cues"] = cues
        return {f: [d["doc_id"] for d in self.documents() if d["folder"] == f]
                for f in sorted({d["folder"] for d in self.data["documents"].values()})}

    def duplicates(self) -> list:
        """Identical content under two or more doc_ids: reported, both kept."""
        by_sha: dict = {}
        for doc in self.data["documents"].values():
            by_sha.setdefault(doc["sha256"], []).append(doc["doc_id"])
        return [{"sha256": sha[:16], "doc_ids": sorted(ids),
                 "note": "identical content; every copy is kept, never merged silently"}
                for sha, ids in sorted(by_sha.items()) if len(ids) > 1]

    def siblings(self) -> list:
        """Same folded title, different content: version siblings, both kept.

        A preprint and its published version are two records. The store does not
        guess which one is authoritative — it lists every variant with its hash.
        """
        by_title: dict = {}
        for doc in self.data["documents"].values():
            key = norm_title(doc["title"])
            if key:
                by_title.setdefault(key, {}).setdefault(doc["sha256"], []).append(doc["doc_id"])
        out = []
        for key in sorted(by_title):
            variants = by_title[key]
            if len(variants) < 2:
                continue
            out.append({"title_key": key,
                        "members": [{"doc_ids": sorted(v), "sha256": sha[:16]}
                                    for sha, v in sorted(variants.items())],
                        "note": "same title, different content: version siblings kept "
                                "separate; the store does not guess which is authoritative"})
        return out

    def retrieve(self, query: str, top: int = 8) -> list:
        """Rank documents against a query by shared content terms; honest misses."""
        q_terms = set(key_terms(query))
        if not q_terms:
            return []
        scored = []
        for doc in self.documents():
            shared = sorted(q_terms & set(doc.get("terms") or []))
            if shared:
                scored.append({"doc_id": doc["doc_id"], "title": doc["title"],
                               "folder": doc.get("folder"), "score": len(shared),
                               "shared": shared[:6], "sha256": doc["sha256"][:16]})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top]

    def export(self, out_dir, report=None) -> dict:
        """library.json (machine) + inventory.md (human handover view) +
        manifest.tsv (the archive manifest: full 64-hex sha256 per document)."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        lib_path = out_dir / "library.json"
        lib_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        inv_path = out_dir / "inventory.md"
        inv_path.write_text(render_inventory_md(self, report or {}),
                            encoding="utf-8")
        # Archive manifest: doc_id, folder, FULL 64-hex sha256, byte length,
        # title — tab separated, one line per document, no wall-clock fields.
        man_lines = ["doc_id\tfolder\tsha256\tbytes\ttitle"]
        for d in self.documents():
            man_lines.append("\t".join([
                d["doc_id"], d.get("folder") or UNFILED, d["sha256"],
                str(d.get("bytes") or 0), (d.get("title") or "").replace("\t", " ")]))
        man_path = out_dir / "manifest.tsv"
        man_path.write_text("\n".join(man_lines) + "\n", encoding="utf-8")
        return {"ok": True, "wrote": [str(lib_path), str(inv_path), str(man_path)],
                "documents": len(self.data["documents"])}


def render_inventory_md(lib: Library, report: dict) -> str:
    """The human view: folders, hashes, metadata (with declared-missing marks),
    version links, duplicates, refusals — re-checkable against library.json."""
    docs = lib.documents()
    folders: dict = {}
    for d in docs:
        folders.setdefault(d.get("folder") or UNFILED, []).append(d)
    lines = ["# 科研资料库清单（handover inventory）", ""]
    lines.append("documents: " + str(len(docs))
                 + " · duplicate sets: " + str(len(report.get("duplicates") or []))
                 + " · version sibling sets: " + str(len(report.get("siblings") or []))
                 + " · refused records: " + str(len(report.get("refused") or []))
                 + " · spec_sha256 " + str(report.get("spec_sha256", "-")))
    lines.append("")
    for folder in sorted(folders):
        lines.append("## " + folder + "（" + str(len(folders[folder])) + " documents）")
        lines.append("")
        for d in folders[folder]:
            head = "- **" + d["doc_id"] + "**"
            if d["title"]:
                head += " — " + d["title"]
            lines.append(head)
            paras = len([p for p in d["text"].splitlines() if p.strip()])
            lines.append("  sha256 " + d["sha256"][:16] + " · paragraphs " + str(paras))
            meta = d.get("meta") or {}
            if meta:
                src = d.get("meta_src") or {}
                lines.append("  meta: " + "; ".join(
                    k + "=" + str(v) + "（出处: " + str(src.get(k, "record")) + "）"
                    for k, v in meta.items()))
            missing = (report.get("meta_missing") or {}).get(d["doc_id"])
            if missing:
                lines.append("  meta missing (declared, absent — recorded, not guessed): "
                             + ", ".join(missing))
            if d.get("supersedes"):
                lines.append("  supersedes " + d["supersedes"]
                             + "（版本链，旧版保留）")
            if d.get("superseded_by"):
                lines.append("  superseded by " + d["superseded_by"])
            if d.get("folder_cues"):
                lines.append("  filed via cue: " + ", ".join(d["folder_cues"][:4]))
        lines.append("")
    dups = report.get("duplicates") or []
    if dups:
        lines.append("## duplicate content（同内容多份，逐份保留，未合并）")
        lines.append("")
        for dup in dups:
            lines.append("- sha " + dup["sha256"] + ": " + ", ".join(dup["doc_ids"]))
        lines.append("")
    sibs = report.get("siblings") or []
    if sibs:
        lines.append("## version siblings（同题不同内容，都保留，不合并）")
        lines.append("")
        for sib in sibs:
            parts = [m["sha256"] + " → " + ", ".join(m["doc_ids"]) for m in sib["members"]]
            lines.append("- " + sib["title_key"] + ": " + " | ".join(parts))
        lines.append("")
    refused = report.get("refused") or []
    if refused:
        lines.append("## refused records（如实拒绝，不静默跳过）")
        lines.append("")
        for r in refused:
            lines.append("- index " + str(r.get("index")) + " [" + str(r.get("rule", ""))
                         + "]: " + str(r.get("reason", "")))
        lines.append("")
    retr = report.get("retrieval")
    if retr:
        lines.append("## retrieval（query: " + str(retr.get("query", "")) + "）")
        lines.append("")
        for h in retr.get("hits") or []:
            lines.append("- " + h["doc_id"] + " (score " + str(h["score"])
                         + ", shared: " + ", ".join(h["shared"]) + ")")
        if not retr.get("hits"):
            lines.append("- (no document matches — honest empty result)")
        lines.append("")
    lines.append("(示意 inventory 格式 — generated from the store; every line is "
                 "re-checkable against library.json)")
    return "\n".join(lines)


def run(spec, base_dir=None):
    """Ingest every record, assign folders, census duplicates and siblings, and
    answer the optional retrieval query.

    Returns (library, result). The result is a refusal dict (status
    undetermined) when nothing could be ingested at all.
    """
    if not isinstance(spec, dict):
        return None, _refusal("lib.spec_unreadable", "the spec is not a JSON object")
    structure, struct_skipped = valid_structure(spec.get("structure"))
    meta_fields = [str(f).strip() for f in (spec.get("meta_fields") or [])
                   if str(f).strip()]
    rec_raw = spec.get("records")
    if not isinstance(rec_raw, list) or not rec_raw:
        return None, _refusal("lib.no_records",
                              "spec.records is missing, empty or not a list; nothing can "
                              "be ingested")

    lib = Library()
    refused = []
    findings = []
    counts = {"stored": 0, "unchanged": 0, "versioned": 0}
    if struct_skipped:
        findings.append({"rule": "lib.structure_skipped", "severity": "low",
                         "count": len(struct_skipped), "entries": struct_skipped,
                         "why": "these structure entries could not be used; the rest ran"})

    for i, rec in enumerate(rec_raw):
        if not isinstance(rec, dict):
            refused.append({"index": i, "rule": "lib.record_skipped",
                            "reason": "record entry is not an object: "
                                      + type(rec).__name__})
            continue
        doc_id = str(rec.get("id") or "").strip() or "doc-" + str(i + 1).zfill(3)
        if not safe_doc_id(doc_id):
            refused.append({"index": i, "rule": "lib.id_invalid", "doc_id": doc_id,
                            "reason": "doc_id carries folder semantics (path "
                                      "separator or '.'/'..'); refused as unsafe — "
                                      "the folder taxonomy must stay exact"})
            continue
        title = str(rec.get("title") or "").strip()
        meta = rec.get("meta")
        if meta is not None and not isinstance(meta, dict):
            findings.append({"rule": "lib.meta_invalid", "severity": "low",
                             "index": i, "doc_id": doc_id,
                             "why": "meta is not an object; stored as empty, never guessed"})
            meta = {}
        text = None
        if rec.get("text") is not None:
            text = str(rec["text"])
        elif rec.get("path"):
            p = Path(str(rec["path"]))
            if not p.is_absolute() and base_dir:
                p = Path(base_dir) / p
            if not p.exists():
                refused.append({"index": i, "rule": "lib.file_missing", "doc_id": doc_id,
                                "path": str(rec["path"]),
                                "reason": "file not found: " + str(rec["path"])
                                          + "; named here, never silently skipped"})
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                refused.append({"index": i, "rule": "lib.file_unreadable",
                                "doc_id": doc_id, "path": str(rec["path"]),
                                "reason": "file could not be read as UTF-8 text: "
                                          + str(exc)})
                continue
        else:
            refused.append({"index": i, "rule": "lib.record_skipped", "doc_id": doc_id,
                            "reason": "record has neither text nor path; nothing to ingest"})
            continue
        res = lib.add(doc_id, text, title, meta)
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if res["status"] == "versioned":
            findings.append({"rule": "lib.version_created", "severity": "medium",
                             "doc_id": res["doc_id"], "supersedes": res["supersedes"],
                             "why": "the same doc_id was re-ingested with different content; "
                                    "the old entry is kept and the new content becomes the "
                                    "next version — never overwritten"})

    if not lib.data["documents"]:
        reasons = "; ".join(str(r.get("reason", "")) for r in refused[:5])
        return None, _refusal("lib.no_records",
                              "no record could be ingested (" + reasons + ")")

    folders = lib.assign_folders(structure)
    dups = lib.duplicates()
    sibs = lib.siblings()
    unfiled_n = sum(1 for d in lib.documents() if d["folder"] == UNFILED)
    # A declared folder that received zero documents is named: either its cues
    # never match the batch or the taxonomy is surplus — either way it must not
    # hide behind a tree that looks filled.
    empty_folders = [f["folder"] for f in structure
                     if len(folders.get(f["folder"]) or []) == 0]
    if empty_folders:
        findings.append({"rule": "lib.folder_empty", "severity": "low",
                         "count": len(empty_folders), "folders": empty_folders,
                         "why": "these declared folders received no document; the "
                                "cues never matched this batch — fix the rule or "
                                "drop the folder, never guess documents into it"})
    for dup in dups:
        findings.append({"rule": "lib.duplicate_content", "severity": "low",
                         "sha256": dup["sha256"], "doc_ids": dup["doc_ids"],
                         "why": "identical content under several doc_ids; every copy kept "
                                "and reported here, never merged silently"})
    for sib in sibs:
        findings.append({"rule": "lib.version_sibling", "severity": "medium",
                         "title_key": sib["title_key"], "members": sib["members"],
                         "why": "same title, different content: version siblings kept "
                                "separate — a preprint and its published version are two "
                                "records, not one"})
    if unfiled_n:
        findings.append({"rule": "lib.unfiled", "severity": "low", "count": unfiled_n,
                         "why": "these documents matched no declared structure rule; they "
                                "sit in " + UNFILED + " instead of a guessed folder"})

    retrieval = None
    query = spec.get("query")
    if query:
        hits = lib.retrieve(str(query))
        retrieval = {"query": str(query), "hits": hits, "empty": not hits,
                     "note": "" if hits else
                     "no document shares a content term with the query; honest empty result"}

    meta_missing: dict = {}
    if meta_fields:
        for d in lib.documents():
            absent = [f for f in meta_fields
                      if not str((d.get("meta") or {}).get(f, "")).strip()]
            if absent:
                meta_missing[d["doc_id"]] = absent

    result = {
        "schema_version": SCHEMA_VERSION,
        # Spec-carried values pass through: a case_id declared on the spec
        # itself is honoured in the result (a case file can also supply it via
        # the CLI --case passthrough, which keeps this value when present).
        "case_id": spec.get("case_id")
        if isinstance(spec.get("case_id"), (str, int)) else None,
        # Honest status: ok = every record ingested; partial = the batch was
        # stored but some records were refused (limits listed); a run that
        # could not ingest anything returns the refusal dict instead.
        "status": "ok" if not refused else "partial",
        "counts": {"documents": len(lib.data["documents"]), **counts,
                   "refused": len(refused)},
        "refused": refused,
        "findings": findings,
        "folders": folders,
        "documents": [{"doc_id": d["doc_id"], "title": d["title"],
                       "folder": d["folder"], "folder_cues": d.get("folder_cues") or [],
                       "sha256": d["sha256"][:16], "bytes": d.get("bytes") or 0,
                       "meta": d.get("meta") or {},
                       "meta_src": d.get("meta_src") or {},
                       "supersedes": d.get("supersedes"),
                       "superseded_by": d.get("superseded_by")}
                      for d in lib.documents()],
        "duplicates": dups,
        "siblings": sibs,
        "retrieval": retrieval,
        "meta_missing": meta_missing,
        "spec_sha256": hashlib.sha256(json.dumps(
            {"records": rec_raw, "structure": spec.get("structure")}, sort_keys=True,
            ensure_ascii=False).encode("utf-8")).hexdigest()[:16],
    }
    return lib, result
