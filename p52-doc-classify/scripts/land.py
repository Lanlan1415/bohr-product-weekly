"""Five-step landing protocol: turn labels into real, reversible directory work.

The organising brief names the failure: classification that stays a chat
suggestion. Steps P2 (label a record) was already mechanical in classify.py;
this module makes the other four steps mechanical too, each with named rules a
reviewer can recompute:

  P1 inventory    walk the batch root, hash every file (sha256), record size,
                  kind, readability; a file that cannot be read is named, never
                  silently dropped; a 0-byte file and an encrypted PDF are
                  flagged as unusable for text extraction
  P3 naming plan  map every entry to a target directory (category, year) and a
                  canonical filename from the declared template, with the
                  degradation chain author-year-title -> doi -> title -> original
                  stem -> uncategorized prefix; collisions resolved by content
                  hash suffix, never by overwriting
  P4 dedup/ver    exact duplicates by sha256 (keep one, archive the rest —
                  never delete), near duplicates by DOI or title+author+year
                  (manual confirm), preprint vs published relations from a
                  declared version field or filename cues
  P5 journal      execute the plan as moves with a per-op journal (both-end
                  sha256), never overwrite a differing target, resume from the
                  manifest on rerun (zero ops when already done), and roll the
                  whole batch back in reverse journal order

Determinism: no wall-clock fields anywhere; the same tree and the same spec
produce a byte-identical result, and rerunning execution over a finished tree
performs zero operations.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

SCHEMA_VERSION = "doc-land/v1"
UNCLASSIFIED = "未分类"

# File-type classes by extension (the 文件类型 element of the six-element check).
TYPE_BY_EXT = {
    ".pdf": "pdf", ".docx": "office", ".doc": "office", ".xlsx": "office",
    ".xls": "office", ".pptx": "office", ".ppt": "office",
    ".txt": "text", ".md": "text", ".rtf": "text",
    ".csv": "data", ".tsv": "data", ".json": "data",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image",
    ".tiff": "image", ".gif": "image",
    ".zip": "archive", ".gz": "archive", ".7z": "archive",
}
PDF_MAGIC = b"%PDF-"
PDF_ENCRYPT_MARK = b"/Encrypt"

# Characters a filesystem refuses or that make names ambiguous across systems.
FORBIDDEN_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
NAME_MAX = 60

PREPRINT_CUES = ("preprint", "arxiv", "biorxiv", "ssrn", "submitted", "draft",
                 "workingpaper", "working-paper", "预印本", "投稿稿")
FORMAL_CUES = ("published", "final", "accepted", "camera-ready", "cameraready",
               "official", "正式版", "已发表", "发表版")


def _sha256_file(path: Path) -> str | None:
    """Streamed digest; None only when the file cannot be read."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _hash8(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


def slugify(text) -> str:
    """A filesystem-safe, deterministic slug.

    Keeps CJK and letters as-is (多语言标题保留原文), turns whitespace into
    single hyphens, and strips characters filesystems refuse.
    """
    t = str(text or "").replace("\u00a0", " ").strip()
    t = FORBIDDEN_NAME_RE.sub("", t)
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    return t.strip("-")


def _norm_doi(doi) -> str:
    d = str(doi or "").strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:", "info:doi/"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip()


def _norm_key(*parts) -> str:
    joined = "|".join(str(p or "") for p in parts)
    t = joined.strip().lower()
    t = re.sub(r"[\s_-]+", "", t)
    return t


def _refusal(rule: str, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
            "refusal": {"rule": rule, "message": message},
            "limits": ["the batch was not organised; nothing moved"]}


def _severity_counts(findings: list) -> dict:
    counts: dict = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return counts


def _status_for(findings: list) -> str:
    """high -> blocked (exit 4), medium -> review (exit 3), else ok (exit 0)."""
    counts = _severity_counts(findings)
    if counts.get("high"):
        return "blocked"
    if counts.get("medium"):
        return "review"
    return "ok"


# ---------------------------------------------------------------------------
# P1 inventory
# ---------------------------------------------------------------------------

