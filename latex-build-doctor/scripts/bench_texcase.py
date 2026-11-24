"""Independent texcase regression suite; use --real for an actual local TeX build.

All cases are synthetic fixtures, not official answers. Artifacts stay in a temp
folder. The default suite needs no TeX; --real additionally compiles a minimal
source project with bibliography, math, figure/table and cross-references.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import build_loop  # noqa: E402

TEX = r"""\documentclass{article}
\usepackage{amsmath}
\title{Reproducible Build Smoke Fixture}
\author{Test Fixture}
\begin{document}
\maketitle
\section{Method}
Figure~\ref{fig:method} and Eq.~\eqref{eq:energy} are resolved, as is \cite{smith2020}.
\begin{figure}[h]\centering\fbox{method schematic}\caption{Method}\label{fig:method}\end{figure}
\begin{equation}E = mc^2\label{eq:energy}\end{equation}
\begin{table}[h]\centering\caption{Measurements}\begin{tabular}{lr}\hline
Sample & Value \\\hline A & 12.5 \\\hline\end{tabular}\end{table}
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""

BIB = r"""@article{smith2020,
  author = {Smith, Alex and Doe, Jordan},
  title = {A Reproducible Synthetic Study},
  journal = {Fixture Journal},
  year = {2020},
  volume = {1},
  pages = {1--2}
}
"""

CASE = {
    "case_id": "synthetic-latex-smoke",
    "title": "pass through this exact title",
    "output_contract": {
        "case_id": "input identifier", "status": "honest status",
        "deliverable": "editable source and actual PDF if built",
        "build_report": "compile rounds", "source_files": "source manifest",
        "changes": "source edit records", "title": "case-owned title",
        "review_note": "non-derivable field must remain null with a limit",
        "review_panel": {"decision": "human decision", "editor_note": "human note"},
    },
}


def run_cli(case_path: Path, project: Path, out: Path, extra=()):
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS / "texcase.py"), "--case", str(case_path),
         "--project", str(project), "--out", str(out), *extra],
        capture_output=True, text=True, timeout=500)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return proc, result


