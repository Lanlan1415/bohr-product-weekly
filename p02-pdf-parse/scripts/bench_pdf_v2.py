"""pdf-parse v2 real-backend behavioural regression.

The main fixture is a generated three-page scientific PDF with two columns,
metadata, native merged table geometry, an image, Unicode math and references.
It is synthetic input for testing, not a prepared official answer.
"""
from __future__ import annotations

import base64
import copy
import json
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "pdfparse.py"
try:
    import pymupdf as fitz
    HAVE = True
except ImportError:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import fitz
        HAVE = True
    except ImportError:
        HAVE = False

SCENARIOS = []
PNG_1PX = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def scenario(name):
    def decorate(fn):
        fn.scenario_name = name
        SCENARIOS.append(fn)
        return fn
    return decorate


def make_paper(path: Path):
    doc = fitz.open()
    doc.set_metadata({"title": "A Synthetic Multi-column Study", "author": "Alice Example; Bob Example",
                      "subject": "Parser regression", "keywords": "PDF, tables, reading order"})
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((52, 48), "A Synthetic Multi-column Study", fontsize=18)
    p1.insert_text((170, 72), "Alice Example; Bob Example", fontsize=10)
    p1.insert_text((70, 92), "Example University, Department of Methods", fontsize=9)
    p1.insert_text((52, 122), "Abstract", fontsize=13)
    p1.insert_textbox(fitz.Rect(52, 135, 560, 182),
                      "We evaluate extraction quality using a controlled synthetic document with explicit source coordinates. " * 2,
                      fontsize=10)
    p1.insert_text((42, 214), "1 Introduction", fontsize=13)
    p1.insert_textbox(fitz.Rect(42, 230, 285, 410),
                      "Reading order must remain within a column before moving to the next column. " * 7, fontsize=10)
    p1.insert_text((320, 214), "2 Methods", fontsize=13)
    p1.insert_text((320, 238), "2.1 Recruitment", fontsize=12)
    p1.insert_textbox(fitz.Rect(320, 252, 570, 420),
                      "Participants were assigned to two synthetic arms and every measurement was retained. " * 6, fontsize=10)
    p1.insert_text((42, 446), "E = mc² and ΔS ≥ 0 (1)", fontsize=11)
    rect = fitz.Rect(45, 485, 205, 565)
    p1.insert_image(rect, stream=PNG_1PX)
    p1.insert_text((42, 582), "Figure 1. Synthetic source image.", fontsize=9)
    p1.insert_text((285, 760), "Page 1", fontsize=8)

    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((285, 24), "Page 2", fontsize=8)
    p2.insert_text((60, 58), "Table 1. Outcomes by synthetic arm", fontsize=9)
    x0, x1, x2, x3, x4 = 60, 222, 386, 550, 550
    ys = [76, 104, 132, 160]
    for y in ys:
        p2.draw_line((x0, y), (x3, y), width=0.7)
    p2.draw_line((x0, ys[0]), (x0, ys[-1]), width=0.7)
    p2.draw_line((x3, ys[0]), (x3, ys[-1]), width=0.7)
    for x in (x1, x2):
        p2.draw_line((x, ys[1]), (x, ys[-1]), width=0.7)
    p2.insert_text((218, 94), "Combined outcomes", fontsize=9)
    for x, text in ((70, "Arm"), (232, "Before"), (396, "After")):
        p2.insert_text((x, 121), text, fontsize=9)
    for x, text in ((70, "A"), (232, "1.0"), (396, "2.0")):
        p2.insert_text((x, 149), text, fontsize=9)
    p2.insert_text((42, 210), "3 Results", fontsize=13)
    p2.insert_textbox(fitz.Rect(42, 226, 285, 405),
                      "The parsed values remain associated with their native table cells and page coordinates. " * 6, fontsize=10)
    p2.insert_text((320, 210), "4 Discussion", fontsize=13)
    p2.insert_textbox(fitz.Rect(320, 226, 570, 405),
                      "Structural extraction does not interpret the scientific meaning of a table or formula. " * 6, fontsize=10)
    p2.insert_text((285, 760), "Page 2", fontsize=8)

    p3 = doc.new_page(width=612, height=792)
    p3.insert_text((285, 24), "Page 3", fontsize=8)
    p3.insert_text((42, 62), "References", fontsize=13)
    p3.insert_textbox(fitz.Rect(42, 82, 565, 190),
                      "[1] Example A. Source-anchored parsing. doi:10.1000/example.1\n"
                      "[2] Example B. Conservative table extraction. Synthetic Journal 2025.", fontsize=9)
    p3.insert_text((42, 730), "* Synthetic fixture note; no official case content.", fontsize=7)
    p3.insert_text((285, 760), "Page 3", fontsize=8)
    doc.save(path)
    doc.close()


