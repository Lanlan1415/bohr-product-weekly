"""Benchmark for the research-dissemination skill.

One scenario per rule plus repaired-twin guards, aligned to the scoring points
this task states:

  facts/data/units preserved        -> invariant_broken, invariant_added
  figure references preserved       -> xref_lost
  no unsupported new conclusions    -> absolute_without_citation, causal_overreach
  key conclusions preserved         -> key_conclusion_lost
  hype refused; jargon matched      -> hype_language, jargon_for_public,
                                       abbr_unexpanded, term_inconsistent
  reviewable change list            -> change_list_missing, change_no_action,
                                       change_no_reason, open_questions_missing
  declared inputs                   -> audience_undeclared, source_text_missing
  nothing to audit                  -> no_text

    python bench_diss.py
"""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "audience": "public",
    "evidence": ["doe2020"],
    "source_text": "Uptake rose 3-fold under the coating.",
    "key_conclusions": ["A porous coating raises uptake 3-fold"],
    "limitations": "only one material tested",
    "text": "A porous coating raises uptake 3-fold [doe2020].",
    "open_questions": [],
    "changes": [{"action": "replaced technical terms with plain language",
                 "reason": "audience is public"}],
}

def d(**over):
    s = copy.deepcopy(BASE); s.update(over); return s

def _without(key: str):
    s = copy.deepcopy(BASE); s.pop(key, None); return s

SCEN = [
    ("clean", lambda: (d(), [])),
    ("hype", lambda: (d(text="A revolutionary coating raises uptake 3-fold [doe2020]."), ["diss.hype_language"])),
    ("absolute_uncited", lambda: (d(text="The coating always raises uptake 3-fold."), ["diss.absolute_without_citation"])),
    ("invariant_broken", lambda: (d(text="A porous coating raises uptake 9-fold [doe2020]."), ["diss.invariant_broken"])),
    ("invariant_added", lambda: (d(text="A porous coating raises uptake 3-fold and costs 50 yuan [doe2020]."), ["diss.invariant_added"])),
    ("key_conclusion_lost", lambda: (d(key_conclusions=["A porous coating reduces toxicity"], text="A porous coating raises uptake 3-fold [doe2020]."), ["diss.key_conclusion_lost"])),
    ("change_list_missing", lambda: (d(changes=[]), ["diss.change_list_missing"])),
    ("change_no_action", lambda: (d(changes=[{"reason": "audience is public"}]), ["diss.change_no_action"])),
    ("change_no_reason", lambda: (d(changes=[{"action": "x"}]), ["diss.change_no_reason"])),
    ("limitations_omitted", lambda: (d(limitations=""), ["diss.limitations_omitted"])),
    ("unknown_source", lambda: (d(text="A porous coating raises uptake 3-fold [ghost]."), ["diss.unknown_source"])),
    ("no_text", lambda: (d(text=""), ["diss.no_text"])),

    # --- declared inputs ---------------------------------------------------
    ("audience_undeclared", lambda: (d(audience=""), ["diss.audience_undeclared"])),
    ("source_text_missing", lambda: (d(source_text=""), ["diss.source_text_missing"])),

    # --- figure references must survive ------------------------------------
    ("xref_lost", lambda: (d(source_text="Uptake rose 3-fold under the coating (Fig 3b)."),
                           ["diss.xref_lost"])),
    ("fp_xref_kept", lambda: (d(source_text="Uptake rose 3-fold under the coating (Fig 3b).",
                                text="A porous coating raises uptake 3-fold (Fig. 3b) [doe2020]."), [])),

    # --- related must not become causal ------------------------------------
    ("causal_overreach", lambda: (d(text="A porous coating causes uptake to rise 3-fold [doe2020]."),
                                  ["diss.causal_overreach", "diss.key_conclusion_lost"])),
    ("fp_causal_in_source", lambda: (d(
        source_text="The coating causes pore retention, and uptake rose 3-fold under the coating.",
        text="A porous coating raises uptake 3-fold because the coating causes pore "
             "retention [doe2020]."), [])),

    # --- open questions are declared, not silent ---------------------------
    ("open_questions_missing", lambda: (_without("open_questions"),
                                        ["diss.open_questions_missing"])),
    ("fp_open_questions_empty", lambda: (d(), [])),  # declared empty is accepted

    # --- abbreviations need their expansion --------------------------------
    ("abbr_unexpanded", lambda: (d(
        abbreviations={"ELISA": "enzyme-linked immunosorbent assay"},
        text="The ELISA assay shows a porous coating raises uptake 3-fold [doe2020]."),
        ["diss.abbr_unexpanded"])),
    ("fp_abbr_expanded", lambda: (d(
        abbreviations={"ELISA": "enzyme-linked immunosorbent assay"},
        key_conclusions=["a porous coating raises uptake 3-fold"],
        text="The enzyme-linked immunosorbent assay (ELISA) shows a porous coating raises "
             "uptake 3-fold [doe2020]."), [])),

    # --- one concept, one name ---------------------------------------------
    ("term_inconsistent", lambda: (d(
        term_locks={"uptake rate": {"preferred": "uptake rate",
                                    "variants": ["absorption speed"]}},
        text="A porous coating raises uptake 3-fold, so the absorption speed rises [doe2020]."),
        ["diss.term_inconsistent"])),
    ("fp_term_lock_clean", lambda: (d(
        term_locks={"uptake rate": {"preferred": "uptake rate",
                                    "variants": ["absorption speed"]}},
        text="A porous coating raises uptake 3-fold [doe2020]."), [])),

    # --- jargon list still fires for a public audience ----------------------
    ("jargon_for_public", lambda: (d(jargon_terms=["adsorption isotherm"],
        text="A porous coating raises uptake 3-fold via the adsorption isotherm [doe2020]."),
        ["diss.jargon_for_public"])),
]

def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "dissemination")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok, "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")
    passed = sum(1 for r in rows if r["pass"])
    (Path(__file__).resolve().parent / "report_diss.json").write_text(
        json.dumps({"schema_version": "diss-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())
