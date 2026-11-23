"""Adversarial and boundary tests for scicode; standard library unittest."""
from __future__ import annotations

import copy
import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
CLI = HERE / "scicode.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import codegen  # noqa: E402
import runner  # noqa: E402

ROWS = [
    {"sample": "S1", "x": "1", "y": "2"},
    {"sample": "S2", "x": "2", "y": "4"},
    {"sample": "S3", "x": "3", "y": "6"},
]
SPEC = {
    "case_id": "adversarial", "section": "scicode",
    "input": {"path": "data.csv", "format": "csv"},
    "columns": [{"name": "sample", "type": "id"},
                {"name": "x", "type": "numeric"}, {"name": "y", "type": "numeric"}],
    "metrics": ["x", "y"],
}
CASE = {"case_id": "adversarial", "case_payload": "case-value",
        "output_contract": {"status": "engine", "analysis_result": "engine",
                            "execution_result": "engine", "case_payload": "case",
                            "missing_payload": "null"}}


class CLIMixin:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="scicode-adversarial-")
        self.root = Path(self.temporary.name)
        self.out = self.root / "out"
        with (self.root / "data.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["sample", "x", "y"], lineterminator="\n")
            writer.writeheader()
            writer.writerows(ROWS)
        self.write_spec(SPEC)
        self.write_case(CASE)

    def tearDown(self):
        self.temporary.cleanup()

    def write_spec(self, value, raw=False):
        text = value if raw else json.dumps(value, ensure_ascii=False)
        (self.root / "spec.json").write_text(text, encoding="utf-8")

    def write_case(self, value, raw=False):
        text = value if raw else json.dumps(value, ensure_ascii=False)
        (self.root / "case.json").write_text(text, encoding="utf-8")

    def invoke(self, extra=(), case=True):
        command = [sys.executable, "-I", str(CLI), "--spec", str(self.root / "spec.json"),
                   "--out", str(self.out)]
        if case:
            command += ["--case", str(self.root / "case.json")]
        command += list(extra)
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)
        result = json.loads((self.out / "result.json").read_text(encoding="utf-8"))
        self.assertNotIn("Traceback", process.stdout)
        self.assertNotIn("Traceback", process.stderr)
        return process, result

    def assert_refusal(self, process, result, rule, rc=5):
        self.assertEqual(process.returncode, rc, (process.stdout, process.stderr, result))
        self.assertEqual(result["status"], "undetermined" if rc == 5 else result["status"])
        self.assertIn(rule, {finding["rule"] for finding in result["findings"]})
        self.assertIn("case_id", result)
        self.assertIsNone(result["analysis_result"])
        self.assertFalse(result["execution_result"]["executed"])


