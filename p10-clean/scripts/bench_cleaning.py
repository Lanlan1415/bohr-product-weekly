"""Benchmark for the cleaning engine: one planted defect or one FP guard per scenario.

Every rule id the engine can report is covered by a defect scenario (the rule must
fire) or a repaired-twin guard (the rule must stay silent on the repaired input).
The clean baseline must report nothing, so a detector cannot pass by flagging
everything. CLI scenarios exercise the refusal paths of cleandata.py — every one
must end undetermined with a written result file, never a traceback.

    python bench_cleaning.py
"""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleaning as C
import cleandata as CL

BASE = {
 "columns":[{"name":"bandgap","target_unit":"eV","plausible":[0,6]},
            {"name":"conc","target_unit":"mol/L","plausible":[0,100]}],
 "key_columns":["material"], "value_columns":["bandgap"],
}
CLEAN_ROWS = [{"material":"TiO2","bandgap":"3.20 eV","conc":"5 mM"},
              {"material":"ZnO","bandgap":"3.37 eV","conc":"1 mM"}]


def mk(rows, **over):
    spec = copy.deepcopy(BASE); spec["rows"] = rows; spec.update(over)
    return spec, rows


def s_clean():      return "run", mk(copy.deepcopy(CLEAN_ROWS)), []
def s_missing():    return "run", mk(copy.deepcopy(CLEAN_ROWS)+[{"material":"GaN","bandgap":"not reported","conc":"1 mM"}]), ["clean.missing_values"]
def s_unparsed():   return "run", mk(copy.deepcopy(CLEAN_ROWS)+[{"material":"GaN","bandgap":"about 3.4 eV","conc":"1 mM"}]), ["clean.unparsed_values"]
def s_dup_record(): return "run", mk(copy.deepcopy(CLEAN_ROWS)+[dict(CLEAN_ROWS[0])]), ["clean.duplicate_records"]
def s_dup_experiment():
    return "run", mk(copy.deepcopy(CLEAN_ROWS)+[{"material":"TiO2","bandgap":"3.10 eV","conc":"5 mM"}]), ["clean.duplicate_experiments"]


# --- field mapping (R10) and the unmapped-fields list ------------------------

def s_alias_mapped():
    """FP guard: an aliased source column is renamed and never reported unmapped."""
    spec, rows = mk([{"material":"TiO2","bg":"3.20 eV","conc":"5 mM"}],
                    field_aliases={"bg":"bandgap"})
    return "run", (spec, rows), [], {"r10_in_ledger": True, "canonical_key": "bandgap"}

def s_alias_unmapped():
    """An undeclared, unaliased column is named, not silently carried."""
    spec, rows = mk([{"material":"TiO2","bandgap":"3.20 eV","conc":"5 mM","ph":"7.4"}])
    return "run", (spec, rows), ["clean.unmapped_columns"]

def s_declared_absent():
    """A schema field no row carries is declared-dead, not silent."""
    spec, rows = mk([{"material":"TiO2","bandgap":"3.20 eV","conc":"5 mM"}],
                    columns=copy.deepcopy(BASE["columns"])+[{"name":"strain","semantic":"numeric"}])
    return "run", (spec, rows), ["clean.declared_fields_absent"]

# --- synonym normalisation (R11) ---------------------------------------------

def s_synonym_merge():
    """Declared synonyms merge the same entity under one reviewable key."""
    spec, rows = mk([{"material":"TiO2","bandgap":"3.20 eV","conc":"5 mM"},
                     {"material":"titanium dioxide","bandgap":"3.05 eV","conc":"5 mM"},
                     {"material":"TIO2","bandgap":"3.30 eV","conc":"5 mM"}],
                    synonyms={"titanium dioxide":"TiO2","tio2":"TiO2"})
    return "run", (spec, rows), ["clean.duplicate_experiments"], {"synonym_unmapped_empty": True}

def s_synonym_unmapped():
    """A spelling outside the synonym table is listed for human confirmation."""
    spec, rows = mk([{"material":"TiO2","bandgap":"3.20 eV","conc":"5 mM"},
                     {"material":"SnO2","bandgap":"1.5 eV","conc":"5 mM"}],
                    synonyms={"tio2":"TiO2"})
    return "run", (spec, rows), ["clean.synonym_unmapped"]

# --- structured unit conversion (R04) -----------------------------------------

def s_range_conversion():
    """FP guard: a range converts both endpoints and stays a range."""
    spec, rows = mk([{"material":"GaN","bandgap":"3.0-3.4 eV","conc":"1 mM"}],
                    columns=[{"name":"bandgap","target_unit":"meV","plausible":[0,6000]},
                             {"name":"conc","target_unit":"mol/L","plausible":[0,100]}])
    return "run", (spec, rows), [], {"r04_new": "3000-3400 meV"}