def make_project(root: Path, text=TEX):
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.tex").write_text(text, encoding="utf-8")
    (root / "refs.bib").write_text(BIB, encoding="utf-8")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="execute a real TeX compiler if available")
    args = parser.parse_args(argv)
    rows = []

    def check(name, ok, detail=""):
        rows.append({"scenario": name, "pass": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<36} {detail}")

    with tempfile.TemporaryDirectory(prefix="texcase_bench_") as td:
        tmp = Path(td)
        case_path = tmp / "case.json"
        case_path.write_text(json.dumps(CASE, ensure_ascii=False), encoding="utf-8")

        # Cold isolated import, including direct module dependency imports.
        cold = subprocess.run(
            [sys.executable, "-I", "-c",
             "import importlib.util; p=" + repr(str(SCRIPTS / 'texcase.py')) +
             ";s=importlib.util.spec_from_file_location('cold_texcase',p);"
             "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print('ok')"],
            capture_output=True, text=True, timeout=120)
        check("cold_isolated_import", cold.returncode == 0 and "ok" in cold.stdout,
              cold.stderr.strip()[:160])

        # Static no-engine simulation and three-part deliverable/contract.
        project = tmp / "clean"
        make_project(project)
        out = tmp / "out_static"
        proc, result = run_cli(case_path, project, out, ("--static-only",))
        check("static_partial_no_pdf_claim",
              proc.returncode == 3 and result.get("status") == "partial"
              and result.get("compilation_attempted") is False
              and result.get("pdf_generated") is False and not (out / "main.pdf").exists(),
              f"exit={proc.returncode}")
        check("contract_all_fields_direct",
              all(k in result for k in CASE["output_contract"])
              and result.get("title") == CASE["title"]
              and result.get("review_note") is None
              and any("review_note" in x for x in result.get("limits", [])),
              f"keys={sorted(k for k in CASE['output_contract'] if k not in result)}")
        check("nested_contract_shape_preserved",
              set(result.get("review_panel", {})) == {"decision", "editor_note"}
              and result["review_panel"]["decision"] is None
              and any("review_panel.decision" in x for x in result.get("limits", [])))
        check("real_editable_source_and_reports",
              (out / "main.tex").is_file() and (out / "src" / "refs.bib").is_file()
              and (out / "static_report.json").is_file()
              and (out / "repro_record.json").is_file()
              and (out / "log_report.json").is_file())

        # Same input and same output directory, no timestamps -> byte identical.
        first_bytes = (out / "result.json").read_bytes()
        proc2, result2 = run_cli(case_path, project, out, ("--static-only",))
        check("static_rerun_byte_identical",
              proc2.returncode == 3 and (out / "result.json").read_bytes() == first_bytes)
        check("stale_pdf_removed_on_static_rerun",
              not (out / "main.pdf").exists() and result2.get("pdf_generated") is False)

        # Broken references and malformed environment become source-localized findings.
        broken = tmp / "broken"
        make_project(broken, TEX.replace("Figure~\\ref{fig:method}", "Figure~\\ref{fig:missing}")
                     .replace("\\end{document}", "\\begin{itemize}\\item x\\end{enumerate}\\end{document}"))
        proc_bad, bad = run_cli(case_path, broken, tmp / "out_broken", ("--static-only",))
        checks = {x.get("check") for x in (bad.get("static_summary") and
                  json.loads((tmp / "out_broken" / "static_report.json").read_text(encoding="utf-8")).get("issues", []))}
        check("hostile_static_localizes_defects",
              proc_bad.returncode == 4 and "ref_undefined" in checks and "env_mismatch" in checks
              and "Traceback" not in proc_bad.stderr, f"checks={sorted(checks)}")

        # Repaired twin must be clean on the invariant path (no false-positive pass trick).
        repaired = tmp / "repaired"
        make_project(repaired)
        proc_ok, ok = run_cli(case_path, repaired, tmp / "out_repaired", ("--static-only",))
        check("repaired_twin_no_static_error",
              proc_ok.returncode == 3 and not ok.get("errors")
              and all(x.get("severity") != "error" for x in ok.get("findings", []) if isinstance(x, dict)))

        # Bad JSON, non-object case, missing project and missing main all structured refuse.
        bad_json = tmp / "bad.json"
        bad_json.write_text("{ not json", encoding="utf-8")
        p, r = run_cli(bad_json, project, tmp / "out_bad_json")
        check("refusal_malformed_json", p.returncode == 5 and r.get("status") == "refused"
              and "case_id" in r and "Traceback" not in p.stderr)
        non_object = tmp / "list.json"
        non_object.write_text("[]", encoding="utf-8")
        p, r = run_cli(non_object, project, tmp / "out_non_object")
        check("refusal_non_object_case", p.returncode == 5 and r.get("status") == "refused")
        p, r = run_cli(case_path, tmp / "missing_project", tmp / "out_missing_project")
        check("refusal_missing_project_keeps_contract",
              p.returncode == 5 and r.get("case_id") == CASE["case_id"]
              and all(k in r for k in CASE["output_contract"]))
        empty = tmp / "empty"
        empty.mkdir()
        p, r = run_cli(case_path, empty, tmp / "out_empty")
        check("refusal_no_main", p.returncode == 5 and r.get("status") == "refused")

        # Malformed option values also refuse without a traceback.
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "texcase.py"),
                            "--case", str(case_path), "--project", str(project),
                            "--out", str(tmp / "out_bad_options"), "--max-rounds", "1"],
                           capture_output=True, text=True, timeout=120)
        check("refusal_invalid_round_budget", p.returncode == 5 and "Traceback" not in p.stderr)

        # Unit probes for citations and convergence blockers, not just newlabel.
        check("log_blockers_unresolved_citation",
              build_loop.log_blockers(tmp / "none.log") is None)
        blocker_log = tmp / "blocker.log"
        blocker_log.write_text("LaTeX Warning: Citation `missing' on page 1 undefined on input line 8.\n",
                               encoding="utf-8")
        check("log_blockers_catches_unresolved", bool(build_loop.log_blockers(blocker_log)))
        aux = tmp / "state.aux"
        aux.write_text("\\newlabel{eq:x}{{1}{1}}\n\\citation{smith2020}\n", encoding="utf-8")
        h1 = build_loop.build_state_hash(aux, tmp, "state")
        (tmp / "state.bbl").write_text("\\bibitem{smith2020} Smith.", encoding="utf-8")
        h2 = build_loop.build_state_hash(aux, tmp, "state")
        check("state_hash_tracks_bibliography", h1 != h2)
        unicode_project = tmp / "unicode.tex"
        unicode_project.write_text("\\documentclass{ctexart}", encoding="utf-8")
        old_which = shutil.which
        try:
            build_loop.shutil.which = lambda name: ("/bin/" + name) if name in ("xelatex", "latexmk") else None
            driver, engine = build_loop.choose_engine(unicode_project, "auto")
            check("auto_engine_respects_cjk", driver == "latexmk" and engine == "xelatex",
                  f"{driver}/{engine}")
        finally:
            build_loop.shutil.which = old_which
        latexmk_cmd = build_loop.build_engine_cmd("latexmk", "xelatex", "main.tex", "none")
        check("latexmk_dependency_flags",
              "-xelatex" in latexmk_cmd and "-recorder" in latexmk_cmd and "-bibtex" in latexmk_cmd
              and "-file-line-error" in latexmk_cmd)

        # A chapter is not an independent document; its labels are project-wide.
        multi = tmp / "multi"
        (multi / "sections").mkdir(parents=True)
        (multi / "main.tex").write_text(
            "\\documentclass{article}\\usepackage{amsmath}\\begin{document}\n"
            "\\input{sections/method} See \\eqref{eq:child}.\n\\end{document}\n", encoding="utf-8")
        (multi / "sections" / "method.tex").write_text(
            "\\begin{equation}x=y+1\\label{eq:child}\\end{equation}\n", encoding="utf-8")
        p_multi, r_multi = run_cli(case_path, multi, tmp / "out_multi", ("--static-only",))
        check("multifile_cross_reference_clean",
              p_multi.returncode == 3
              and all(x.get("severity") != "error" for x in r_multi.get("findings", [])
                      if isinstance(x, dict) and not str(x.get("rule", "")).startswith("texcase."))
              and (tmp / "out_multi" / "src" / "sections" / "method.tex").is_file())

        if args.real:
            real_project = tmp / "real"
            make_project(real_project)
            real_out = tmp / "out_real"
            proc_real, real = run_cli(case_path, real_project, real_out,
                                      ("--engine", "pdflatex", "--time-budget", "240",
                                       "--max-rounds", "6", "--no-preview"))
            report_path = real_out / "build_report.json"
            build = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            if not build.get("passes"):
                check("real_tex_compiler_discovered", False,
                      "no engine passes; use the static suite on machines without TeX")
            else:
                check("real_tex_compiler_discovered", True,
                      f"{build.get('engine')} rounds={build.get('rounds_engine')}")
                pdf_ok = (real_out / "main.pdf").read_bytes()[:4] == b"%PDF" if (real_out / "main.pdf").exists() else False
                check("real_source_strict_compile",
                      proc_real.returncode == 0 and real.get("status") == "success"
                      and build.get("converged") is True and pdf_ok,
                      f"exit={proc_real.returncode} status={real.get('status')} converged={build.get('converged')}")
                check("real_environment_and_repro_record",
                      (real_out / "environment.json").is_file()
                      and any(p.get("fls_present") for p in build.get("passes", []))
                      and (real_out / "repro_record.json").is_file())
                check("real_log_diagnostics_and_source_hash",
                      (real_out / "log_report.json").is_file()
                      and all(x.get("sha256") for x in real.get("source_manifest", []))
                      and not any(x.get("path") == "main.pdf" for x in real.get("source_manifest", [])))
                repro = json.loads((real_out / "repro_record.json").read_text(encoding="utf-8"))
                check("real_template_packages_fonts_recorded",
                      bool(repro.get("template")) and repro.get("packages") is not None
                      and repro.get("commands") and repro.get("generated_at") is None)

                # A real error must be localized, then a real edit must restore a
                # strictly converged build in the same output directory.
                original_tex = (real_project / "main.tex").read_text(encoding="utf-8")
                (real_project / "main.tex").write_text(
                    original_tex.replace("\\section{Method}", "\\section{Method}\n\\badbuildmacro"),
                    encoding="utf-8")
                proc_error, error_result = run_cli(
                    case_path, real_project, real_out,
                    ("--engine", "pdflatex", "--time-budget", "240", "--max-rounds", "4", "--no-preview"))
                error_log = json.loads((real_out / "log_report.json").read_text(encoding="utf-8"))
                error_items = error_log.get("errors") or []
                check("real_compile_error_line_localization",
                      proc_error.returncode == 4 and error_result.get("status") == "partial"
                      and any(e.get("line") for e in error_items)
                      and any(e.get("category") == "undefined_control_sequence" for e in error_items)
                      and error_result.get("build", {}).get("converged") is not True,
                      f"errors={len(error_items)}")
                (real_project / "main.tex").write_text(original_tex, encoding="utf-8")
                proc_fixed, fixed = run_cli(
                    case_path, real_project, real_out,
                    ("--engine", "pdflatex", "--time-budget", "240", "--max-rounds", "6", "--no-preview"))
                fixed_build = json.loads((real_out / "build_report.json").read_text(encoding="utf-8"))
                fixed_log = json.loads((real_out / "log_report.json").read_text(encoding="utf-8"))
                check("real_repair_recompile_converges",
                      proc_fixed.returncode == 0 and fixed.get("status") == "success"
                      and fixed_build.get("converged") is True and not fixed_log.get("errors"))

    report = {"schema_version": "texcase-bench/v1", "real_compile_requested": bool(args.real),
              "fixtures_are_synthetic": True, "scenarios": rows,
              "totals": {"passed": sum(r["pass"] for r in rows), "of": len(rows)}}
    (SCRIPTS / "report_texcase.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} pass")
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