class AdversarialCLI(CLIMixin, unittest.TestCase):
    def test_clean_exit_and_contract(self):
        process, result = self.invoke()
        self.assertEqual(process.returncode, 0)
        self.assertEqual(result["case_payload"], "case-value")
        self.assertIsNone(result["missing_payload"])
        self.assertTrue(any("missing_payload" in x for x in result["limits"]))

    def test_bad_json(self):
        self.write_spec("{bad", raw=True)
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.spec_unreadable")
        self.assertEqual(result["case_payload"], "case-value")
        self.assertIn("missing_payload", result)

    def test_non_object_spec(self):
        for value in ([], "text", 42, None):
            with self.subTest(value=value):
                self.write_spec(value)
                process, result = self.invoke()
                self.assert_refusal(process, result, "input.spec_not_object")

    def test_missing_spec_file(self):
        (self.root / "spec.json").unlink()
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.spec_unreadable")

    def test_missing_input_file(self):
        (self.root / "data.csv").unlink()
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.file_missing")

    def test_missing_case_file(self):
        (self.root / "case.json").unlink()
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.case_unreadable")
        self.assertEqual(result["case_id"], "adversarial")

    def test_bad_case_json_still_uses_spec_contract(self):
        self.write_case("[", raw=True)
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.case_unreadable")
        self.assertEqual(result["case_id"], "adversarial")

    def test_wrong_input_types(self):
        for value in ("data.csv", [], None, 42):
            with self.subTest(value=value):
                spec = copy.deepcopy(SPEC)
                spec["input"] = value
                self.write_spec(spec)
                process, result = self.invoke()
                self.assert_refusal(process, result, "input.path_invalid")

    def test_empty_csv(self):
        (self.root / "data.csv").write_text("sample,x,y\n", encoding="utf-8")
        process, result = self.invoke()
        self.assertEqual(process.returncode, 5)
        self.assertIn("input.no_rows", {f["rule"] for f in result["findings"]})
        self.assertTrue(result["execution_result"]["executed"])
        self.assertEqual(result["execution_result"]["stderr"], "")

    def test_duplicate_header_and_wide_row_refused(self):
        for text, rule in (("sample,x,x,y\nS,1,2,3\n", "input.duplicate_columns"),
                           ("sample,x,y\nS,1,2,unexpected\n", "input.row_shape")):
            with self.subTest(rule=rule):
                (self.root / "data.csv").write_text(text, encoding="utf-8")
                process, result = self.invoke()
                self.assertEqual(process.returncode, 4)
                self.assertIn(rule, {f["rule"] for f in result["findings"]})
                self.assertEqual(result["execution_result"]["stderr"], "")

    def test_malformed_json_input_is_structured(self):
        spec = copy.deepcopy(SPEC)
        spec["input"] = {"path": "data.json", "format": "json"}
        self.write_spec(spec)
        (self.root / "data.json").write_text("{bad", encoding="utf-8")
        process, result = self.invoke()
        self.assertEqual(process.returncode, 5)
        self.assertIn("execution.analysis_error", {f["rule"] for f in result["findings"]})
        self.assertNotIn("Traceback", result["execution_result"]["stderr"])

    def test_json_non_list_and_scalar_rows(self):
        for value in ({"x": 1}, [1, 2]):
            with self.subTest(value=value):
                spec = copy.deepcopy(SPEC)
                spec["input"] = {"path": "data.json", "format": "json"}
                self.write_spec(spec)
                (self.root / "data.json").write_text(json.dumps(value), encoding="utf-8")
                process, result = self.invoke()
                self.assertEqual(process.returncode, 5)
                self.assertTrue({f["rule"] for f in result["findings"]} &
                                {"input.rows_type", "input.row_type"})

    def test_unknown_section(self):
        spec = copy.deepcopy(SPEC)
        spec["section"] = "database-cleaning"
        self.write_spec(spec)
        process, result = self.invoke()
        self.assert_refusal(process, result, "section.unknown")

    def test_network_url_refused(self):
        spec = copy.deepcopy(SPEC)
        spec["input"]["path"] = "https://example.invalid/data.csv"
        self.write_spec(spec)
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.network_forbidden")

    def test_outside_allowlist_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.csv").write_text("sample,x,y\nS,1,2\n", encoding="utf-8")
        case_dir = self.root / "nested"
        case_dir.mkdir()
        spec = copy.deepcopy(SPEC)
        spec["input"]["path"] = str(outside / "secret.csv")
        (case_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        (case_dir / "case.json").write_text(json.dumps(CASE), encoding="utf-8")
        process = subprocess.run([sys.executable, "-I", str(CLI), "--spec", str(case_dir / "spec.json"),
                                  "--case", str(case_dir / "case.json"), "--out", str(self.out)],
                                 capture_output=True, text=True, timeout=30)
        result = json.loads((self.out / "result.json").read_text(encoding="utf-8"))
        self.assert_refusal(process, result, "input.path_outside_allowlist")

    def test_input_output_overlap_refused(self):
        self.out.mkdir()
        (self.out / "data.csv").write_text("sample,x,y\nS,1,2\n", encoding="utf-8")
        spec = copy.deepcopy(SPEC)
        spec["input"]["path"] = str(self.out / "data.csv")
        self.write_spec(spec)
        process, result = self.invoke()
        self.assert_refusal(process, result, "input.output_overlap")

    def test_oversize_input_refused(self):
        (self.root / "data.csv").write_text("sample,x,y\n" + "S,1,2\n" * 100, encoding="utf-8")
        process, result = self.invoke(extra=("--max-input-bytes", "100"))
        self.assert_refusal(process, result, "input.too_large")

    def test_bad_contract_type_blocks_without_traceback(self):
        case = copy.deepcopy(CASE)
        case["output_contract"] = 42
        self.write_case(case)
        process, result = self.invoke()
        self.assertEqual(process.returncode, 4)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("contract.invalid", {f["rule"] for f in result["findings"]})

    def test_contract_list_wrong_entry_degrades(self):
        case = copy.deepcopy(CASE)
        case["output_contract"] = ["status", "case_payload", 42]
        self.write_case(case)
        process, result = self.invoke()
        self.assertEqual(process.returncode, 0)
        self.assertTrue(any("output_contract[2]" in x for x in result["limits"]))

    def test_idempotent_rerun_same_bytes_and_exit(self):
        first_process, _ = self.invoke()
        first = (self.out / "result.json").read_bytes()
        first_analysis = (self.out / "analysis.json").read_bytes()
        second_process, _ = self.invoke()
        self.assertEqual(first_process.returncode, second_process.returncode)
        self.assertEqual(first, (self.out / "result.json").read_bytes())
        self.assertEqual(first_analysis, (self.out / "analysis.json").read_bytes())
        self.assertFalse((self.out / ".scicode-stdout.tmp").exists())

    def test_caller_credentials_not_in_environment_or_result(self):
        secret = "DO-NOT-FORWARD-7319"
        with mock.patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": secret, "HTTP_PROXY": "http://proxy.invalid"}):
            process, result = self.invoke()
        self.assertEqual(process.returncode, 0)
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))


