"""Independent, standard-library bench for the real SQLite execution engine.

The fixture is created at run time.  No binary database or prepared official
answer is shipped.  Aggregate gold values below are independent Python-computed
literals, not output copied from the query being tested.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbquery as D  # noqa: E402


DICTIONARY = {
    "id": {"description": "stable row identifier", "semantic": "id"},
    "experiment_id": {"description": "experiment foreign key", "semantic": "id"},
    "measurement_id": {"description": "measurement identifier", "semantic": "id"},
    "name": {"description": "experimental arm", "semantic": "categorical"},
    "value": {"description": "response in arbitrary units", "unit": "AU", "semantic": "numeric"},
    "mean_value": {"description": "arithmetic mean response", "unit": "AU", "semantic": "numeric"},
    "n": {"description": "number of measurements", "semantic": "count"},
    "note": {"description": "optional measurement annotation", "semantic": "text"},
    "concentration": {"description": "concentration in concentration_unit", "semantic": "numeric"},
    "concentration_unit": {"description": "declared concentration unit", "semantic": "unit"},
    "dose": {"description": "dose in dose_unit", "semantic": "numeric"},
    "dose_unit": {"description": "declared dose unit", "semantic": "unit"},
    "text": {"description": "literal text result", "semantic": "text"},
    "x": {"description": "test value", "semantic": "numeric"},
}


def create_fixture(path: Path) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE experiments (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            dose REAL,
            dose_unit TEXT
        );
        CREATE TABLE measurements (
            id INTEGER PRIMARY KEY,
            experiment_id INTEGER NOT NULL,
            value REAL NOT NULL,
            concentration REAL,
            concentration_unit TEXT,
            note TEXT,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id)
        );
        INSERT INTO experiments VALUES
            (1, 'Control', 1.0, 'g'),
            (2, 'Treated', 500.0, 'mg'),
            (3, 'Empty', NULL, NULL);
        INSERT INTO measurements VALUES
            (1, 1, 1.5, 1000.0, 'uM', 'A'),
            (2, 1, 2.5, 2000.0, 'uM', NULL),
            (3, 2, 3.0, 1.0, 'mM', 'B'),
            (4, 2, 4.0, 2.0, 'mM', 'B');
        PRAGMA user_version = 7;
    """)
    connection.close()


def spec(sql: str, **extra) -> dict:
    result = {"sql": sql, "data_dictionary": DICTIONARY, "numeric_tolerance": 1e-9}
    result.update(extra)
    return result


def check_clean(r):
    assert not r["findings"], r["findings"]
    assert r["status"] == "clean"
    assert r["execution"]["row_count"] == 3
    assert r["rows"][0] == {"id": 1, "name": "Control"}
    assert r["query_plan"], "real SQLite plan is empty"


def check_null(r):
    assert r["quality_report"]["per_column"]["note"]["null_count"] == 1
    assert r["analysis_result"]["summary"]["nulls"]["note"] == 1
    assert r["rows"][1]["note"] is None
    assert not r["findings"]


def check_aggregate(r):
    # Independently derived from (1.5, 2.5) and (3.0, 4.0).
    assert r["rows"] == [
        {"name": "Control", "n": 2, "mean_value": 2.0},
        {"name": "Treated", "n": 2, "mean_value": 3.5},
    ]
    assert r["relationships"]["joins"][0]["pairs"][0]["declared_foreign_key"] is True
    assert r["aggregation"]["grain"] == ["name"]
    assert r["aggregation"]["grain_check"]["unique"] is True
    assert r["conclusions"]["independent_check_passed"] is True
    assert not r["findings"], r["findings"]


def check_left_join(r):
    assert r["execution"]["row_count"] == 5
    assert r["rows"][-1]["measurement_id"] is None
    assert r["aggregation"]["grain_check"]["unique"] is True
    assert not r["findings"], r["findings"]


def check_units(r):
    column = r["analysis_rows"][0].keys() - r["rows"][0].keys()
    assert column == {"concentration__mM"}
    assert [row["concentration__mM"] for row in r["analysis_rows"]] == [1.0, 2.0, 1.0, 2.0]
    assert [row["concentration"] for row in r["rows"]] == [1000.0, 2000.0, 1.0, 2.0]
    assert all(change["dimension"] in ("molar", "same_unit") for change in r["unit_changes"])
    assert not r["findings"], r["findings"]


def check_duplicate_columns(r):
    assert list(r["rows"][0]) == ["id", "id__2"]
    assert r["rows"][0] == {"id": 1, "id__2": 1}


def check_deterministic(r):
    assert r["execution"]["snapshot_stable"] is True


AGG_SQL = """
SELECT e.name AS name, COUNT(m.id) AS n, AVG(m.value) AS mean_value
FROM experiments AS e
JOIN measurements AS m ON e.id = m.experiment_id
GROUP BY e.name
ORDER BY e.name
""".strip()


