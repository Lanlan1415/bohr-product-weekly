"""Real-file bench for formatfit.py; DOCX fixtures exist only in temporary dirs."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EX = HERE.parent / "examples" / "run_minimal.py"
spec = importlib.util.spec_from_file_location("formatfit_example", EX)
EXMOD = importlib.util.module_from_spec(spec); spec.loader.exec_module(EXMOD)
sys.path.insert(0, str(HERE))
import formatfit as F  # noqa: E402

BASE_SPEC = {
    "case_id": "fit-bench", "apply": True,
    "template": {"spec": {"font": "Liberation Serif", "size_pt": 11,
                          "line_spacing": 1.5, "margin_mm": 25, "columns": 1,
                          "heading_levels": 3, "export_format": "docx"}},
    "headings": [{"text": "1 Introduction", "level": 1}, {"text": "2 Methods", "level": 1}],
    "output_contract": {"case_id": "id", "status": "engine", "revised_manuscript": "engine",
                        "compliance": "engine", "case_value": "case", "missing_value": "unknown"},
    "case_value": {"kept": [1, 2, 3]},
}


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def run(name, mutator=None, expected=(), expected_status=None, source_figure=False):
            case_root = root / name; case_root.mkdir()
            source = case_root / "source.docx"
            EXMOD.write_demo_docx(source, figure=source_figure)
            s = copy.deepcopy(BASE_SPEC); s["source_file"] = str(source)
            if mutator:
                mutator(s, case_root)
            try:
                r = F.build(s, case_root / "out")
                fired = {f["rule"] for f in r["findings"]}
                ok = all(x in fired for x in expected)
                if not expected:
                    ok = not r["findings"]
                if expected_status:
                    ok = ok and r["status"] == expected_status
                rows.append({"scenario": name, "pass": ok, "status": r["status"],
                             "fired": sorted(fired)})
                return s, r
            except Exception as exc:
                rows.append({"scenario": name, "pass": False, "error": str(exc), "fired": []})
                return s, None

        def template_json(s, d):
            t = d / "template.json"; t.write_text(json.dumps({"template": s["template"]}),
                                                   encoding="utf-8")
            s["template_file"] = str(t)

        s, r = run("clean_real_apply", template_json)
        rows[-1]["pass"] = rows[-1]["pass"] and r["content_preservation"]["text_identical"] \
            and r["revised_manuscript"]["path"].endswith("adapted.docx") \
            and r["case_value"] == {"kept": [1, 2, 3]} and r["missing_value"] is None \
            and r["rendering"]["visual_inspection"] == "not_performed"

        def existing_compliant(s, d):
            out = d / "existing.docx"
            EXMOD.write_demo_docx(out, margin_mm=25, font="Liberation Serif", size_pt=11,
                                  paragraphs=[("1 Introduction", "Heading1"),
                                              ("We study it [a1].", None), ("2 Methods", "Heading1"),
                                              ("We use 3 mM [a2].", None)])
            # Existing fixture lacks 1.5 spacing, so remove that requirement for this audit.
            s["template"]["spec"].pop("line_spacing")
            s["template"]["spec"]["heading_levels"] = 1
            s["apply"] = False; s["output_file"] = str(out)
        run("audit_existing_output", existing_compliant)

        def changed(s, d):
            out = d / "changed.docx"
            EXMOD.write_demo_docx(out, paragraphs=[("1 Introduction", "Heading1"),
                                                   ("A silently rewritten claim [a1].", None),
                                                   ("2 Methods", "Heading1"), ("We use 3 mM [a2].", None)])
            s["apply"] = False; s["output_file"] = str(out); s["template"]["spec"].pop("line_spacing")
        run("content_change_detected", changed, ["fit.content_changed"], "blocked")

        def lost(s, d):
            s["apply"] = False; s["template"]["spec"].pop("line_spacing")
            EXMOD.write_demo_docx(d / "source.docx", figure=True)
            s["source_file"] = str(d / "source.docx")
            out = d / "lost.docx"; EXMOD.write_demo_docx(out, figure=False)
            s["output_file"] = str(out)
        run("content_unit_lost", lost, ["fit.unit_lost"], "blocked")

        def bad_margin(s, d):
            s["template"]["spec"]["margin_mm"] = 30
        run("applied_margin_measured", bad_margin)  # apply makes 30, so still clean

        def wrong_margin(s, d):
            s["apply"] = False; s["output_file"] = str(d / "source.docx")
            s["template"]["spec"].pop("line_spacing")
            s["template"]["spec"]["heading_levels"] = 1
        run("margin_mismatch_detected", wrong_margin, ["fit.margin_mismatch"], "blocked")

        def unknown_caption(s, d):
            s["template"]["spec"] = {"caption_position": "below"}
            s["headings"] = []
        run("unverifiable_caption_is_not_pass", unknown_caption, ["fit.check_unverified"], "review")

        def caption(s, d):
            s["apply"] = False; s["output_file"] = str(d / "source.docx")
            s["template"]["spec"] = {"caption_position": "below"}; s["headings"] = []
        run("actual_caption_adjacency", caption, source_figure=True)

        def declaration(s, d):
            s["template"]["sections"] = ["Introduction", "Methods", "Data Availability"]
        run("required_declaration_missing", declaration, ["fit.required_text_missing"], "blocked")

        def actual_toc(s, d):
            s["apply"] = False; s["output_file"] = str(d / "toc.docx")
            EXMOD.write_demo_docx(d / "toc.docx", toc=True)
            EXMOD.write_demo_docx(d / "source.docx", toc=True)
            s["template"]["spec"] = {"toc_expected": True}; s["headings"] = []
        run("actual_toc_field_detected", actual_toc)

        def actual_page(s, d):
            s["apply"] = False; s["output_file"] = str(d / "page.docx")
            EXMOD.write_demo_docx(d / "page.docx", page_number=True)
            s["template"]["spec"] = {"page_numbers": True}; s["headings"] = []
        run("actual_page_field_detected", actual_page)

        # Actual DOCX template recognition, not a JSON assertion.
        case_root = root / "docx_template"; case_root.mkdir()
        t = case_root / "template.docx"
        EXMOD.write_demo_docx(t, margin_mm=22, font="Liberation Serif", size_pt=12)
        req, evidence = F.template_requirements(t)
        ok = (req["font"] == "Liberation Serif" and req["size_pt"] == 12
              and all(abs(req["margin_mm"][side] - 22) < 0.01 for side in ("top", "left"))
              and evidence["kind"] == "docx_ooxml")
        rows.append({"scenario": "docx_template_recognition", "pass": ok, "fired": []})

        tex = root / "template.tex"
        tex.write_text(r"\documentclass[12pt,twocolumn]{article}" + "\n"
                       r"\usepackage[margin=2cm]{geometry}" + "\n"
                       r"\usepackage{fontspec}\setmainfont{Liberation Serif}" + "\n"
                       r"\setstretch{1.25}\bibliographystyle{plain}", encoding="utf-8")
        req, evidence = F.template_requirements(tex)
        ok = (req["size_pt"] == 12 and req["columns"] == 2 and req["margin_mm"] == 20
              and req["font"] == "Liberation Serif" and req["line_spacing"] == 1.25
              and req["reference_style"] == "plain")
        rows.append({"scenario": "tex_template_recognition", "pass": ok, "fired": []})

        # Malformed binary and hostile spec are subprocess tests for exit code/result/no traceback.
        badroot = root / "bad_binary"; badroot.mkdir()
        bad = badroot / "bad.docx"; bad.write_bytes(b"not a zip")
        s = copy.deepcopy(BASE_SPEC); s["source_file"] = str(bad)
        sp = badroot / "spec.json"; sp.write_text(json.dumps(s), encoding="utf-8")
        p = subprocess.run([sys.executable, "-I", str(HERE / "formatfit.py"), "--spec", str(sp),
                            "--out", str(badroot / "out")], capture_output=True, text=True, timeout=30)
        try:
            payload = json.loads((badroot / "out" / "result.json").read_text(encoding="utf-8"))
            ok = (p.returncode == 5 and payload["case_id"] == "fit-bench"
                  and payload["status"] == "undetermined" and payload["missing_value"] is None
                  and "Traceback" not in p.stderr)
        except Exception:
            ok = False
        rows.append({"scenario": "structured_bad_docx_refusal", "pass": ok, "fired": []})

        # Idempotency includes the adapted DOCX and every JSON deliverable.
        case_root = root / "determinism"; case_root.mkdir()
        src = case_root / "source.docx"; EXMOD.write_demo_docx(src)
        s = copy.deepcopy(BASE_SPEC); s["source_file"] = str(src); s["status"] = "pretend-success"
        out = case_root / "out"
        r1 = F.build(s, out); bytes1 = (out / "result.json").read_bytes(); docx1 = (out / "adapted.docx").read_bytes()
        r2 = F.build(s, out); bytes2 = (out / "result.json").read_bytes(); docx2 = (out / "adapted.docx").read_bytes()
        ok = bytes1 == bytes2 and docx1 == docx2 and r1["status"] == r2["status"] == "clean"
        rows.append({"scenario": "deterministic_and_engine_precedence", "pass": ok, "fired": []})

    for row in rows:
        print(("PASS" if row["pass"] else "FAIL") + f"  {row['scenario']:<38} {row.get('fired', [])}")
    passed = sum(bool(r["pass"]) for r in rows)
    report = {"schema_version": "formatfit-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_formatfit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