class GeneratorAndRunner(unittest.TestCase):
    def test_read_only_sql_validation(self):
        for query in ("DELETE FROM t", "PRAGMA table_info(t)", "SELECT 1; SELECT 2",
                      "WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE t",
                      "SELECT load_extension('x')"):
            with self.subTest(query=query):
                spec = copy.deepcopy(SPEC)
                spec["input"] = {"path": "x.db", "format": "sqlite", "query": query}
                with self.assertRaises(codegen.SpecError):
                    codegen.normalize_spec(spec)

    def test_generator_deterministic_and_static_audit(self):
        first, _ = codegen.generate_code(SPEC, resolved_input="data.csv")
        reordered = dict(reversed(list(SPEC.items())))
        second, _ = codegen.generate_code(reordered, resolved_input="data.csv")
        self.assertEqual(first, second)
        self.assertTrue(codegen.audit_generated_code(first))
        with self.assertRaises(codegen.SpecError):
            codegen.audit_generated_code("import os\n")
        with self.assertRaises(codegen.SpecError):
            codegen.audit_generated_code("eval('1+1')\n")

    def test_sanitized_environment_drops_secrets(self):
        with mock.patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "x", "PLAYGROUND_TOKEN": "y",
                                          "HTTP_PROXY": "http://proxy", "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}):
            env = runner._sanitized_environment()
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertNotIn("PLAYGROUND_TOKEN", env)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(env["PYTHONHASHSEED"], "0")

    def test_timeout_kills_generated_style_child(self):
        with tempfile.TemporaryDirectory(prefix="scicode-timeout-") as temporary:
            root = Path(temporary)
            code = root / "analysis.py"
            code.write_text("while True:\n    pass\n", encoding="utf-8")
            result = runner.execute_generated(code, root, timeout=1, max_output_chars=100)
            self.assertTrue(result["timed_out"])
            self.assertFalse(result["executed"])
            self.assertTrue((root / "execution-log.json").is_file())

    def test_stdout_capture_limit(self):
        with tempfile.TemporaryDirectory(prefix="scicode-output-cap-") as temporary:
            root = Path(temporary)
            code = root / "analysis.py"
            code.write_text("print('x' * 10000)\n", encoding="utf-8")
            result = runner.execute_generated(code, root, timeout=5, max_output_chars=100)
            self.assertTrue(result["executed"])
            self.assertTrue(result["stdout_truncated"])
            self.assertLessEqual(len(result["stdout"]), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