def run(root: Path, case: dict, pdf_name="paper.pdf", repeat_out=None):
    case_path = root / "case.json"
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = repeat_out or root / "out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "parse", "--case", str(case_path),
                           "--out", str(out)], capture_output=True, text=True, timeout=240)
    result_path = out / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return proc, result, out


def paper_case():
    return {"case_id": "rich-v2", "section": "pdf_parse", "pdf_path": "paper.pdf",
            "output_contract": ["case_id", "status", "reading_result", "evidence_and_boundaries", "运行状态"]}


def result_row(result, block_id):
    return next(b for b in result["blocks"] if b["block_id"] == block_id)


@scenario("rich_scientific_pdf_clean_and_complete")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    make_paper(root / "paper.pdf")
    proc, r, out = run(root, paper_case())
    if proc.returncode != 0:
        return False, f"exit {proc.returncode}, findings={r.get('findings')}"
    titles = [x["title"] for x in r["outline_flat"]]
    checks = [r["metadata"]["title"] == "A Synthetic Multi-column Study",
              "1 Introduction" in titles, "2.1 Recruitment" in titles, "References" in titles,
              len(r["tables"]) == 1, len(r["formulas"]) >= 1, len(r["references"]) == 2,
              len(r["captions"]) == 2, bool(r["tables"][0]["cells"]),
              (out / "full_text.txt").exists(), (out / "document.md").exists(),
              "Page 1" not in (out / "full_text.txt").read_text(encoding="utf-8")]
    return all(checks), f"outline={len(titles)}, tables={len(r['tables'])}, formulas={len(r['formulas'])}, refs={len(r['references'])}"


@scenario("native_merged_table_cell_geometry")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    make_paper(root / "paper.pdf")
    _, r, _ = run(root, paper_case())
    table = r["tables"][0]
    texts = [c["text"] for c in table["cells"]]
    return any(value and "Combined" in value for value in texts) and "Before" in texts \
        and any(c.get("covered_by") or (c.get("colspan") or 1) > 1 or (c.get("rowspan") or 1) > 1 for c in table["cells"]) \
        and bool(table["merged_regions"]), f"merged={len(table['merged_regions'])}, cells={len(texts)}"


@scenario("column_order_and_verbatim_locators")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    make_paper(root / "paper.pdf")
    _, r, out = run(root, paper_case())
    body = (out / "full_text.txt").read_text(encoding="utf-8")
    order_ok = body.index("1 Introduction") < body.index("Reading order must remain") < body.index("2 Methods") < body.index("Participants were assigned")
    for loc in r["evidence_and_boundaries"]["locators"]:
        b = result_row(r, loc["block_id"])
        if b["text"][loc["char_start"]:loc["char_end"]] != loc["quote"]:
            return False, f"bad slice {loc['block_id']}"
    return order_ok and r["pages"][0]["columns"] == 2, f"columns={r['pages'][0]['columns']}"


@scenario("short_pdf_does_not_fall_back")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    doc = fitz.open(); p = doc.new_page(); p.insert_text((40, 50), "1 Short\nA tiny but valid text layer."); doc.save(root / "paper.pdf"); doc.close()
    proc, r, _ = run(root, paper_case())
    return proc.returncode == 0 and r["provenance"]["backend"] == "pymupdf" and "tiny but valid" in r["blocks"][-1]["text"], \
        f"backend={r.get('provenance', {}).get('backend')}"


@scenario("mixed_scanned_page_is_partial_not_fabricated")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    doc = fitz.open(); p1 = doc.new_page(); p1.insert_text((40, 50), "1 Text page\nThis page has real text.")
    pix = fitz.Pixmap(PNG_1PX)
    p2 = doc.new_page(); p2.insert_image(p2.rect, pixmap=pix)
    doc.save(root / "paper.pdf"); doc.close()
    proc, r, _ = run(root, paper_case())
    return proc.returncode == 3 and r["reading_result"]["scanned_pages"] == [2] \
        and any(b["kind"] == "scanned_page" for b in r["blocks"]) and r["evidence_and_boundaries"]["unverified"], \
        f"exit={proc.returncode}, scanned={r.get('reading_result', {}).get('scanned_pages')}"