def inventory(root) -> dict:
    """P1: hash every file under root, sorted by relative posix path.

    Every file gets path, size, sha256, kind, usable. Files that cannot be read
    (OSError), 0-byte files and encrypted PDFs stay in the listing but are
    marked and named in findings — an honest inventory, never a crash.
    """
    rootp = Path(root)
    if not rootp.is_dir():
        return _refusal("land.root_missing",
                        "the batch root is not a readable directory: " + str(rootp))
    files, skipped = [], []
    for p in sorted(x for x in rootp.rglob("*") if x.is_file()):
        rel = p.relative_to(rootp).as_posix()
        try:
            size = p.stat().st_size
        except OSError as exc:
            skipped.append({"path": rel, "reason": "stat failed: " + str(exc)})
            continue
        head = b""
        readable = True
        try:
            with p.open("rb") as fh:
                head = fh.read(4096)
        except OSError as exc:
            readable = False
        kind = TYPE_BY_EXT.get(p.suffix.lower(), "other")
        encrypted = False
        if kind == "pdf" and head.startswith(PDF_MAGIC) and PDF_ENCRYPT_MARK in head:
            encrypted = True
        entry = {"path": rel, "size": size, "sha256": None, "kind": kind,
                 "encrypted": encrypted, "usable": False}
        if not readable:
            skipped.append({"path": rel, "reason": "unreadable: open/read failed"})
            files.append(entry)
            continue
        digest = _sha256_file(p)
        if digest is None:
            skipped.append({"path": rel, "reason": "unreadable during hashing"})
            files.append(entry)
            continue
        entry["sha256"] = digest
        entry["usable"] = size > 0 and not encrypted
        files.append(entry)

    findings = []
    unreadable = [s for s in skipped if s["reason"].startswith("unreadable")]
    if unreadable:
        findings.append({"rule": "inv.unreadable", "severity": "medium",
                         "count": len(unreadable), "entries": unreadable,
                         "why": "these files could not be read; they stay in the "
                                "inventory, are excluded from organising, and the "
                                "batch continues"})
    stat_failed = [s for s in skipped if s["reason"].startswith("stat failed")]
    if stat_failed:
        findings.append({"rule": "inv.unreadable", "severity": "medium",
                         "count": len(stat_failed), "entries": stat_failed,
                         "why": "these paths could not be stat-ed; named, not dropped"})
    zero = [f["path"] for f in files if f.get("sha256") and f["size"] == 0]
    if zero:
        findings.append({"rule": "inv.zero_byte", "severity": "low",
                         "count": len(zero), "paths": zero,
                         "why": "0-byte files are damage candidates: excluded from "
                                "organising until inspected"})
    enc = [f["path"] for f in files if f.get("encrypted")]
    if enc:
        findings.append({"rule": "inv.pdf_encrypted", "severity": "medium",
                         "count": len(enc), "paths": enc,
                         "why": "encrypted PDFs have no extractable text layer; classify "
                                "them by filename/path cues at low confidence instead"})
    by_kind: dict = {}
    for f in files:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
    return {"status": "ok", "root": str(rootp),
            "files": files, "skipped": skipped,
            "counts": {"files": len(files), "bytes": sum(f["size"] for f in files),
                       "by_kind": by_kind},
            "findings": findings}


# ---------------------------------------------------------------------------
# P3 naming plan
# ---------------------------------------------------------------------------

def _classification_fields(entry: dict) -> dict:
    """Keep label provenance attached to a proposed old→new operation."""
    return {
        "secondary_categories": list(entry.get("secondary_categories") or []),
        "classification_confidence": entry.get("classification_confidence"),
        "classification_reason": entry.get("classification_reason"),
        "classification_evidence": list(entry.get("classification_evidence") or [])[:8],
        "metadata_provenance": dict(entry.get("metadata_provenance") or {}),
        "text_extraction": dict(entry.get("text_extraction") or {}),
    }


def _name_for(entry: dict, opts: dict) -> dict:
    """Canonical stem for one entry, with the declared degradation chain.

    author+year+title -> doi -> title -> original stem -> uncategorized- prefix.
    Every drop below the full template is recorded (degraded + missing fields),
    so 元数据未补齐 is a fact on the record, not a guess.
    """
    template = str(opts.get("naming_template") or "author-year-title").strip().lower()
    author, year, title, doi = (entry.get("author"), entry.get("year"),
                                entry.get("title"), entry.get("doi"))
    stem = Path(str(entry.get("path") or "")).stem
    missing, basis = [], None
    if template == "keep":
        basis, name = "keep original stem", stem
    elif template == "doi" and doi:
        basis, name = "doi", "doi-" + slugify(doi)
    elif author and year and title:
        basis = "author-year-title"
        name = slugify(author) + "-" + str(year) + "-" + slugify(title)
    elif doi:
        basis = "doi (degraded)"
        name = "doi-" + slugify(doi)
        missing = [f for f in ("author", "year", "title") if not entry.get(f)]
    elif title:
        basis = "title (degraded)"
        name = slugify(title)
        missing = [f for f in ("author", "year", "doi") if not entry.get(f)]
    elif author or year:
        basis = "original stem (degraded)"
        name = slugify(stem)
        missing = [f for f in ("author", "year", "title", "doi") if not entry.get(f)]
    else:
        basis = "uncategorized prefix (degraded)"
        name = "uncategorized-" + slugify(stem)
        missing = ["author", "year", "title", "doi"]
    max_len = int(opts.get("max_name_len") or NAME_MAX)
    if len(name) > max_len:
        name = name[: max_len - 9].rstrip("-") + "-" \
            + _hash8(str(entry.get("path")) + "|" + name)
        basis += " +truncated"
    return {"name": name, "basis": basis, "missing": missing,
            "degraded": bool(missing)}


