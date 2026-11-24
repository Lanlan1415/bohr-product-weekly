#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py -- offline self-test for the latex-build-doctor scripts.

Covers (no TeX engine required for tests 1-3 and 5-7):
  1. parse_log: built-in sample log snippet -> at least 3 different error
     root-cause categories, warnings classified, rerun flag detected
  2. static_check: detects the planted environment mismatch AND the unbalanced
     $ math, plus the tabular column mismatch
  3. repro_record: generates a JSON record with the required keys from a
     sample log + a fabricated build report
  4. detect_tex: real probe of this machine; BOTH exit 0 (engines present) and
     exit 3 (none present) are legal outcomes -- the result is recorded
     honestly either way
  5. build_loop aux hashing: same labels -> same hash, changed labels -> new hash
  6. build_loop convergence rule on fabricated aux/log files
  7. build_loop import surface (functions used by tests exist)

Usage:
    python -I selftest.py [-v]

Exit codes: 0 = all tests passed; 1 = at least one failure (details printed).
"""
import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

SAMPLE_LOG = r"""This is pdfTeX, Version 4.23 (MiKTeX 25.12) (preloaded format=pdflatex.fmt)
entering extended mode
(./sample.tex
(C:/texmf/tex/latex/base/article.cls
Document Class: article 2019/12/05 v1.4k Standard LaTeX document class
)
(C:/texmf/tex/latex/geometry/geometry.sty
Package: geometry 2020/01/02 v5.9 Page geometry
) (./sample.aux)
./sample.tex:12: Undefined control sequence.
l.12 ...boxed{\mybadmacro{x}}
                             
./sample.tex:15: LaTeX Error: \begin{itemize} on input line 5 ended by \end{enumerate}.
                                                
l.15 ...\end{enumerate}
./sample.tex:20: Missing $ inserted.
<inserted text> 
                $
l.20 ...x = 3 plus more text
[1{C:/texmf/fonts/type1/public/amsfonts/cm/cmr10.pfb}] (./sample.aux) )
Package natbib Warning: Citation `smith2020' on page 1 undefined on input li
ne 40.
LaTeX Warning: Reference `fig:demo' on page 1 undefined on input line 22.
LaTeX Warning: There were undefined references.
Overfull \hbox (12.3pt too wide) in paragraph at lines 30--32
[]
LaTeX Warning: Label `eq:x' multiply defined.
Package rerunfilecheck Warning: File `sample.out' has changed.
(Rerun to get outlines right)
"""

SAMPLE_TEX = r"""\documentclass{article}
\begin{document}
See Figure~\ref{fig:demo} and Eq $x^2$ plus $y_1 math.
\begin{itemize}
\item a
\end{enumerate}
\begin{tabular}{ll}
a & b & c \\
d & e \\
\end{tabular}
\end{document}
"""

ROUND_REPORT_SAMPLE = {
    "main": "sample.tex",
    "driver": "manual",
    "engine": "pdflatex",
    "passes": [
        {"index": 1, "kind": "engine", "tool": "pdflatex",
         "args": ["pdflatex", "-interaction=nonstopmode", "-file-line-error", "sample.tex"],
         "exit_code": 0, "seconds": 1.2, "timed_out": False},
        {"index": 2, "kind": "bib", "tool": "bibtex",
         "args": ["bibtex", "sample"], "exit_code": 0, "seconds": 0.3,
         "timed_out": False},
        {"index": 3, "kind": "engine", "tool": "pdflatex",
         "args": ["pdflatex", "-interaction=nonstopmode", "-file-line-error", "sample.tex"],
         "exit_code": 0, "seconds": 1.0, "timed_out": False},
    ],
    "rounds_engine": 3,
    "converged": True,
    "convergence_rule": "strict: exit=0, aux label hash stable across last 2 rounds, no rerun warnings",
    "status": "success",
    "pdf_path": None,
    "time_budget_seconds": 900,
    "elapsed_seconds": 2.5,
    "time_budget_exceeded": False,
}


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s%s" % (name, (" :: " + detail) if detail else ""))
        FAILURES.append(name)


def write_temp(dirname, name, content):
    path = os.path.join(dirname, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return path


def test_parse_log(tmp):
    import parse_log
    log_path = write_temp(tmp, "sample.log", SAMPLE_LOG)
    report = parse_log.parse_log_file(log_path)
    errs = report["errors"]
    warns = report["warnings"]
    err_cats = {e["category"] for e in errs}
    warn_cats = {w["category"] for w in warns}
    check("parse_log: >=3 error categories",
          len(err_cats) >= 3,
          "got %s" % sorted(err_cats))
    check("parse_log: undefined_control_sequence found",
          "undefined_control_sequence" in err_cats, str(sorted(err_cats)))
    check("parse_log: math_mode_error found",
          "math_mode_error" in err_cats, str(sorted(err_cats)))
    check("parse_log: environment_mismatch found",
          "environment_mismatch" in err_cats, str(sorted(err_cats)))
    check("parse_log: undefined_reference warning",
          "undefined_reference" in warn_cats, str(sorted(warn_cats)))
    check("parse_log: undefined_citation warning (wrapped line merged)",
          "undefined_citation" in warn_cats, str(sorted(warn_cats)))
    check("parse_log: overfull_box warning",
          "overfull_box" in warn_cats, str(sorted(warn_cats)))
    check("parse_log: multiply_defined_label warning",
          "multiply_defined_label" in warn_cats, str(sorted(warn_cats)))
    check("parse_log: rerun_needed detected",
          report["summary"]["rerun_needed"] is True)
    check("parse_log: error line numbers extracted",
          any(e.get("line") == 12 for e in errs),
          json.dumps([(e["category"], e.get("line")) for e in errs]))
    check("parse_log: error file attributed",
          any((e.get("file") or "").endswith("sample.tex") for e in errs),
          json.dumps([e.get("file") for e in errs]))
    # blg parsing
    blg = write_temp(tmp, "sample.blg",
                     "Warning----empty journal in Sample2020\n"
                     "I was expecting a `,' or a `}'---line 12 of file refs.bib\n")
    report2 = parse_log.parse_log_file(log_path, blg_path=blg)
    blg_cats = {i["category"] for i in report2["errors"] + report2["warnings"]}
    check("parse_log: .blg bibliography_problem items",
          "bibliography_problem" in blg_cats, str(sorted(blg_cats)))
    return report


def test_static_check(tmp):
    import static_check
    tex_path = write_temp(tmp, "sample.tex", SAMPLE_TEX)
    with open(tex_path, "rb") as fh:
        raw = fh.read()
    clean = static_check.preprocess(SAMPLE_TEX)
    issues = []
    issues.extend(static_check.scan_envs(clean))
    issues.extend(static_check.scan_braces(clean))
    issues.extend(static_check.scan_math(clean))
    checks = {i["check"] for i in issues}
    check("static_check: environment mismatch detected",
          "env_mismatch" in checks, str(sorted(checks)))
    check("static_check: unbalanced $ detected",
          "math_dollar_unbalanced" in checks, str(sorted(checks)))
    # full-file run for the table + ref checks
    report = static_check.main([tex_path])
    # main() prints; re-run the logic to capture issues instead:
    doc_scope = {"cite_sources": []}
    all_issues, _ = static_check.check_file(tex_path, doc_scope)
    got = {i["check"] for i in all_issues}
    check("static_check: ref_undefined detected (\\ref{fig:demo} has no \\label)",
          "ref_undefined" in got, str(sorted(got)))
    check("static_check: tabular column mismatch detected",
          "table_column_mismatch" in got, str(sorted(got)))
    check("static_check: env mismatch via check_file",
          any(i["check"] == "env_mismatch" for i in all_issues))
    check("static_check: math unbalanced via check_file",
          any(i["check"].startswith("math_") for i in all_issues))
    check("static_check: exit code stays 0 without --fail-on-error",
          report == 0)
    return all_issues


def test_repro_record(tmp):
    import repro_record
    tex_path = write_temp(tmp, "sample.tex", SAMPLE_TEX)
    log_path = write_temp(tmp, "sample.log", SAMPLE_LOG)
    rounds_path = write_temp(tmp, "rounds.json",
                             json.dumps(ROUND_REPORT_SAMPLE))
    record = repro_record.build_record(
        main_tex=tex_path, log_path=log_path, rounds_path=rounds_path,
        workdir=tmp)
    required = ["template", "tool", "packages", "fonts", "commands", "rounds",
                "inputs", "pdf", "generated_at", "notes"]
    missing = [k for k in required if k not in record]
    check("repro_record: all required keys present", not missing,
          "missing: %s" % missing)
    check("repro_record: template class extracted from log",
          record["template"].get("class") == "article",
          json.dumps(record["template"]))
    check("repro_record: package version extracted (geometry)",
          any(p["name"] == "geometry" for p in (record["packages"] or [])),
          json.dumps(record["packages"]))
    check("repro_record: font file extracted from log",
          any("cmr10.pfb" in f for f in (record["fonts"] or [])),
          json.dumps(record["fonts"]))
    check("repro_record: command sequence captured",
          isinstance(record["commands"], list) and len(record["commands"]) == 3)
    check("repro_record: input hash computed",
          any(i.get("sha256") for i in record["inputs"]))
    check("repro_record: rounds info carried",
          record["rounds"] and record["rounds"]["converged"] is True)
    return record


def test_detect_tex(tmp):
    out_path = os.path.join(tmp, "detect.json")
    cp = subprocess.run(
        [sys.executable, "-I", os.path.join(SCRIPT_DIR, "detect_tex.py"),
         "--out", out_path],
        capture_output=True, timeout=120)
    rc = cp.returncode
    check("detect_tex: exit code is 0 or 3", rc in (0, 3), "rc=%d" % rc)
    try:
        with open(out_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        check("detect_tex: JSON report readable", False, str(exc))
        return
    check("detect_tex: JSON has status and tools",
          data.get("status") in ("ok", "no_tex") and isinstance(data.get("tools"), dict))
    if rc == 0:
        check("detect_tex: honest engine list (>=1 engine)",
              len(data.get("engines_available", [])) >= 1)
        print("      detect_tex found engines: %s" % data.get("engines_available"))
    else:
        check("detect_tex: no_tex case provides install hints",
              len(data.get("install_hints", [])) > 0)
        print("      detect_tex found NO TeX engine (recorded honestly)")


def test_build_loop_units(tmp):
    import build_loop
    aux1 = write_temp(tmp, "a1.aux",
                      "\\relax\n\\newlabel{eq:x}{{1}{1}}\n"
                      "\\newlabel{fig:demo}{{1}{2}}\n"
                      "\\@input{child.aux}\n")
    write_temp(tmp, "child.aux", "\\newlabel{tab:one}{{2}{3}}\n")
    aux2 = write_temp(tmp, "a2.aux",
                      "\\relax\n\\newlabel{eq:x}{{1}{1}}\n"
                      "\\newlabel{fig:demo}{{1}{2}}\n"
                      "\\@input{child.aux}\n")
    write_temp(tmp, "child2.aux", "\\newlabel{tab:one}{{2}{3}}\n")
    h1 = build_loop.aux_label_hash(aux1)
    h2 = build_loop.aux_label_hash(aux2)
    check("build_loop: identical aux tree -> identical hash", h1 == h2,
          "%s vs %s" % (h1, h2))
    aux3 = write_temp(tmp, "a3.aux",
                      "\\relax\n\\newlabel{eq:x}{{1}{1}}\n"
                      "\\newlabel{fig:demo}{{1}{3}}\n"
                      "\\@input{child.aux}\n")
    h3 = build_loop.aux_label_hash(aux3)
    check("build_loop: changed page number -> different hash", h3 != h1)
    # convergence rule on fabricated files
    work = os.path.join(tmp, "conv")
    os.makedirs(work, exist_ok=True)
    write_temp(work, "conv.aux",
               "\\relax\n\\newlabel{eq:x}{{1}{1}}\n")
    log = write_temp(work, "conv.log",
                     "This is pdfTeX, Version 4.23\n(no rerun warnings here)\n")
    rep = build_loop.run_build(
        os.path.join(work, "conv.tex"), driver="manual", engine="pdflatex",
        workdir=work, max_rounds=2, time_budget=120,
        miktex_installer="none", keep_logs=work)
    # engine binary will fail (no real compile) -- the loop must record that
    # honestly instead of claiming convergence
    check("build_loop: fabricated run reports failure honestly",
          rep["status"] in ("failed", "partial", "time_budget_exceeded"),
          json.dumps({"status": rep.get("status"),
                      "converged": rep.get("converged")}))
    check("build_loop: passes recorded with exit codes",
          isinstance(rep["passes"], list) and len(rep["passes"]) >= 1
          and "exit_code" in rep["passes"][0])
    check("build_loop: rerun marker scan works (negative case)",
          build_loop.log_has_rerun(log) is False)
    log2 = write_temp(work, "conv2.log",
                      "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.\n")
    check("build_loop: rerun marker scan works (positive case)",
          build_loop.log_has_rerun(log2) is True)
    return rep


def test_import_surface():
    names = ["detect_tex", "build_loop", "parse_log", "static_check", "repro_record"]
    ok = True
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:
            ok = False
            check("import: %s" % name, False, str(exc))
    if ok:
        check("import: all 5 scripts import cleanly", True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run offline self-tests for latex-build-doctor.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    tmp = tempfile.mkdtemp(prefix="latex_doctor_selftest_")
    print("selftest workdir: %s" % tmp)
    test_import_surface()
    test_parse_log(tmp)
    test_static_check(tmp)
    test_repro_record(tmp)
    test_detect_tex(tmp)
    test_build_loop_units(tmp)
    print("")
    if FAILURES:
        print("SELFTEST RESULT: %d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("SELFTEST RESULT: ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