@scenario("encrypted_pdf_named_refusal")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    doc = fitz.open(); doc.new_page().insert_text((40, 50), "secret")
    doc.save(root / "paper.pdf", encryption=fitz.PDF_ENCRYPT_AES_128, user_pw="pw"); doc.close()
    proc, r, _ = run(root, paper_case())
    return proc.returncode == 5 and r["status"] == "undetermined" and r["reason"] == "encrypted" and r["case_id"] == "rich-v2", \
        f"exit={proc.returncode}, reason={r.get('reason')}"


@scenario("unknown_section_exit5_full_contract")
def _(root):
    if HAVE:
        make_paper(root / "paper.pdf")
    case = paper_case() | {"section": "figure_parse", "delivery_note": "kept",
                           "output_contract": [{"field": "case_id"}, {"name": "delivery_note"}, {"key": "absent"}]}
    proc, r, _ = run(root, case)
    return proc.returncode == 5 and r["case_id"] == "rich-v2" and r["delivery_note"] == "kept" and r["absent"] is None \
        and r["output_contract_fields"] == ["case_id", "delivery_note", "absent"], f"exit={proc.returncode}"


@scenario("case_not_object_exit4_result")
def _(root):
    path = root / "case.json"; path.write_text("[]", encoding="utf-8")
    out = root / "out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "parse", "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True)
    r = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return proc.returncode == 4 and r["reason"] == "case_not_object" and "Traceback" not in proc.stderr, f"exit={proc.returncode}"


@scenario("missing_pdf_exit5_result")
def _(root):
    proc, r, _ = run(root, paper_case())
    return proc.returncode == 5 and r["reason"] == "pdf_missing" and r["case_id"] == "rich-v2" \
        and r["reading_result"] is None, f"exit={proc.returncode}, reason={r.get('reason')}"


@scenario("no_table_fabricated_from_aligned_prose")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    doc = fitz.open(); p = doc.new_page(width=612, height=792)
    for y in range(80, 300, 35):
        p.insert_text((50, y), "Ordinary left prose without any ruling lines", fontsize=10)
        p.insert_text((250, y), "Separate ordinary right prose is not evidence", fontsize=10)
        p.insert_text((450, y), "of a table", fontsize=10)
    doc.save(root / "paper.pdf"); doc.close()
    proc, r, _ = run(root, paper_case())
    return proc.returncode in (0, 3) and r["tables"] == [] and any("No native table" in x for x in r["limits"]), \
        f"tables={len(r.get('tables', []))}"


@scenario("engine_case_null_contract_priority")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    doc = fitz.open(); doc.new_page().insert_text((40, 50), "1 Short\nText"); doc.save(root / "paper.pdf"); doc.close()
    case = paper_case() | {"status": "forged", "delivery_note": {"kept": True},
                           "output_contract": ["case_id", "status", "delivery_note", "absent"]}
    proc, r, _ = run(root, case)
    return proc.returncode == 3 and r["status"] == "review" and r["delivery_note"] == {"kept": True} \
        and r["absent"] is None and any("absent" in x for x in r["limits"]), f"status={r.get('status')}"


@scenario("deterministic_result_and_artifacts_replay")
def _(root):
    if not HAVE:
        return True, "skip: PyMuPDF unavailable"
    make_paper(root / "paper.pdf")
    p1, _, out1 = run(root, paper_case())
    out2 = root / "second"
    p2, _, _ = run(root, paper_case(), repeat_out=out2)
    names = ["result.json", "full_text.txt", "document.md", "tables.json", "source_pages.json"]
    return p1.returncode == p2.returncode == 0 and all((out1 / n).read_bytes() == (out2 / n).read_bytes() for n in names), \
        "five artifacts byte compared"


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, fn in enumerate(SCENARIOS):
            work = root / str(i); work.mkdir()
            try:
                ok, why = fn(work)
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"scenario": fn.scenario_name, "pass": bool(ok), "why": why})
            print(("PASS" if ok else "FAIL") + f"  {fn.scenario_name:<50}{why}")
    report = {"schema_version": "pdf-parse-bench/v2", "backend_available": HAVE,
              "fixture_notice": "generated synthetic scientific PDF, not official case output",
              "scenarios": rows, "totals": {"passed": sum(x["pass"] for x in rows), "of": len(rows)}}
    (HERE / "report_pdf_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} v2 scenarios pass")
    return 0 if all(x["pass"] for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