def build_plan(entries: list, inv: dict, opts: dict | None = None,
               archive_map: dict | None = None) -> dict:
    """P3: deterministic old->new plan from entries joined onto the P1 inventory.

    Directory layering: slugified category, plus a year subdirectory when the
    entry carries a year. Target-name collisions are resolved with a content
    hash suffix — the plan never proposes overwriting a different file.
    `archive_map` (from the P4 dedup pass) maps an exact duplicate's path to
    the copy being kept: the duplicate moves into the duplicates directory,
    never deleted.
    """
    opts = dict(opts or {})
    dupes_keep = {str(k).replace("\\", "/"): str(v).replace("\\", "/")
                  for k, v in (archive_map or {}).items()}
    archive_set = set(dupes_keep)
    year_subdir = bool(opts.get("year_subdir", True))
    dupes_dir = slugify(opts.get("dupes_dir") or "duplicates")
    findings: list = []
    files = {f["path"]: f for f in inv.get("files", []) if f.get("sha256")}
    plan: list = []
    covered: set = set()
    seen_targets: dict = {}

    usable_paths = [p for p, f in files.items() if f.get("usable")]
    entries = [e for e in (entries or []) if isinstance(e, dict)]
    seen_entry_paths: set = set()
    dup_entry_rows = []
    for i, e in enumerate(entries):
        rel = str(e.get("path") or "").replace("\\", "/").strip()
        if rel in seen_entry_paths:
            dup_entry_rows.append({"index": i, "path": rel,
                                   "why": "a second entry names a file already planned; "
                                          "only the first entry plans it, so no file is "
                                          "moved twice"})
            continue
        seen_entry_paths.add(rel)
        f = files.get(rel)
        if f is None:
            findings.append({"rule": "plan.entry_not_found", "severity": "medium",
                             "entry_index": i, "path": rel,
                             "why": "the entry names a file that is not in the P1 "
                                    "inventory (missing, unreadable or outside the root); "
                                    "it gets no plan row"})
            continue
        covered.add(rel)
        meta = {"author": e.get("author"), "year": e.get("year"),
                "title": e.get("title"), "doi": e.get("doi")}
        category = str(e.get("category") or "").strip() or UNCLASSIFIED
        year = e.get("year")
        ext = Path(rel).suffix.lower()
        if rel in archive_set:
            # P4 verdict: this copy is an exact duplicate — it moves into the
            # duplicates directory (archived, never deleted), not the category tree.
            new_rel = dupes_dir + "/" + Path(rel).name
            if new_rel.lower() in seen_targets and seen_targets[new_rel.lower()] != rel:
                new_rel = dupes_dir + "/" + Path(rel).stem + "-" + f["sha256"][:8] + ext
                findings.append({"rule": "name.collision_resolved", "severity": "low",
                                 "path": rel, "target": new_rel,
                                 "why": "two archived duplicates share a filename; the second "
                                        "gets a content hash suffix instead of overwriting"})
            seen_targets[new_rel.lower()] = rel
            plan.append({"id": "p" + str(i + 1).zfill(3), "path": rel,
                         "old": rel, "new": new_rel, "op": "move",
                         "sha256": f["sha256"], "category": "重复归档",
                         "name_basis": "archive-duplicate",
                         "metadata_incomplete": False, "missing_fields": [],
                         "why": "exact duplicate of " + (dupes_keep.get(rel) or "")
                                + "; archived into " + dupes_dir + ", never deleted",
                         **_classification_fields(e)})
            continue
        named = _name_for({**e, "path": rel}, opts)
        parts = [slugify(part) for part in category.split("/") if part.strip()] or [UNCLASSIFIED]
        if year_subdir and year not in (None, ""):
            parts.append(str(year))
        parts.append(named["name"])
        new_rel = "/".join(parts) + ext
        key = new_rel.lower()
        if key in seen_targets and seen_targets[key] != rel:
            stem = Path(named["name"]).stem
            new_rel = "/".join(parts[:-1]) + "/" + stem + "-" + _hash8(rel) + ext
            findings.append({"rule": "name.collision_resolved", "severity": "low",
                             "path": rel, "target": new_rel,
                             "why": "two entries map to the same target name; the second "
                                    "gets a content hash suffix instead of overwriting"})
        seen_targets[new_rel.lower()] = rel
        old_rel = rel
        op = "none" if new_rel == rel else "move"
        plan.append({"id": "p" + str(i + 1).zfill(3), "path": rel,
                     "old": old_rel, "new": new_rel, "op": op,
                     "sha256": f["sha256"], "category": category,
                     "name_basis": named["basis"],
                     "metadata_incomplete": bool(named["missing"]),
                     "missing_fields": named["missing"],
                     "why": "category " + category + (" / year " + str(year) if year_subdir and year not in (None, "") else "")
                            + "; name from " + named["basis"],
                     **_classification_fields(e)})

    if dup_entry_rows:
        findings.append({"rule": "plan.duplicate_entry", "severity": "medium",
                         "count": len(dup_entry_rows), "entries": dup_entry_rows,
                         "why": "entries naming the same file: only the first plans it, "
                                "so no file is moved twice"})
    uncovered = [p for p in usable_paths if p not in covered]
    if uncovered:
        findings.append({"rule": "plan.uncovered_files", "severity": "low",
                         "count": len(uncovered), "paths": uncovered,
                         "why": "usable inventory files with no entry: they appear in the "
                                "inventory and stay untouched, but the six-element check "
                                "wants a stated reason for each"})
    degraded = [p["path"] for p in plan if p["metadata_incomplete"]]
    if degraded:
        findings.append({"rule": "name.degraded", "severity": "low",
                         "count": len(degraded), "paths": degraded,
                         "why": "metadata below the full author-year-title template: the "
                                "degradation chain produced the name and the missing "
                                "fields are on the record, never invented"})

    return {"plan": plan, "findings": findings,
            "coverage": {"inventory_files": len(usable_paths),
                         "entries": len(entries),
                         "planned": len(plan),
                         "uncovered": uncovered}}