def s_plusminus_conversion():
    """FP guard: the error bar converts with the value, never dropped."""
    spec, rows = mk([{"material":"GaN","bandgap":"3.20 eV","conc":"1 mM"}],
                    columns=[{"name":"bandgap","target_unit":"eV","plausible":[0,6]},
                             {"name":"volt","target_unit":"V"}],
                    value_columns=["bandgap","volt"])
    rows[0]["volt"] = "12\u00b10.5 mV"
    return "run", (spec, rows), [], {"r04_new": "0.012\u00b10.0005 V"}

# --- provenance and the to-confirm list ----------------------------------------

def s_provenance():
    """FP guard: with a source column every change carries its origin."""
    spec, rows = mk([{"material":"TiO2","bandgap":" 3.20 eV ","conc":"5 mM","study":"S1"},
                     {"material":"ZnO","bandgap":" 3.37 eV ","conc":"1 mM","study":"S2"}],
                    source_column="study")
    return "run", (spec, rows), [], {"provenance_sources": ["S1","S2"]}

def s_pending_review():
    """Unparsed cells and duplicate experiments land in the to-confirm list."""
    spec, rows = mk([{"material":"TiO2","bandgap":"about 3.2 eV","conc":"5 mM"},
                     {"material":"TiO2","bandgap":"3.10 eV","conc":"5 mM"}])
    return "run", (spec, rows), ["clean.unparsed_values","clean.duplicate_experiments"], \
        {"pending_whats": {"unparsed","duplicate_experiment"}}

# --- CLI refusal paths (undetermined, never a traceback) ------------------------

def s_cli_missing_spec():
    """A spec file that does not exist is refused, not a FileNotFoundError."""
    return "cli", {"spec": "__no_such_spec__.json"}, ["clean.spec_unreadable"], \
        {"status": "undetermined"}

def s_cli_rows_not_list():
    """spec.rows that is a string is refused, not enumerated character by character."""
    return "cli", {"payload": {"rows": "hello", "columns": [{"name": "bandgap"}]}}, \
        ["clean.spec_unreadable"], {"status": "undetermined"}

def s_cli_empty_rows():
    """An empty rows list is refused (clean.no_rows), not reported as clean."""
    return "cli", {"payload": {"rows": [], "columns": [{"name": "bandgap"}]}}, \
        ["clean.no_rows"], {"status": "undetermined"}

def s_cli_no_table():
    """Neither rows nor a table path is refused (clean.no_table)."""
    return "cli", {"payload": {"columns": [{"name": "bandgap"}]}}, \
        ["clean.no_table"], {"status": "undetermined"}

def s_cli_table_unreadable():
    """A table file that is not valid UTF-8 text is refused, not a traceback."""
    return "cli", {"payload": {"columns": [{"name": "bandgap"}], "table_path": "gbk_table.csv"},
                   "bytes": b"\xb1\xea\xc7\xa9,\xca\xfd\xd6\xb5\n\xcf\xb5\xcd\xb3,12\n"}, \
        ["clean.table_unreadable"], {"status": "undetermined"}

def s_cli_case_contract():
    """FP guard: --case supplies case_id and the output_contract echo; the run stays clean."""
    return "cli", {"payload": {"columns": [{"name": "bandgap", "target_unit": "eV"}],
                               "key_columns": ["material"],
                               "rows": [{"material": "TiO2", "bandgap": "3.20 eV"}],
                               "summary": "contract echo demo"},
                   "case": {"case_id": "case-demo-001",
                            "output_contract": {"case_id": "echo", "status": "audit",
                                                "summary": "pass-through", "changes": "ledger",
                                                "cleaned_table": "table", "notes": "unknown"}}}, \
        [], {"status": "clean", "case_id": "case-demo-001",
             "summary": "contract echo demo", "notes_is_none": True}


SCEN = [("clean", s_clean), ("missing", s_missing), ("unparsed", s_unparsed),
        ("duplicate_record", s_dup_record), ("duplicate_experiment", s_dup_experiment),
        ("alias_mapped", s_alias_mapped), ("alias_unmapped", s_alias_unmapped),
        ("declared_absent", s_declared_absent),
        ("synonym_merge", s_synonym_merge), ("synonym_unmapped", s_synonym_unmapped),
        ("range_conversion", s_range_conversion), ("plusminus_conversion", s_plusminus_conversion),
        ("provenance", s_provenance), ("pending_review", s_pending_review),
        ("cli_missing_spec", s_cli_missing_spec), ("cli_rows_not_list", s_cli_rows_not_list),
        ("cli_empty_rows", s_cli_empty_rows), ("cli_no_table", s_cli_no_table),
        ("cli_table_unreadable", s_cli_table_unreadable), ("cli_case_contract", s_cli_case_contract)]