SCENARIOS = [
    ("clean_select", spec("SELECT id, name FROM experiments ORDER BY id",
                          expected_row_count=3,
                          expected_rows=[{"id": 1, "name": "Control"}, {"id": 2, "name": "Treated"}, {"id": 3, "name": "Empty"}]),
     [], "clean", check_clean),
    ("null_preserved", spec("SELECT id, note FROM measurements ORDER BY id",
                            expected_summary={"row_count": 4, "nulls": {"note": 1}}),
     [], "clean", check_null),
    ("aggregate_gold", spec(AGG_SQL, grain=["name"],
                            expected_row_count=2,
                            expected_rows=[{"name": "Control", "n": 2, "mean_value": 2.0},
                                           {"name": "Treated", "n": 2, "mean_value": 3.5}],
                            expected_summary={"row_count": 2, "sums": {"n": 4}},
                            independent_check="SELECT CASE WHEN (SELECT AVG(value) FROM measurements WHERE experiment_id=1)=2.0 THEN 1 ELSE 0 END"),
     [], "clean", check_aggregate),
    ("left_join_null", spec("SELECT e.id AS experiment_id, m.id AS measurement_id FROM experiments e LEFT JOIN measurements m ON e.id=m.experiment_id ORDER BY experiment_id, measurement_id",
                            grain=["measurement_id"], expected_row_count=5),
     [], "clean", check_left_join),
    ("not_null_violation", spec("SELECT id, note FROM measurements ORDER BY id", not_null=["note"]),
     ["validation.unexpected_null"], "blocked", None),
    ("temperature_conversion", spec("SELECT 32.0 AS value",
                                    units={"value": {"source_unit": "F", "target_unit": "K"}},
                                    expected_summary={"sums": {"value__K": 273.15}}),
     [], "clean", None),
    ("duplicate_grain", spec("SELECT experiment_id, value FROM measurements ORDER BY id", grain=["experiment_id"]),
     ["validation.grain_not_unique"], "blocked", None),
    ("duplicate_rows", spec("SELECT 1 AS x UNION ALL SELECT 1 AS x"),
     ["data.duplicate_rows"], "review", None),
    ("unit_conversion", spec("SELECT id, concentration, concentration_unit FROM measurements ORDER BY id",
                             units={"concentration": {"unit_column": "concentration_unit", "target_unit": "mM"}},
                             expected_summary={"sums": {"concentration__mM": 6.0}}),
     [], "clean", check_units),
    ("unit_incompatible", spec("SELECT id, concentration, concentration_unit FROM measurements ORDER BY id",
                               units={"concentration": {"unit_column": "concentration_unit", "target_unit": "g"}}),
     ["unit.incompatible"], "blocked", None),
    ("mixed_units_audit", spec("SELECT id, concentration, concentration_unit FROM measurements ORDER BY id",
                               units={"concentration": {"unit_column": "concentration_unit"}}),
     ["unit.mixed_units"], "review", None),
    ("empty_result", spec("SELECT id FROM experiments WHERE 0"), ["query.empty_result"], "review", None),
    ("row_count_mismatch", spec("SELECT id FROM experiments", expected_row_count=99),
     ["validation.row_count_mismatch"], "blocked", None),
    ("expected_rows_mismatch", spec("SELECT id FROM experiments ORDER BY id", expected_rows=[{"id": 999}]),
     ["validation.rows_mismatch"], "blocked", None),
    ("independent_check_failure", spec("SELECT id FROM experiments ORDER BY id",
                                       independent_check="SELECT CASE WHEN (SELECT COUNT(*) FROM experiments)=99 THEN 1 ELSE 0 END"),
     ["validation.independent_check_failed"], "blocked", None),
    ("write_rejected", spec("DELETE FROM measurements"), ["query.not_read_only"], "refused", None),
    ("multi_statement_rejected", spec("SELECT 1; DELETE FROM measurements"), ["query.multiple_statements"], "refused", None),
    ("cte_write_rejected", spec("WITH x AS (SELECT 1) DELETE FROM measurements"),
     ["security.read_only_violation"], "refused", None),
    ("attach_rejected", spec("ATTACH DATABASE 'other-db' AS other"), ["query.not_read_only"], "refused", None),
    ("dangerous_function_rejected", spec("SELECT load_extension('x')"),
     ["security.read_only_violation"], "refused", None),
    ("readfile_rejected", spec("SELECT readfile('secret.txt')"),
     ["security.read_only_violation"], "refused", None),
    ("duplicate_columns", spec("SELECT id, id FROM experiments ORDER BY id"),
     ["query.duplicate_column_names"], "review", check_duplicate_columns),
    ("semicolon_literal", spec("SELECT ';' AS text"), [], "clean", None),
    ("valid_cte", spec("WITH selected AS (SELECT id, name FROM experiments) SELECT id, name FROM selected ORDER BY id",
                       expected_row_count=3), [], "clean", None),
    ("comma_join_condition", spec("SELECT e.id AS experiment_id, m.id AS measurement_id FROM experiments e, measurements m WHERE e.id=m.experiment_id ORDER BY measurement_id",
                                  expected_row_count=4), [], "clean", None),
    ("join_without_condition", spec("SELECT e.id AS experiment_id, m.id AS measurement_id FROM experiments e JOIN measurements m"),
     ["join.condition_missing"], "blocked", None),
    ("truncated_result", spec("SELECT id FROM measurements ORDER BY id", max_rows=2),
     ["query.rows_truncated"], "blocked", None),
    ("contract_passthrough", spec("SELECT id, name FROM experiments ORDER BY id", case_id="case-db-001",
                                  output_contract=["status", "rows", "query_plan", "execution", "custom_field"],
                                  custom_field={"from_spec": True}), [], "clean", None),
]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory(prefix="dbquery-bench-") as tmp:
        root = Path(tmp)
        db = root / "fixture"
        invalid = root / "invalid-db"
        invalid.write_text("not a sqlite database", encoding="utf-8")
        for name, case_spec, expected, expected_status, checker in SCENARIOS:
            create_fixture(db)
            before = file_hash(db)
            out = root / name
            target = invalid if name == "invalid_database" else root / "missing-db" if name == "missing_database" else db
            result = D.run_analysis(target, case_spec, out)
            fired = {finding["rule"] for finding in result.get("findings", [])}
            failures = [f"missing rule: {rule}" for rule in expected if rule not in fired]
            if result["status"] != expected_status:
                failures.append(f"status {result['status']} != {expected_status}")
            if not expected and result["findings"]:
                failures.append(f"unexpected findings: {sorted(fired)}")
            if before != file_hash(db):
                failures.append("read-only execution mutated fixture bytes")
            if not (out / "result.json").is_file():
                failures.append("result.json absent")
            if expected_status == "refused" and isinstance(case_spec.get("sql"), str):
                if not (out / "query.sql").is_file() or (out / "query.sql").stat().st_size == 0:
                    failures.append("failed query.sql was not retained")
            if checker:
                try:
                    checker(result)
                except Exception as exc:
                    failures.append(f"content check: {type(exc).__name__}: {exc}")
            if expected_status in ("clean", "review", "blocked") and (out / "query.sql").is_file():
                if not (out / "query_plan.json").is_file() or (out / "query_plan.json").stat().st_size < 10:
                    failures.append("real query plan missing/empty")
                if not (out / "rows.json").is_file():
                    failures.append("rows.json missing")
            if name == "contract_passthrough":
                for key in ("case_id", "status", "rows", "query_plan", "execution", "custom_field"):
                    if key not in result:
                        failures.append(f"contract key absent: {key}")
                if result.get("case_id") != "case-db-001" or result.get("custom_field") != {"from_spec": True}:
                    failures.append("case_id/custom_field not passed verbatim")
            rows.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                         "status": result["status"], "exit_code": D.EXIT_CODES[result["status"]],
                         "failures": failures, "pass": not failures})
        # Missing/invalid environments are separate because no valid fixture is used.
        for name, target, rule in (("missing_database", root / "absent-db", "connection.unavailable"),
                                   ("invalid_database", invalid, "connection.invalid_database"),
                                   ("unsupported_driver", db, "connection.unsupported_driver")):
            case_spec = spec("SELECT 1", driver="postgres" if name == "unsupported_driver" else "sqlite")
            out = root / name
            result = D.run_analysis(target, case_spec, out)
            failures = [] if result["status"] == "undetermined" and any(f["rule"] == rule for f in result["findings"]) else ["wrong structured environment refusal"]
            if not (out / "result.json").is_file():
                failures.append("result.json absent")
            rows.append({"scenario": name, "expected": [rule],
                         "fired": [f["rule"] for f in result["findings"]], "status": result["status"],
                         "exit_code": D.EXIT_CODES[result["status"]], "failures": failures, "pass": not failures})
        # Same output path and identical bytes: no timestamps or elapsed-time noise.
        deterministic_dir = root / "deterministic"
        first = D.run_analysis(db, spec("SELECT id, name FROM experiments ORDER BY id", expected_row_count=3), deterministic_dir)
        first_bytes = (deterministic_dir / "result.json").read_bytes()
        second = D.run_analysis(db, spec("SELECT id, name FROM experiments ORDER BY id", expected_row_count=3), deterministic_dir)
        second_bytes = (deterministic_dir / "result.json").read_bytes()
        failures = [] if first_bytes == second_bytes and first["rows"] == second["rows"] else ["non-deterministic result bytes"]
        rows.append({"scenario": "deterministic_rerun", "expected": [], "fired": [],
                     "status": second["status"], "exit_code": D.EXIT_CODES[second["status"]],
                     "failures": failures, "pass": not failures})
    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "dbquery-bench/v1", "totals": {"passed": passed, "of": len(rows)},
              "scenarios": rows,
              "gold_note": "Aggregate gold rows are independent literals from the known fixture; databases are generated in temp dirs."}
    output = Path(__file__).resolve().parent / "report_dbquery.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(f"{'PASS' if row['pass'] else 'FAIL'} {row['scenario']:<30} status={row['status']:<12} failures={row['failures']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