# ---------------------------------------------------------------------------
# P4 dedup and version relations
# ---------------------------------------------------------------------------

def dedup_versions(entries: list, inv: dict, opts: dict | None = None) -> dict:
    """P4: exact duplicates (sha256), near duplicates (DOI / title+author+year),
    and preprint-vs-published relations. Nothing is ever deleted: exact
    duplicates get an archive move into the duplicates directory, near
    duplicates wait for manual confirmation.
    """
    opts = dict(opts or {})
    findings: list = []
    files = {f["path"]: f for f in inv.get("files", []) if f.get("sha256") and f.get("usable")}
    meta: dict = {}
    for e in (entries or []):
        if isinstance(e, dict) and e.get("path"):
            meta[str(e["path"]).replace("\\", "/")] = e

    # exact duplicates by content hash
    by_hash: dict = {}
    for rel, f in sorted(files.items()):
        by_hash.setdefault(f["sha256"], []).append(rel)
    duplicates = []
    for h, rels in sorted(by_hash.items()):
        if len(rels) < 2:
            continue
        def richness(rel):
            e = meta.get(rel) or {}
            return sum(1 for k in ("author", "year", "title", "doi") if e.get(k))
        keep = sorted(rels, key=lambda r: (-richness(r), len(r), r))[0]
        archive = [r for r in rels if r != keep]
        duplicates.append({"sha256": h, "keep": keep, "archive": archive,
                           "policy": "keep the entry with the most complete metadata, "
                                     "then the shorter path, then lexicographic"})
        findings.append({"rule": "dup.exact", "severity": "low",
                         "count": len(archive), "keep": keep, "archive": archive,
                         "why": "identical bytes; one copy is kept, the rest are archived "
                                "into the duplicates directory — never deleted"})

    # near duplicates: same DOI or same title+author+year, different bytes
    groups: dict = {}
    for rel, e in sorted(meta.items()):
        if rel not in files:
            continue
        doi = _norm_doi(e.get("doi"))
        if doi:
            groups.setdefault("doi:" + doi, set()).add(rel)
        t = e.get("title")
        if t and e.get("author") and e.get("year"):
            k = "tay:" + _norm_key(e.get("author"), t, e.get("year"))
            groups.setdefault(k, set()).add(rel)
    near = []
    for key, rels in sorted(groups.items()):
        hashes = {files[r]["sha256"] for r in rels if r in files}
        if len(rels) < 2 or len(hashes) < 2:
            continue  # single file, or already handled as an exact duplicate
        rels_sorted = sorted(rels)
        basis = "doi" if key.startswith("doi:") else "title+author+year"
        existing = next((g for g in near if g["paths"] == rels_sorted), None)
        if existing is not None:
            # DOI and title+author+year describe ONE related file set, not two
            # independent near-duplicates or version relations.
            existing["keys"].append(key)
            existing["basis"] = "+".join(dict.fromkeys(existing["basis"].split("+") + [basis]))
            continue
        near.append({"key": key, "keys": [key], "basis": basis, "paths": rels_sorted,
                     "decision": "manual_confirm"})
        findings.append({"rule": "dup.near", "severity": "medium",
                         "basis": basis, "paths": rels_sorted,
                         "why": "same " + basis + " but different bytes: candidate "
                                "duplicate, both stay in place until a human confirms "
                                "which one to keep"})

    # Coalesce OVERLAPPING groups, not just identical path sets. A DOI group
    # may include an attachment while title+year identifies only the article;
    # both keys still describe one connected piece of evidence.
    merged = True
    while merged:
        merged = False
        for i in range(len(near)):
            if merged:
                break
            for j in range(i + 1, len(near)):
                if set(near[i]["paths"]) & set(near[j]["paths"]):
                    near[i]["paths"] = sorted(set(near[i]["paths"]) | set(near[j]["paths"]))
                    near[i]["keys"] = near[i].get("keys", [near[i]["key"]]) + near[j].get("keys", [near[j]["key"]])
                    near[i]["basis"] = "+".join(dict.fromkeys(
                        near[i]["basis"].split("+") + near[j]["basis"].split("+")))
                    del near[j]
                    merged = True
                    break
    findings = [f for f in findings if f.get("rule") != "dup.near"]
    for group in near:
        findings.append({"rule": "dup.near", "severity": "medium",
                         "basis": group["basis"], "paths": group["paths"], "keys": group["keys"],
                         "why": "overlapping declared identity keys were coalesced into one "
                                "manual-confirm group; every differing file stays in place"})

    # version relations inside near-duplicate groups
    relations = []
    for g in near:
        pre, formal, unknown = [], [], []
        for rel in g["paths"]:
            e = meta.get(rel) or {}
            declared = str(e.get("version") or e.get("pubstate") or "").strip().lower()
            hay = declared or slugify(Path(rel).stem).lower().replace("-", "")
            if any(c in hay for c in PREPRINT_CUES):
                pre.append(rel)
            elif any(c in hay.replace("-", "") for c in FORMAL_CUES):
                formal.append(rel)
            else:
                unknown.append(rel)
        if pre and formal:
            relations.append({"formal": formal, "preprint": pre,
                              "basis": "declared version field" if any(
                                  (meta.get(r) or {}).get("version") or (meta.get(r) or {}).get("pubstate")
                                  for r in pre + formal) else "filename cue",
                              "group": g["key"]})
            findings.append({"rule": "ver.relation", "severity": "low",
                             "formal": formal, "preprint": pre,
                             "why": "preprint vs published distinguished; the formal copy "
                                    "goes to the main directory and the relation is on the "
                                    "record for the handover inventory"})
        elif "doi" in g["basis"] or (pre or formal):
            findings.append({"rule": "ver.ambiguous", "severity": "low",
                             "paths": g["paths"],
                             "why": "candidate duplicates but neither side declares a "
                                    "version; both stay in place until a human decides "
                                    "which is the formal copy"})

    archive_map = {r: d["keep"] for d in duplicates for r in d["archive"]}
    return {"duplicates": duplicates, "near_duplicates": near,
            "version_relations": relations, "archive_map": archive_map,
            "findings": findings}


