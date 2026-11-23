"""Black-box hostile probes for the real pdf-parse v2 CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench_pdf_v2 as fixture  # noqa: E402

CLI = HERE / "pdfparse.py"
HAVE = fixture.HAVE
fitz = fixture.fitz if HAVE else None
PROBES = []
MISSING = object()


def probe(name, expected, needs_pdf=True):
    def decorate(fn):
        PROBES.append((name, expected, needs_pdf, fn))
        return fn
    return decorate


def simple_pdf(path: Path, text="1 Short\nA small valid PDF text layer."):
    doc = fitz.open(); doc.new_page().insert_text((40, 50), text); doc.save(path); doc.close()


def basic(**kw):
    case = {"case_id": "pdf-hostile", "section": "parse", "pdf_path": "paper.pdf",
            "output_contract": ["case_id", "status", "reading_result", "evidence_and_boundaries"]}
    case.update(kw)
    return case


def invoke(tmp: Path, case=MISSING, raw=None, missing_case=False):
    path = tmp / "case.json"
    if not missing_case:
        if raw is not None:
            path.write_bytes(raw if isinstance(raw, bytes) else str(raw).encode("utf-8"))
        else:
            path.write_text(json.dumps(basic() if case is MISSING else case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "parse", "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True, timeout=240)
    try:
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        parseable = True
    except Exception:
        result, parseable = {}, False
    return {"proc": proc, "result": result, "out": out, "parseable": parseable,
            "trace_free": "Traceback" not in proc.stdout + proc.stderr}


@probe("clean_pdf", 0)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    return invoke(tmp), lambda r, o: r["case_id"] == "pdf-hostile" and r["provenance"]["backend"] == "pymupdf"


@probe("case_missing", 5, False)
def _(tmp):
    return invoke(tmp, missing_case=True), lambda r, o: r["reason"].startswith("case_unreadable")


@probe("case_bad_json", 5, False)
def _(tmp):
    return invoke(tmp, raw="{bad"), lambda r, o: r["reason"].startswith("case_unreadable")


@probe("case_not_object_exit4", 4, False)
def _(tmp):
    return invoke(tmp, raw="[]"), lambda r, o: r["reason"] == "case_not_object"


@probe("no_pdf_path_exit4", 4, False)
def _(tmp):
    c = basic(); c.pop("pdf_path")
    return invoke(tmp, c), lambda r, o: r["reason"] == "no_pdf_path"


@probe("wrong_pdf_path_type_exit4", 4)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    return invoke(tmp, basic(pdf_path=7)), lambda r, o: r["reason"] == "no_pdf_path"


@probe("missing_pdf_exit5_contract", 5, False)
def _(tmp):
    return invoke(tmp), lambda r, o: r["reason"] == "pdf_missing" and r["case_id"] == "pdf-hostile" \
        and all(k in r for k in ("reading_result", "evidence_and_boundaries"))


@probe("unknown_section_exit5_contract", 5)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    c = basic(section="figure_parse", delivery_note="kept", output_contract=["case_id", "delivery_note", "absent"])
    return invoke(tmp, c), lambda r, o: r["case_id"] == "pdf-hostile" and r["delivery_note"] == "kept" and r["absent"] is None


@probe("garbage_pdf_exit5", 5)
def _(tmp):
    (tmp / "paper.pdf").write_bytes(b"not a PDF")
    return invoke(tmp), lambda r, o: r["status"] == "undetermined" and r["reason"] == "all_backends_failed"


@probe("directory_instead_of_pdf_exit5", 5)
def _(tmp):
    (tmp / "paper.pdf").mkdir()
    return invoke(tmp), lambda r, o: r["reason"] == "pdf_missing"


@probe("fully_scanned_refusal_not_ocr_fiction", 5)
def _(tmp):
    doc = fitz.open(); pix = fitz.Pixmap(fixture.PNG_1PX); p = doc.new_page(); p.insert_image(p.rect, pixmap=pix)
    doc.save(tmp / "paper.pdf"); doc.close()
    return invoke(tmp), lambda r, o: r["reason"] == "scanned_only" and r["reading_result"] is None


@probe("encrypted_named_refusal", 5)
def _(tmp):
    doc = fitz.open(); doc.new_page().insert_text((40, 50), "secret")
    doc.save(tmp / "paper.pdf", encryption=fitz.PDF_ENCRYPT_AES_128, user_pw="pw"); doc.close()
    return invoke(tmp), lambda r, o: r["reason"] == "encrypted"


@probe("mixed_scan_partial_review", 3)
def _(tmp):
    doc = fitz.open(); doc.new_page().insert_text((40, 50), "1 Text\nReal text")
    pix = fitz.Pixmap(fixture.PNG_1PX); p = doc.new_page(); p.insert_image(p.rect, pixmap=pix)
    doc.save(tmp / "paper.pdf"); doc.close()
    return invoke(tmp), lambda r, o: r["reading_result"]["scanned_pages"] == [2] and r["evidence_and_boundaries"]["unverified"]


@probe("bom_case", 0)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    raw = b"\xef\xbb\xbf" + json.dumps(basic()).encode("utf-8")
    return invoke(tmp, raw=raw), lambda r, o: r["case_id"] == "pdf-hostile"


@probe("nested_materials_pdf", 0)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    c = basic(materials=[{"name": "paper", "path": "paper.pdf"}]); c.pop("pdf_path")
    return invoke(tmp, c), lambda r, o: r["status"] == "clean"


@probe("sole_pdf_autodiscovery_review", 3)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    c = basic(); c.pop("pdf_path")
    return invoke(tmp, c), lambda r, o: any(x["rule"] == "pdf.input_autodiscovery" for x in r["findings"])


@probe("multiple_pdfs_primary_only_review", 3)
def _(tmp):
    simple_pdf(tmp / "a.pdf", "1 Primary\nPRIMARY-TEXT")
    simple_pdf(tmp / "b.pdf", "1 Secondary\nSECOND-PDF-SECRET")
    c = basic(pdf_path=None, materials=["a.pdf", "b.pdf"]); c.pop("pdf_path")
    row = invoke(tmp, c)
    blob = (row["out"] / "result.json").read_text(encoding="utf-8")
    return row, lambda r, o: "PRIMARY-TEXT" in blob and "SECOND-PDF-SECRET" not in blob \
        and any(x["rule"] == "pdf.multiple_pdf_candidates" for x in r["findings"])


@probe("native_tables_disabled_no_fake_grid", 0)
def _(tmp):
    fixture.make_paper(tmp / "paper.pdf")
    return invoke(tmp, basic(native_tables=False)), lambda r, o: r["tables"] == [] and len(r["outline_flat"]) >= 5


@probe("contract_bad_shape_no_crash", 0)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    return invoke(tmp, basic(output_contract=7)), lambda r, o: any("unsupported type" in x for x in r["limits"])


@probe("contract_object_list_complete", 0)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    c = basic(output_contract=[{"field": "case_id"}, {"name": "reading_result"}, {"key": "运行状态"}])
    return invoke(tmp, c), lambda r, o: r["output_contract_fields"] == ["case_id", "reading_result", "运行状态"] \
        and r["运行状态"] == "clean"


@probe("contract_missing_field_review", 3)
def _(tmp):
    simple_pdf(tmp / "paper.pdf")
    return invoke(tmp, basic(output_contract=["case_id", "unavailable"])), \
        lambda r, o: r["unavailable"] is None and r["status"] == "review"


@probe("deterministic_byte_replay", 0)
def _(tmp):
    fixture.make_paper(tmp / "paper.pdf")
    row = invoke(tmp)
    second = tmp / "second"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "parse", "--case", str(tmp / "case.json"),
                           "--out", str(second)], capture_output=True, text=True, timeout=240)
    same = proc.returncode == 0 and (row["out"] / "result.json").read_bytes() == (second / "result.json").read_bytes()
    return row, lambda r, o: same


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, (name, expected, needs_pdf, fn) in enumerate(PROBES):
            tmp = root / str(i); tmp.mkdir()
            if needs_pdf and not HAVE:
                rows.append({"probe": name, "pass": True, "skip": "PyMuPDF unavailable", "expected_exit": expected})
                print(f"PASS  {name:<48}skip: no PyMuPDF")
                continue
            row = None
            try:
                row, checker = fn(tmp)
                proc, result = row["proc"], row["result"]
                extra = bool(checker(result, row["out"]))
                ok = proc.returncode == expected and row["parseable"] and row["trace_free"] and extra
                why = "" if ok else f"exit={proc.returncode} expected={expected}; json={row['parseable']}; trace_free={row['trace_free']}; predicate={extra}; stderr={proc.stderr[-180:]}"
            except Exception as exc:
                proc, result, ok, why = None, {}, False, f"harness {type(exc).__name__}: {exc}"
            rows.append({"probe": name, "expected_exit": expected, "actual_exit": proc.returncode if proc else None,
                         "result_json": bool(result), "traceback_free": row["trace_free"] if row else False,
                         "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<48}" + why)
    report = {"schema_version": "pdf-parse-hostile/v2", "backend_available": HAVE,
              "fixture_notice": "synthetic hostile PDF and case probes only", "probes": rows,
              "totals": {"passed": sum(x["pass"] for x in rows), "of": len(rows)}}
    (HERE / "report_pdf_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} hostile probes pass")
    return 0 if all(x["pass"] for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