def run_cli(payload: dict, root: Path) -> dict:
    name = payload.get("spec")
    out = root / "res"
    out.mkdir(parents=True, exist_ok=True)
    if name:
        return CL.build_and_audit(root / name, out)
    sp = root / "spec.json"
    body = payload["payload"]
    if "bytes" in payload:
        (root / body["table_path"]).write_bytes(payload["bytes"])
    sp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    case = root / "case.json"
    if payload.get("case"):
        case.write_text(json.dumps(payload["case"], ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return CL.build_and_audit(sp, out, case)
    return CL.build_and_audit(sp, out)


def main() -> int:
    root = Path(__file__).resolve().parent / "_run"
    if root.exists():
        import shutil
        shutil.rmtree(root)  # a fresh scratch tree: the already_cleaned guard must not
                             # trip on a previous bench run's result.json
    rows_out = []
    for name, builder in SCEN:
        built = builder()
        kind, payload, expect = built[0], built[1], built[2]
        extra_asserts = built[3] if len(built) > 3 else {}
        missing = []
        if kind == "run":
            spec, rows = payload
            r = C.clean(rows, spec)
        else:
            r = run_cli(payload, root / name)
            got = extra_asserts.pop("status", None)
            if got and r["status"] != got:
                missing.append("status:" + r["status"])
        fired = {f["rule"] for f in r["findings"]}
        missing.extend(x for x in expect if x not in fired)
        spurious = [] if expect else [f["rule"] for f in r["findings"]
                                      if f["severity"] in ("high", "medium")]
        if kind == "run" and not r.get("idempotent"):
            missing.append("idempotent")
        # per-scenario structural asserts, one per planted rule/guard
        if extra_asserts.get("r10_in_ledger") and "R10" not in r.get("changes_by_rule", {}):
            missing.append("R10_ledger")
        if extra_asserts.get("canonical_key"):
            keys = set(r["cleaned_table"][0]) if r.get("cleaned_table") else set()
            if extra_asserts["canonical_key"] not in keys:
                missing.append("canonical_key")
        if extra_asserts.get("r04_new"):
            news = [c.get("new") for c in r.get("changes", []) if c.get("rule") == "R04"]
            if extra_asserts["r04_new"] not in news:
                missing.append("r04_new:" + str(news))
            cleaned_cell = (r.get("cleaned_table") or [{}])[0]
            hit = [v for v in cleaned_cell.values() if v == extra_asserts["r04_new"]]
            if not hit:
                missing.append("r04_cleaned_cell")
        if extra_asserts.get("synonym_unmapped_empty") and r["duplicates"]["synonym_unmapped"]:
            missing.append("synonym_unmapped_not_empty")
        if extra_asserts.get("provenance_sources"):
            got = (r.get("provenance") or {}).get("sources")
            if got != extra_asserts["provenance_sources"]:
                missing.append("provenance:" + str(got))
            if not all("source" in c for c in r.get("changes", [])):
                missing.append("changes_without_source")
        if extra_asserts.get("pending_whats"):
            whats = {p.get("what") for p in r.get("pending_review", [])}
            if not extra_asserts["pending_whats"] <= whats:
                missing.append("pending:" + str(sorted(whats)))
        if extra_asserts.get("case_id") and r.get("case_id") != extra_asserts["case_id"]:
            missing.append("case_id:" + str(r.get("case_id")))
        if extra_asserts.get("summary") and r.get("summary") != extra_asserts["summary"]:
            missing.append("summary:" + str(r.get("summary")))
        if extra_asserts.get("notes_is_none") and r.get("notes") is not None:
            missing.append("notes_not_none")
        ok = not missing and not spurious
        rows_out.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                         "missing": missing, "spurious": spurious,
                         "idempotent": r.get("idempotent"), "status": r.get("status"),
                         "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} expected={expect} missing={missing} "
              f"spurious={spurious}")
    passed = sum(1 for r in rows_out if r["pass"])
    (Path(__file__).resolve().parent / "report_cleaning.json").write_text(
        json.dumps({"schema_version": "cleaning-bench/v2", "scenarios": rows_out,
                    "totals": {"passed": passed, "of": len(rows_out)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows_out)} pass")
    return 0 if passed == len(rows_out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