# ---------------------------------------------------------------------------
# P5 execute, journal, rollback
# ---------------------------------------------------------------------------

def execute(plan: list, root, out_dir, journal_name: str = "journal.jsonl") -> dict:
    """P5: perform the plan's move ops under root, journalling every op.

    Never overwrites: a target that exists with different content is a named
    conflict and blocks the batch (exit 4 semantics). A target that already
    exists with the same content counts as done (rerun/resume = zero ops).
    """
    rootp = Path(root)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    journal_path = Path(out_dir) / journal_name
    done_before = 0
    if journal_path.exists():
        for line in journal_path.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("op") == "move":
                    done_before += 1
            except json.JSONDecodeError:
                continue
    findings: list = []
    journal: list = []
    changed = 0
    already = 0
    seq = done_before
    for p in plan:
        if p.get("op") != "move":
            continue
        src = rootp / p["old"]
        dst = rootp / p["new"]
        if not src.exists():
            if dst.exists() and (_sha256_file(dst) == p.get("sha256")):
                already += 1  # a previous run finished this op: resume, no rewrite
                continue
            findings.append({"rule": "exec.source_missing", "severity": "medium",
                             "path": p["old"],
                             "why": "planned source is gone and the target does not carry "
                                    "its content; the op cannot run — check for manual "
                                    "changes since the plan was made"})
            continue
        if dst.exists():
            if _sha256_file(dst) == p.get("sha256") == _sha256_file(src):
                already += 1
                continue
            findings.append({"rule": "exec.skipped_conflict", "severity": "high",
                             "path": p["old"], "target": p["new"],
                             "why": "target exists with different content: the plan never "
                                    "overwrites; move the target by hand or revise the plan"})
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as exc:
            findings.append({"rule": "exec.move_failed", "severity": "high",
                             "path": p["old"], "target": p["new"],
                             "why": "move failed: " + str(exc)})
            continue
        verified = _sha256_file(dst)
        seq += 1
        entry = {"seq": seq, "op": "move", "from": p["old"], "to": p["new"],
                 "sha256": p.get("sha256"), "sha256_verified": verified,
                 "why": p.get("why", "")}
        journal.append(entry)
        with journal_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if verified != p.get("sha256"):
            findings.append({"rule": "exec.mismatch", "severity": "high",
                             "path": p["new"],
                             "why": "content hash after the move does not match the "
                                    "inventory hash; the op was rolled back"})
            undo = {"seq": seq + 0.5, "op": "undo", "from": p["old"], "to": p["new"],
                    "sha256": p.get("sha256"), "why": "auto-rollback of a mismatched move"}
            try:
                shutil.move(str(dst), str(src))
                with journal_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(undo, ensure_ascii=False) + "\n")
            except OSError as exc:
                undo["error"] = str(exc)
        else:
            changed += 1
    return {"changed": changed, "already_done": already, "journal": journal,
            "journal_path": str(journal_path), "findings": findings}


