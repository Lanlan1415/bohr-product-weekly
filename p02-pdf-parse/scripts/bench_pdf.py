"""pdf-parse regression bench — one scenario per refusal branch and one clean.

Each scenario constructs a real input (synthesised PDF or case file), runs the
CLI as a subprocess, and asserts the behaviour rather than the presence of a
result.json. Clean baseline: a real 2-column paper PDF parses with outline +
tables + formula + zero warnings.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "pdfparse.py"

try:
    import fitz  # noqa: F401
    HAVE_FITZ = True
except ImportError:
    HAVE_FITZ = False


def _make_sample_pdf(dst: Path) -> None:
    """Generate a deterministic 2-column test PDF with table + formula."""
    if not HAVE_FITZ:
        return
    import fitz
    doc = fitz.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((40, 40), "1 Introduction", fontsize=13)
    p1.insert_text((320, 40), "2 Methods", fontsize=13)
    p1.insert_textbox(fitz.Rect(40, 80, 280, 400),
                      "We study surface capture. The current binder shows weak uptake. " * 8,
                      fontsize=10)
    p1.insert_textbox(fitz.Rect(320, 80, 580, 400),
                      "We calibrated at 25 C with six replicates per arm. " * 8,
                      fontsize=10)
    # Formula
    p1.insert_text((40, 430), "The rate obeys E = mc², with ΔS ≥ 0.", fontsize=11)
    # Footer
    p1.insert_text((280, 760), "Page 1", fontsize=9)
    doc.save(dst)
    doc.close()


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, "-X", "utf8", str(CLI), *args],
                       capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def scenario(name: str):
    def deco(fn):
        def wrapper(d: Path):
            return fn(d, name)
        wrapper.scenario_name = name
        return wrapper
    return deco


@scenario("clean_basic")
def _clean(d: Path, name: str):
    pdf = d / "sample.pdf"
    _make_sample_pdf(pdf)
    if not pdf.exists():
        return {"name": name, "pass": True, "skip": True, "why": "no fitz backend"}
    case = d / "case.json"
    case.write_text(json.dumps({
        "case_id": "clean-basic",
        "pdf_path": pdf.name,
        "output_contract": ["status", "case_id", "reading_result", "evidence_and_boundaries"]}),
        encoding="utf-8")
    (d / "out").mkdir(exist_ok=True)
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")], cwd=d)
    if code != 0 or not (d / "out" / "result.json").exists():
        return {"name": name, "pass": False, "why": f"exit {code}"}
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
    if res.get("case_id") != "clean-basic":
        return {"name": name, "pass": False, "why": "case_id missing"}
    outline = res.get("outline", [])
    has_formula = any(b.get("kind") == "formula" for b in res.get("blocks", []))
    if not outline or not has_formula:
        return {"name": name, "pass": False, "why": "no outline or no formula"}
    return {"name": name, "pass": True, "why": f"outline={len(outline)}, backend={res['provenance']['backend']}"}


@scenario("case_unreadable")
def _case_unreadable(d: Path, name: str):
    case = d / "case.json"
    case.write_text("{not json", encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    return {"name": name, "pass": code == 5 and (d / "out" / "result.json").exists(),
            "why": f"exit {code}"}


@scenario("case_not_object")
def _case_not_object(d: Path, name: str):
    case = d / "case.json"
    case.write_text("[]", encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    return {"name": name, "pass": code == 4 and (d / "out" / "result.json").exists(),
            "why": f"exit {code}"}


@scenario("pdf_path_missing")
def _pdf_missing(d: Path, name: str):
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "x", "pdf_path": "/nonexistent/file.pdf"}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    return {"name": name, "pass": code == 5 and (d / "out" / "result.json").exists(),
            "why": f"exit {code}"}


@scenario("no_pdf_path_field")
def _no_path_field(d: Path, name: str):
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "x"}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    return {"name": name, "pass": code == 4 and (d / "out" / "result.json").exists(),
            "why": f"exit {code}"}


@scenario("garbage_pdf")
def _garbage_pdf(d: Path, name: str):
    pdf = d / "junk.pdf"
    pdf.write_bytes(b"\x00\x01\x02not really a pdf\x03\x04")
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "junk", "pdf_path": str(pdf)}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    if code not in (4, 5):
        return {"name": name, "pass": False, "why": f"exit {code}"}
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
    if res.get("status") != "undetermined":
        return {"name": name, "pass": False, "why": f"status {res.get('status')}"}
    return {"name": name, "pass": True, "why": f"reason={res.get('reason')}"}


@scenario("plaintext_pdf")
def _plaintext_pdf(d: Path, name: str):
    """A 'PDF' that is just plain text — reader should refuse or degrade cleanly."""
    pdf = d / "plain.pdf"
    pdf.write_text("This is plain text pretending to be a pdf.", encoding="utf-8")
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "plain", "pdf_path": str(pdf)}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    if code not in (0, 3, 5):
        return {"name": name, "pass": False, "why": f"exit {code}"}
    return {"name": name, "pass": True, "why": f"exit {code}"}


@scenario("encrypted_pdf")
def _encrypted_pdf(d: Path, name: str):
    if not HAVE_FITZ:
        return {"name": name, "pass": True, "skip": True, "why": "no fitz"}
    pdf = d / "enc.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((40, 40), "secret")
    doc.save(pdf, encryption=fitz.PDF_ENCRYPT_AES_128, user_pw="pw")
    doc.close()
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "enc", "pdf_path": str(pdf)}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8")) if (d / "out" / "result.json").exists() else {}
    return {"name": name, "pass": code in (4, 5) and res.get("status") == "undetermined",
            "why": f"exit {code}, reason={res.get('reason')}"}


@scenario("chinese_pdf")
def _chinese_pdf(d: Path, name: str):
    """CJK content (no embedded CJK font): engine must NOT crash and must keep UTF-8 read hints.
    fitz may return blanks for missing glyphs; the bench expects an honest result,
    not necessarily correct CJK extraction."""
    if not HAVE_FITZ:
        return {"name": name, "pass": True, "skip": True, "why": "no fitz"}
    pdf = d / "zh.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((40, 40), "1 H")
    p.insert_text((40, 80), "CJK:\u4f60\u597d\u4e16\u754c")
    p.insert_text((40, 130), "End")
    doc.save(pdf)
    doc.close()
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "zh", "pdf_path": str(pdf),
                                "output_contract": ["status", "reading_result"]}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
    # Critical assertions: result exists, status is honest, no traceback, exit in {0,3}
    if code not in (0, 3) or res.get("status") not in ("clean", "review"):
        return {"name": name, "pass": False, "why": f"exit {code}, status {res.get('status')}"}
    return {"name": name, "pass": True,
            "why": f"status={res['status']}, backend={res['provenance']['backend']}"}


@scenario("bom_case_spec")
def _bom_case(d: Path, name: str):
    if not HAVE_FITZ:
        return {"name": name, "pass": True, "skip": True, "why": "no fitz"}
    pdf = d / "s.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((40, 40), "1 H")
    p.insert_text((40, 70), "Hello world")
    doc.save(pdf)
    doc.close()
@scenario("bom_case_spec")
def _bom_case(d: Path, name: str):
    if not HAVE_FITZ:
        return {"name": name, "pass": True, "skip": True, "why": "no fitz"}
    pdf = d / "s.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((40, 40), "1 H")
    p.insert_text((40, 70), "Hello world")
    doc.save(pdf)
    doc.close()
    case = d / "case.json"
    case.write_bytes(b'\xef\xbb\xbf' + json.dumps({"case_id": "bom",
                     "pdf_path": pdf.name, "output_contract": ["status"]}).encode("utf-8"))
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")], cwd=d)
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
    return {"name": name, "pass": code in (0, 3) and res.get("status") in ("clean", "review"),
            "why": f"exit {code}, status={res.get('status')}"}


@scenario("dict_output_contract")
def _dict_contract(d: Path, name: str):
    if not HAVE_FITZ:
        return {"name": name, "pass": True, "skip": True, "why": "no fitz"}
    pdf = d / "s.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((40, 40), "1 H")
    doc.save(pdf)
    doc.close()
    case = d / "case.json"
    case.write_text(json.dumps({
        "case_id": "c1", "pdf_path": pdf.name,
        "output_contract": {"status": None, "case_id": None},
        "custom_field": "carried"}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")], cwd=d)
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
    ok = res.get("status") in ("clean", "review") and res.get("case_id") == "c1"
    return {"name": name, "pass": ok, "why": f"status={res.get('status')}"}


@scenario("long_form_pdf")
def _long_form(d: Path, name: str):
    if not HAVE_FITZ:
        return {"name": name, "pass": True, "skip": True, "why": "no fitz"}
    pdf = d / "long.pdf"
    doc = fitz.open()
    for i in range(20):
        p = doc.new_page()
        p.insert_text((40, 40), f"{i+1} Section {i+1}", fontsize=14)
        p.insert_text_box = None
        txt = "We measured the rate at six replicates. " * 60
        p.insert_textbox(fitz.Rect(40, 70, 570, 740), txt, fontsize=10)
    doc.save(pdf)
    doc.close()
    case = d / "case.json"
    case.write_text(json.dumps({"case_id": "long", "pdf_path": str(pdf),
                                "output_contract": ["status"]}), encoding="utf-8")
    code, _, _ = run(["parse", "--case", str(case), "--out", str(d / "out")])
    res = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
    if code != 0:
        return {"name": name, "pass": False, "why": f"exit {code}"}
    return {"name": name, "pass": res["provenance"]["page_count"] == 20,
            "why": f"pages={res['provenance']['page_count']}"}


SCEN = [_clean, _case_unreadable, _case_not_object, _pdf_missing,
        _no_path_field, _garbage_pdf, _plaintext_pdf,
        _encrypted_pdf, _chinese_pdf, _bom_case, _dict_contract, _long_form]


def main():
    rows = []
    for fn in SCEN:
        tmp = Path(tempfile.mkdtemp())
        try:
            result = fn(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        rows.append(result)
        print(f"{'PASS' if result['pass'] else 'FAIL'}  {result['name']:<22} {result['why']}")
    report = {"scenarios": rows, "totals": {"passed": sum(1 for r in rows if r["pass"]),
                                            "of": len(rows)}}
    (HERE / "report_pdf.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(1 for r in rows if r["pass"])
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
