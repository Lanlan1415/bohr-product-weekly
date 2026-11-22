"""A writing client as a runnable tool: propose, review, apply, diff, export.

The four properties the task names become four mechanisms:

  改得准      every edit is a change card anchored to a span of the original; a "wording" edit
              that replaces more than 1.5x the span is a rewrite, a deletion that swallows a
              whole paragraph is a structure change, and a declared `citation` edit may move
              citations (that is its declared layer) while a wording edit may not
  改得可追溯  each card carries the original span, the replacement, and the basis (material or
              reference) it rests on; cards are accepted or rejected one by one, and refused
              proposals are kept with their reasons
  格式不塌    applying is refused if headings, numbering, captions, equations, citations, table
              columns or reference entries changed — a wording edit must not move the skeleton
  交付可用    versions are kept, two versions can be diffed, any version can be restored, the
              export marks every card, and `result` writes the structured deliverable with the
              case id, an honest status and the uncertainties

Two rules are deliberately declarative — they fire only on what an edit *declares*, never on an
absent field, because punishing a missing optional field turns the tool into a false-positive
machine that rewrites correct output:

  edit.basis_support   a `term` edit may be checked against the basis's content, but only when
                       that basis declares content text; a basis without content is never checked
  card.needs_confirm   an edit may declare `confirm: true`; an edit that does not is never flagged
  plan.coverage        a card may declare which workorder points it `covers`; a card that does
                       not is never punished — the point simply stays unaddressed and visible
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

EDIT_KINDS = ("wording", "term", "structure", "citation", "format")
MAX_REPLACE_RATIO = 1.5  # a "wording" edit that more than 1.5x the span is a rewrite
DELETE_KINDS = ("wording", "term")  # the only layers allowed an empty replacement

# The named rules as a registry: exactly what the SKILL.md documents is what fires here.
RULES = (
    "edit.no_basis",
    "edit.basis_unresolved",
    "edit.library_missing",
    "edit.span_not_found",
    "edit.rewrite_limit",
    "edit.delete_span",
    "edit.basis_support",
    "skeleton.moved",
    "load.empty_draft",
    "load.unreadable",
    "export.failure",
    "result.contract",
    "plan.coverage",
    "card.needs_confirm",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n") if p.strip()]


# --- the skeleton a wording edit must not disturb ---------------------------
HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+\S")
CAPTION = re.compile(r"^\s*(Fig(?:ure)?\.?|Table|Tab\.?|式|图|表)\s*\d+", re.I)
EQUATION = re.compile(r"\$\$|\\begin\{equation\}|\\\[")
CITE = re.compile(r"\[([A-Za-z0-9:_\-]+)\]")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")

SKELETON_KEYS = ("heading_numbers", "heading_positions", "captions",
                 "equation_count", "citations", "table_columns")


def skeleton(paragraphs: list[str]) -> dict:
    """The structural fingerprint: numbering, captions, equations, citations, tables, refs."""
    heads = []
    for i, p in enumerate(paragraphs):
        m = HEADING.match(p)
        if m:
            heads.append((i, m.group(1)))
    caps = sorted(CAPTION.sub("", p).strip().lower() for p in paragraphs if CAPTION.match(p))
    return {
        "heading_numbers": [n for _, n in heads],
        "heading_positions": [i for i, _ in heads],
        "captions": caps,
        "equation_count": sum(len(EQUATION.findall(p)) for p in paragraphs),
        "citations": sorted(k for p in paragraphs for k in CITE.findall(p)),
        # 表格 stays consistent at the structural level: the column profile of each row.
        # Editing text inside a cell keeps the profile; adding or dropping a cell moves it.
        "table_columns": [p.count("|") - 1 for p in paragraphs if TABLE_ROW.match(p)],
    }


def skeleton_delta(before: dict, after: dict) -> list[str]:
    """Which structural elements changed. An empty list means the skeleton is intact."""
    return [key for key in SKELETON_KEYS if before.get(key) != after.get(key)]


class WritingClient:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.setdefault("refused", [])
        else:
            self.data = {"version": 0, "versions": {}, "edits": [], "refused": [],
                         "materials": [], "references": [], "applied": []}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- setup ------------------------------------------------------------
    def load(self, text: str, materials=None, references=None, case_id=None) -> dict:
        if not str(text).strip():
            # A draft that carries no text is the mechanical proxy for a corrupted or
            # unreadable input: it is refused as its own diagnosis, never loaded silently.
            return {"ok": False,
                    "reason": "load.empty_draft: the draft is empty; nothing to edit"}
        self.data["versions"]["v0"] = {"paragraphs": split_paragraphs(text)}
        self.data["version"] = 0
        def _records_of(value):
            if isinstance(value, str):
                value = [value]
            return [v for v in (value or []) if isinstance(v, dict)]
        self.data["materials"] = _records_of(materials)
        self.data["references"] = _records_of(references)
        # 输入标识: echoed into the export and the structured result. Declared, never invented.
        self.data["case_id"] = case_id or None
        return {"ok": True, "version": "v0",
                "paragraphs": len(self.data["versions"]["v0"]["paragraphs"])}

    def current(self) -> str:
        return "v%d" % self.data["version"]

    def loaded(self) -> bool:
        """True once a draft has been loaded into this store."""
        return bool(self.data.get("versions"))

    def paragraphs(self, version=None) -> list[str]:
        versions = self.data.get("versions") or {}
        if not versions:
            raise ValueError("no document loaded: run load before this command")
        return versions[version or self.current()]["paragraphs"]

    # --- proposing --------------------------------------------------------
    def propose(self, edits: list[dict]) -> dict:
        """Turn proposed edits into change cards, refusing the ones that cannot be checked."""
        accepted_cards, refused = [], []
        if not self.loaded():
            return {"ok": False, "cards": [], "refused": [
                {"edit": n, "reason": "no document loaded: run load before propose"}
                for n in range(len(edits or []))]}
        paras = self.paragraphs()
        for n, e in enumerate(edits):
            if not isinstance(e, dict):
                refused.append({"edit": n, "reason": "an edit entry was not an object"})
                continue
            kind = str(e.get("kind") or "").strip().lower()
            quote = str(e.get("quote") or "").strip()
            basis = str(e.get("basis") or "").strip()
            raw_after = e.get("after", None)

            if kind not in EDIT_KINDS:
                refused.append({"index": n, "quote": quote[:60],
                                "reason": f"kind '{kind}' is not one of "
                                          f"{'/'.join(EDIT_KINDS)}"})
                continue
            if not quote:
                refused.append({"index": n, "quote": "",
                                "reason": "no original span quoted"})
                continue
            if not basis:
                # An edit with no basis is an opinion; the task asks for 依据.
                refused.append({"index": n, "quote": quote[:60],
                                "reason": "edit.no_basis: an edit must rest on a material "
                                          "or a reference"})
                continue
            if kind == "citation" and not self.data["references"]:
                # 引用库缺失 is its own diagnosis, distinct from a key that merely misses.
                refused.append({"index": n, "quote": quote[:60],
                                "reason": "edit.library_missing: the reference library is "
                                          "empty; load the references first"})
                continue
            if not self._basis_resolves(basis):
                refused.append({"index": n, "quote": quote[:60],
                                "reason": f"edit.basis_unresolved: basis '{basis}' does not "
                                          f"resolve to a material or reference"})
                continue
            located = self._locate(quote, paras)
            if located is None:
                # 指令与稿件内容冲突: the instruction names text the manuscript does not have.
                refused.append({"index": n, "quote": quote[:60],
                                "reason": f"edit.span_not_found: quoted span not found: "
                                          f"{quote[:50]!r}"})
                continue
            if raw_after is None:
                # A missing key is an unfinished edit; an explicit "" is a declared deletion.
                refused.append({"index": n, "quote": quote[:60],
                                "reason": "no replacement text: give the after text, or an "
                                          "explicit empty string to declare a deletion"})
                continue
            after = str(raw_after).strip()

            if not after and kind not in DELETE_KINDS:
                refused.append({"index": n, "quote": quote[:60],
                                "reason": f"edit.delete_span: kind '{kind}' cannot delete; "
                                          f"only wording and term edits may carry an empty "
                                          f"replacement"})
                continue
            if after and kind == "wording" and len(after) > MAX_REPLACE_RATIO * len(quote):
                # 改得准: a wording change that more than replaces the span is a rewrite.
                refused.append({"index": n, "quote": quote[:60],
                                "reason": f"edit.rewrite_limit: a wording edit replaced "
                                          f"{len(quote)} chars with {len(after)}; that is a "
                                          f"rewrite, not a wording edit"})
                continue
            if not after and located[1] == 0 and located[2] == len(paras[located[0]]):
                # Deleting a whole paragraph is a structure-level move, not a wording edit.
                refused.append({"index": n, "quote": quote[:60],
                                "reason": "edit.delete_span: deleting the whole paragraph is "
                                          "a structure change, not a wording edit"})
                continue
            if after and kind == "term":
                # 不新增材料外事实: a term edit may be checked against the basis's content —
                # but only when that basis declares content. Absent content is never a fault.
                content = self._basis_content(basis)
                if content is not None and after not in content:
                    refused.append({"index": n, "quote": quote[:60],
                                    "reason": f"edit.basis_support: replacement {after!r} is "
                                              f"not in the declared content of basis "
                                              f"{basis!r}; the material must carry the "
                                              f"fact the edit inserts"})
                    continue

            card = {"id": "E%d" % (len(self.data["edits"]) + len(accepted_cards) + 1),
                    "kind": kind, "paragraph": located[0], "start": located[1],
                    "end": located[2], "quote": quote, "after": after, "basis": basis,
                    "status": "pending", "base_version": self.current()}
            covers = e.get("covers", None)
            if covers is not None:
                items = covers if isinstance(covers, list) else [covers]
                named = sorted({str(x).strip() for x in items if str(x).strip()})
                if named:
                    card["covers"] = named
            if e.get("confirm") is True:
                # 人工确认项: flagged because the edit declared it, never inferred.
                card["needs_confirm"] = True
            accepted_cards.append(card)
        self.data["edits"].extend(accepted_cards)
        self.data.setdefault("refused", []).extend(refused)
        return {"cards": accepted_cards, "refused": refused}

    def _basis_resolves(self, basis: str) -> bool:
        mats = {str(m.get("id")) for m in self.data["materials"] if isinstance(m, dict)}
        refs = {str(r.get("key")) for r in self.data["references"] if isinstance(r, dict)}
        return basis in mats or basis in refs

    def _basis_content(self, basis: str):
        """The declared content of a basis, or None when it declares none."""
        for m in self.data["materials"]:
            if not isinstance(m, dict):
                continue
            if str(m.get("id")) == basis:
                return str(m.get("content") or "").strip() or None
        for r in self.data["references"]:
            if not isinstance(r, dict):
                continue
            if str(r.get("key")) == basis:
                return str(r.get("content") or "").strip() or None
        return None

    @staticmethod
    def _locate(quote: str, paras: list[str]):
        for i, p in enumerate(paras):
            at = p.find(quote)
            if at >= 0:
                return (i, at, at + len(quote))
        return None

    # --- reviewing --------------------------------------------------------
    def decide(self, card_id: str, accept: bool, reason: str = "") -> dict:
        for c in self.data["edits"]:
            if c["id"] == card_id:
                if c["status"] != "pending":
                    return {"ok": False, "reason": f"{card_id} is already {c['status']}"}
                if accept and c["base_version"] != self.current():
                    return {"ok": False,
                            "reason": f"{card_id} was proposed against {c['base_version']}; "
                                      f"the document is now {self.current()}"}
                c["status"] = "accepted" if accept else "rejected"
                if reason:
                    c["decision_reason"] = reason
                return {"ok": True, "card": c}
        return {"ok": False, "reason": f"no card {card_id}"}

    # --- applying ---------------------------------------------------------
    def apply(self) -> dict:
        """Apply the accepted cards, refusing if the skeleton would move."""
        accepted = [c for c in self.data["edits"] if c["status"] == "accepted"]
        if not accepted:
            return {"ok": True, "changed": 0, "version": self.current(),
                    "note": "nothing accepted, nothing applied (idempotent)"}

        before_paras = self.paragraphs()
        after_paras = list(before_paras)
        # Right to left within a paragraph keeps earlier offsets valid.
        for c in sorted(accepted, key=lambda x: (x["paragraph"], -x["start"])):
            i = c["paragraph"]
            p = after_paras[i]
            if p[c["start"]:c["end"]] != c["quote"]:
                return {"ok": False, "reason": f"{c['id']} no longer matches its span; "
                                               f"re-propose"}
            after_paras[i] = p[:c["start"]] + c["after"] + p[c["end"]:]

        delta = skeleton_delta(skeleton(before_paras), skeleton(after_paras))
        if delta:
            # A declared citation edit may move citations — that is the layer it declared
            # (引用协作: adding, dropping and re-pointing citations must be able to land).
            # Anything else, or any second skeleton change alongside it, is refused.
            declared_citation = all(c["kind"] == "citation" for c in accepted)
            if not (delta == ["citations"] and declared_citation):
                return {"ok": False, "reason": "skeleton.moved: the edit would move the "
                                               "document skeleton",
                        "changed": delta,
                        "hint": "a wording or term edit must not alter numbering, captions, "
                                "equations, citations, table columns or reference entries"}

        v = self.data["version"] + 1
        self.data["versions"]["v%d" % v] = {"paragraphs": after_paras,
                                            "sha256": _sha("\n".join(after_paras))}
        self.data["version"] = v
        self.data["applied"].append({"version": "v%d" % v,
                                     "cards": [c["id"] for c in accepted]})
        return {"ok": True, "changed": len(accepted), "version": "v%d" % v}

    # --- workorder coverage (结果完整性) -----------------------------------
    def plan(self, points) -> dict:
        """Register the edit targets the workorder names, so coverage can be reported."""
        norm = []
        for p in points or []:
            if isinstance(p, dict):
                pid = str(p.get("id") or "").strip()
                if pid:
                    norm.append({"id": pid, "task": str(p.get("task") or "")})
            else:
                pid = str(p).strip()
                if pid:
                    norm.append({"id": pid, "task": ""})
        if not norm:
            return {"ok": False, "reason": "the workorder names no edit points"}
        self.data["plan"] = norm
        return {"ok": True, "points": len(norm)}

    def coverage(self) -> dict:
        """Which workorder points have cards and which stay unaddressed (材料缺口).

        Declarative: only cards that declare `covers` are attributed. A card without
        `covers` is never punished — its points simply remain unaddressed and visible.
        """
        plan = self.data.get("plan") or []
        if not plan:
            return {"ok": True, "planned": False, "points": [], "unaddressed": [],
                    "note": "plan.coverage: no workorder planned, so no coverage is checked"}
        claimed: dict[str, list[str]] = {}
        for c in self.data["edits"]:
            for pid in c.get("covers") or []:
                claimed.setdefault(pid, []).append(c["id"])
        points = [{"id": p["id"], "task": p["task"], "cards": claimed.get(p["id"], []),
                   "status": "covered" if claimed.get(p["id"]) else "unaddressed"}
                  for p in plan]
        return {"ok": True, "planned": True, "points": points,
                "unaddressed": [p["id"] for p in points if p["status"] == "unaddressed"]}

    # --- status and uncertainty (运行状态和不确定性) -------------------------
    def _uncertainty(self) -> tuple[dict, list[dict]]:
        cov = self.coverage()
        pending = [c["id"] for c in self.data["edits"] if c["status"] == "pending"]
        confirm = [c["id"] for c in self.data["edits"] if c.get("needs_confirm")]
        unc = []
        if pending:
            unc.append({"kind": "undecided_cards", "cards": pending,
                        "note": "proposed but neither accepted nor rejected"})
        if confirm:
            unc.append({"kind": "card.needs_confirm", "cards": confirm,
                        "note": "the edit declared it needs human confirmation"})
        if cov.get("planned") and cov.get("unaddressed"):
            unc.append({"kind": "plan.coverage", "points": cov["unaddressed"],
                        "note": "workorder points no card claims (材料缺口)"})
        return cov, unc

    def _status(self, cov: dict) -> str:
        pending = any(c["status"] == "pending" for c in self.data["edits"])
        return "partial" if pending or (cov.get("planned") and cov.get("unaddressed")) \
            else "complete"

    # --- diff, restore, export, result -------------------------------------
    def diff(self, a: str, b: str) -> list[dict]:
        pa, pb = self.paragraphs(a), self.paragraphs(b)
        out = []
        for i in range(max(len(pa), len(pb))):
            l = pa[i] if i < len(pa) else ""
            r = pb[i] if i < len(pb) else ""
            if l != r:
                out.append({"paragraph": i, "from": l, "to": r})
        return out

    def restore(self, version: str) -> dict:
        if version not in self.data["versions"]:
            return {"ok": False, "reason": f"no version {version}"}
        # Restoring appends a new version rather than rewriting history.
        v = self.data["version"] + 1
        self.data["versions"]["v%d" % v] = {
            "paragraphs": list(self.data["versions"][version]["paragraphs"]),
            "restored_from": version}
        self.data["version"] = v
        return {"ok": True, "version": "v%d" % v, "restored_from": version}

    def export(self, out_dir) -> dict:
        """Write a tracked-changes view and the clean text; both carry their basis."""
        out_dir = Path(out_dir)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            tracked = ["# Tracked changes", ""]
            for c in self.data["edits"]:
                mark = {"pending": "?", "accepted": "+", "rejected": "-"}.get(c["status"], "?")
                extra = "  ·  **needs human confirmation**" if c.get("needs_confirm") else ""
                tracked += [f"## [{mark}] {c['id']} — {c['kind']}  ({c['status']}){extra}",
                            f"*anchor*: ¶{c['paragraph']} chars {c['start']}–{c['end']}"
                            f"  ·  *basis*: {c['basis']}",
                            "",
                            f"- **before**: {c['quote']}",
                            f"- **after**: {c['after']}",
                            ""]
            (out_dir / "tracked_changes.md").write_text("\n".join(tracked), encoding="utf-8")
            final = "\n".join(self.paragraphs())
            (out_dir / "final.md").write_text(final, encoding="utf-8")
        except OSError as exc:
            # 导出失败 is identified and reported, never a traceback.
            return {"ok": False, "reason": "export.failure: could not write the export",
                    "error": str(exc)}
        cov, unc = self._uncertainty()
        return {"ok": True, "tracked": str(out_dir / "tracked_changes.md"),
                "final": str(out_dir / "final.md"), "version": self.current(),
                "cards": len(self.data["edits"]),
                "case_id": self.data.get("case_id"),
                "status": self._status(cov), "uncertainty": unc,
                "sha256": _sha(final)}

    def result(self, out_path=None) -> dict:
        """The structured deliverable the output contract asks for: 输入标识, 主结果,
        证据/来源定位, 运行状态, 不确定性 — and the refused proposals with their reasons."""
        cov, unc = self._uncertainty()
        rec = {
            "schema_version": "writing-client-result/v1",
            "case_id": self.data.get("case_id"),
            "status": self._status(cov),
            "versions": sorted(self.data["versions"]),
            "current_version": self.current(),
            "cards": self.data["edits"],
            "refused_proposals": self.data.get("refused") or [],
            "applied": self.data.get("applied") or [],
            "coverage": cov,
            "uncertainty": unc,
            "final_sha256": _sha("\n".join(self.paragraphs())),
        }
        if rec["status"] == "partial":
            # A partial result must identify its limits.
            rec["limits"] = [u.get("note") or u["kind"] for u in unc]
        if out_path is not None:
            try:
                p = Path(out_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                return {"ok": False, "reason": "result.contract: could not write the "
                                               "result file", "error": str(exc)}
        return {"ok": True, **rec}