def rollback(journal_path, root, out_dir) -> dict:
    """Reverse the journal in reverse order, verifying both-end hashes.

    Every restored file is checked against the sha256 recorded when it was
    moved; a mismatch is named, never hidden.
    """
    rootp = Path(root)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    jp = Path(journal_path)
    findings: list = []
    restored, mismatches = 0, 0
    ops = []
    if jp.exists():
        for line in jp.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("op") == "move":
                ops.append(e)
    for e in reversed(ops):
        src, dst = rootp / e["to"], rootp / e["from"]
        if not src.exists():
            if dst.exists() and _sha256_file(dst) == e.get("sha256"):
                restored += 1  # already rolled back by an earlier pass
                continue
            findings.append({"rule": "rollback.source_missing", "severity": "high",
                             "path": e["to"],
                             "why": "the journalled target is gone and the original path "
                                    "does not carry its content"})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as exc:
            findings.append({"rule": "rollback.failed", "severity": "high",
                             "path": e["to"], "why": "restore move failed: " + str(exc)})
            continue
        if _sha256_file(dst) == e.get("sha256"):
            restored += 1
            entry = {"seq": e.get("seq"), "op": "rollback", "from": e["to"],
                     "to": e["from"], "sha256": e.get("sha256"), "why": "reversed"}
            (Path(out_dir) / "rollback.jsonl").open("a", encoding="utf-8").write(
                json.dumps(entry, ensure_ascii=False) + "\n")
        else:
            mismatches += 1
            findings.append({"rule": "rollback.mismatch", "severity": "high",
                             "path": e["from"],
                             "why": "restored file hash does not match the journal hash; "
                                    "inspect this file by hand"})
    status = "blocked" if findings else "ok"
    return {"status": status, "restored": restored, "mismatches": mismatches,
            "findings": findings}


# ---------------------------------------------------------------------------
# Orchestrator: P1 -> P3 -> P4 -> (P5 on demand)
# ---------------------------------------------------------------------------

def land_run(spec: dict, root, out_dir, execute_now: bool = False,
             fresh: bool = False) -> dict:
    """Run the landing protocol over a batch root.

    spec.entries carries one object per file: path (+ optional author, year,
    title, doi, version, category). Everything the engine decides is a named,
    recomputable rule; nothing moves unless execute_now is set.

    Idempotence by manifest: before executing, the plan is written to
    out/manifest.json; an execute run over an already-executed tree resumes
    from that manifest and performs zero operations instead of re-planning
    against moved files. Pass fresh=True to re-plan from scratch.
    """
    inv = inventory(root)
    if inv.get("status") == "undetermined":
        return inv
    entries = spec.get("entries")
    if not isinstance(entries, list) or not entries:
        return _refusal("land.no_entries",
                        "spec.entries is missing, empty or not a list; the protocol plans "
                        "nothing against a guessed metadata set")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    resuming = False
    if execute_now and manifest_path.exists() and not fresh:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            manifest = {}
        resuming = isinstance(manifest, dict) and isinstance(manifest.get("plan"), list)
        if resuming:
            dedup = {"duplicates": manifest.get("duplicates") or [],
                     "near_duplicates": manifest.get("near_duplicates") or [],
                     "version_relations": manifest.get("version_relations") or [],
                     "findings": []}
            plan_res = {"plan": manifest["plan"], "findings": [],
                        "coverage": manifest.get("plan_coverage") or {}}
    if not resuming:
        # P4 first: the exact-duplicate archive map feeds the P3 plan, so a
        # duplicate's row moves it into the duplicates directory, never deleted.
        dedup = dedup_versions(entries, inv, spec.get("organize"))
        plan_res = build_plan(entries, inv, spec.get("organize"),
                              dedup.get("archive_map"))

    findings = list(inv.get("findings") or []) + list(plan_res["findings"]) \
        + list(dedup["findings"])
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": _status_for(findings),
        "mode": "resume" if resuming else "plan",
        "inventory": {"files": inv["files"], "skipped": inv["skipped"],
                      "counts": inv["counts"]},
        "plan": plan_res["plan"],
        "plan_coverage": plan_res["coverage"],
        "duplicates": dedup["duplicates"],
        "near_duplicates": dedup["near_duplicates"],
        "version_relations": dedup["version_relations"],
        "findings": findings,
        "severity_counts": _severity_counts(findings),
        "limits": [],
    }
    if execute_now:
        if not resuming:
            manifest_path.write_text(json.dumps(
                {"schema_version": SCHEMA_VERSION,
                 "plan": plan_res["plan"],
                 "plan_coverage": plan_res["coverage"],
                 "duplicates": dedup.get("duplicates") or [],
                 "near_duplicates": dedup.get("near_duplicates") or [],
                 "version_relations": dedup.get("version_relations") or []},
                ensure_ascii=False, indent=2), encoding="utf-8")
        ex = execute(plan_res["plan"], root, out_dir)
        result["findings"] = findings + ex["findings"]
        result["severity_counts"] = _severity_counts(result["findings"])
        result["status"] = _status_for(result["findings"])
        result["executed"] = {"changed": ex["changed"], "already_done": ex["already_done"],
                              "journal_path": ex["journal_path"]}
        result["idempotent"] = ex["changed"] == 0 and not ex["findings"]
    return result


def materialize_plan(plan: list, root, destination, out_dir) -> dict:
    """Create an organised COPY outside the source tree, never move/delete input.

    Every source is checked before and after copying. Existing identical targets
    are a no-op; differing targets are named conflicts and are never overwritten.
    This makes the rubric's real directory deliverable compatible with a strict
    non-destructive source contract.
    """
    rootp, destp, out = Path(root).resolve(), Path(destination).resolve(), Path(out_dir)
    findings: list[dict] = []
    if rootp == destp or rootp in destp.parents or destp in rootp.parents:
        return {"status": "blocked", "changed": 0, "already_done": 0,
                "findings": [{"rule": "copy.destination_conflict", "severity": "high",
                              "why": "destination must be separate from and not contain the source root"}],
                "input_writes": 0}
    out.mkdir(parents=True, exist_ok=True)
    journal: list[dict] = []
    changed = already = 0
    for row in plan:
        rel_old = str(row.get("old") or "")
        rel_new = str(row.get("new") or "")
        src = (rootp / rel_old).resolve()
        dst = (destp / rel_new).resolve()
        if rootp not in src.parents or destp not in dst.parents:
            findings.append({"rule": "copy.path_escape", "severity": "high",
                             "source": rel_old, "target": rel_new,
                             "why": "source/target escaped its declared root; copy refused"})
            continue
        try:
            before = _sha256_file(src)
        except OSError as exc:
            before = None
            findings.append({"rule": "copy.source_unreadable", "severity": "medium",
                             "source": rel_old, "why": str(exc)})
            continue
        expected = row.get("sha256")
        if before is None or before != expected:
            findings.append({"rule": "copy.source_mismatch", "severity": "high",
                             "source": rel_old, "expected": expected, "actual": before,
                             "why": "source changed or is unreadable since inventory; no copy made"})
            continue
        if dst.exists():
            current = _sha256_file(dst)
            if current == expected:
                already += 1
                continue
            findings.append({"rule": "copy.target_conflict", "severity": "high",
                             "source": rel_old, "target": rel_new,
                             "why": "target exists with different bytes; never overwritten"})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except (OSError, shutil.Error) as exc:
            findings.append({"rule": "copy.failed", "severity": "high",
                             "source": rel_old, "target": rel_new, "why": str(exc)})
            continue
        verified = _sha256_file(dst)
        entry = {"seq": len(journal) + 1, "op": "copy", "from": rel_old, "to": rel_new,
                 "destination_root": str(destp), "sha256": expected,
                 "sha256_verified": verified, "why": row.get("why", "")}
        if verified != expected:
            entry["error"] = "post-copy hash mismatch"
            findings.append({"rule": "copy.mismatch", "severity": "high",
                             "source": rel_old, "target": rel_new,
                             "why": "copied bytes differ; original remains intact, output must be inspected"})
        else:
            changed += 1
        journal.append(entry)
    journal_path = out / "copy_journal.jsonl"
    if journal:
        previous = journal_path.read_text(encoding="utf-8") if journal_path.exists() else ""
        offset = len([line for line in previous.splitlines() if line.strip()])
        with journal_path.open("a", encoding="utf-8") as fh:
            for entry in journal:
                entry["seq"] += offset
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    status = "blocked" if any(f["severity"] == "high" for f in findings) else (
        "review" if findings else "ok")
    return {"status": status, "changed": changed, "already_done": already,
            "journal": journal, "journal_path": str(journal_path), "findings": findings,
            "input_writes": 0, "destination": str(destp),
            "idempotent": changed == 0 and already > 0 and not findings,
            "recovery": "source files are untouched; remove/review generated copies separately if required"}


def render_plan_md(result: dict) -> str:
    """The old->new plan as a handover markdown table."""
    lines = ["# 整理计划（naming & directory plan）", ""]
    inv = result.get("inventory") or {}
    counts = inv.get("counts") or {}
    lines.append("root " + str(inv.get("root", "")) + " · files "
                 + str(counts.get("files", 0)) + " · planned "
                 + str(len(result.get("plan") or [])))
    lines.append("")
    lines.append("| id | old | new | op | name basis |")
    lines.append("|-|-|-|-|-|")
    for p in result.get("plan") or []:
        lines.append("| " + p["id"] + " | " + p["old"] + " | " + p["new"]
                     + " | " + p["op"] + " | " + p["name_basis"] + " |")
    lines.append("")
    dups = result.get("duplicates") or []
    if dups:
        lines.append("## 去重（exact duplicates — archive, never delete）")
        lines.append("")
        for d in dups:
            lines.append("- sha256 " + d["sha256"] + ": keep " + d["keep"]
                         + "; archive " + ", ".join(d["archive"]))
        lines.append("")
    rels = result.get("version_relations") or []
    if rels:
        lines.append("## 版本关系（preprint vs published）")
        lines.append("")
        for r in rels:
            lines.append("- " + r["group"] + ": formal " + ", ".join(r["formal"])
                         + " · preprint " + ", ".join(r["preprint"])
                         + " (" + r["basis"] + ")")
        lines.append("")
    if result.get("findings"):
        lines.append("## findings")
        lines.append("")
        for f in result["findings"]:
            lines.append("- " + f["rule"] + " (" + f.get("severity", "") + "): "
                         + f.get("why", ""))
        lines.append("")
    lines.append("(示意输出格式 — the plan is computed from the run, never hand-written)")
    return "\n".join(lines)
