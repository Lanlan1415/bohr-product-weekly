#!/usr/bin/env python3
"""Case-to-artifact entry point for latex-build-doctor (standard library only).

The agent edits a real LaTeX project first; this command then audits/builds the
actual files.  It never invents an engine, PDF, package version or convergence.

  python -I texcase.py --case case.json --project build/ --out output/
  python -I texcase.py --case case.json --project build/ --out output/ --static-only

Exit codes: 0 strict build success; 3 partial (including no TeX/static-only);
4 build or static errors; 5 structured refusal.  Every path writes result.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import detect_tex  # noqa: E402
import repro_record  # noqa: E402

SOURCE_EXTS = {
    ".tex", ".bib", ".cls", ".sty", ".bst", ".bbx", ".cbx", ".lbx", ".def",
    ".clo", ".fd", ".cfg", ".tikz", ".txt", ".md", ".csv", ".png", ".jpg",
    ".jpeg", ".pdf", ".eps", ".dat", ".json", ".ltx",
}
SKIP_DIRS = {".git", "__pycache__", "round_logs", "preview"}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def case_identifier(case) -> object:
    if not isinstance(case, dict):
        return None
    for key in ("case_id", "id", "caseId"):
        if key in case:
            return case.get(key)
    return None


def find_output_contract(case):
    if isinstance(case, dict):
        if "output_contract" in case:
            return case["output_contract"]
        for value in case.values():
            found = find_output_contract(value)
            if found is not None:
                return found
    elif isinstance(case, list):
        for value in case:
            found = find_output_contract(value)
            if found is not None:
                return found
    return None


def contract_fields(contract) -> tuple[list[str], list[str]]:
    """Return every exact declared field name and any schema limitations."""
    if contract is None:
        return [], []
    if isinstance(contract, dict):
        return [str(k) for k in contract], []
    if isinstance(contract, list):
        bad = [x for x in contract if not isinstance(x, str) or not x.strip()]
        limits = ["non-string output_contract entries cannot be echoed as field names"] if bad else []
        return [x for x in contract if isinstance(x, str) and x.strip()], limits
    return [], ["output_contract is neither an object nor a field-name list; its fields are unknown"]


def skeleton(case) -> dict:
    fields, limits = contract_fields(find_output_contract(case))
    result = {
        "schema_version": "texcase/v1", "case_id": case_identifier(case),
        "skill": "latex-build-doctor", "status": "partial",
        "compilation_attempted": False, "pdf_generated": False,
        "deliverable": {"main_tex": None, "source_dir": None, "pdf": None, "preview": []},
        "evidence_map": [], "boundary": {"limits": list(limits), "uncertainty": []},
        "limits": list(limits), "uncertainty": [],
        "build": {"engine": None, "driver": None, "rounds": 0, "converged": None},
    }
    for key in fields:
        if key not in result:
            if isinstance(contract := find_output_contract(case), dict) and key in contract:
                result[key] = mirror_unknown(contract[key], key, result["limits"])
            else:
                result[key] = None
                result["limits"].append(f"output_contract field '{key}' awaits derivation")
    return result


def refuse(out: Path, case, message: str, code: int = 5) -> int:
    result = skeleton(case)
    result["status"] = "refused"
    result["boundary"] = {"limits": [message], "uncertainty": [message],
                           "human_review": ["inspect the input and structured finding"]}
    result["findings"] = [{"rule": "texcase.refused", "severity": "high",
                           "message": message, "exit_code": code}]
    result["limits"] = list(result.get("limits") or []) + [message]
    result["uncertainty"] = [message]
    # An unparseable case cannot reveal its contract. The standard keys still remain.
    write_json(out / "result.json", result)
    print(json.dumps({"status": "refused", "wrote": str(out / "result.json"),
                      "finding": "texcase.refused"}, ensure_ascii=False))
    return code


def locate_main(project: Path, requested: str | None) -> Path | None:
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = project / candidate
        return candidate.resolve() if candidate.is_file() else None
    candidates = []
    for path in sorted(project.rglob("*.tex")):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\\documentclass" in text:
            candidates.append(path)
    if len(candidates) == 1:
        return candidates[0].resolve()
    # Deterministic convention for a multi-root project: an explicitly named main.
    for name in ("main.tex", "paper.tex", "manuscript.tex"):
        for path in candidates:
            if path.name.lower() == name:
                return path.resolve()
    return None


def sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def source_files(project: Path, main: Path) -> list[dict]:
    main_pdf = main.with_suffix(".pdf").resolve()
    files = []
    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # The generated main PDF is output, never a reproducibility input.
        if path.resolve() == main_pdf:
            continue
        files.append({"path": path.relative_to(project).as_posix(),
                      "sha256": sha256(path), "bytes": path.stat().st_size})
    return files


def deliver_sources(project: Path, main: Path, out: Path, sources: list[dict]) -> None:
    src_dir = out / "src"
    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True, exist_ok=True)
    for record in sources:
        rel = Path(record["path"])
        source = project / rel
        target = src_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if source.resolve() == main.resolve():
            shutil.copyfile(source, out / "main.tex")


def changes_from(path: str | None) -> list:
    if not path:
        return []
    try:
        data = read_json(Path(path))
    except (OSError, ValueError, UnicodeError):
        return []
    return data if isinstance(data, list) else []


def run_builder(main: Path, project: Path, out: Path, args) -> tuple[dict, int]:
    cmd = [sys.executable, "-I", str(SCRIPTS / "build_loop.py"), str(main),
           "--dir", str(project), "--engine", args.engine,
           "--max-rounds", str(args.max_rounds), "--time-budget", str(args.time_budget),
           "--report", str(out / "build_report.json"),
           "--keep-logs", str(out / "round_logs"), "--miktex-installer", "none"]
    if not args.no_preview:
        cmd += ["--make-preview", str(out / "preview")]
    proc = subprocess.run(cmd, cwd=str(project), capture_output=True, timeout=args.time_budget + 30)
    (out / "build.stdout.log").write_bytes((proc.stdout or b"") + (proc.stderr or b""))
    try:
        report = read_json(out / "build_report.json")
    except (OSError, ValueError, UnicodeError):
        report = {"status": "cannot_determine", "compilation_attempted": False,
                  "pdf_generated": False, "converged": False, "passes": [],
                  "error": "builder returned no readable report"}
    report["wrapper_exit_code"] = proc.returncode
    write_json(out / "build_report.json", report)
    return report, proc.returncode


def mirror_unknown(template, path: str, limits: list[str]):
    """Preserve nested contract keys without inventing a scalar or its type."""
    if isinstance(template, dict):
        return {str(k): mirror_unknown(v, f"{path}.{k}" if path else str(k), limits)
                for k, v in template.items()}
    if isinstance(template, list):
        # An array in a contract is a shape constraint, not a synthetic result.
        if path:
            limits.append(f"nested output_contract array '{path}' has no generated items")
        return []
    if path:
        limits.append(f"nested output_contract field '{path}' is not derivable; left null")
    return None


def apply_contract(result: dict, case: dict) -> None:
    """Directly mirror all fields, including every nested output_contract key."""
    contract = find_output_contract(case)
    fields, schema_limits = contract_fields(contract)
    summary = {}
    known = {
        "case_id": result.get("case_id"), "status": result.get("status"),
        "main_tex": "main.tex", "tex": "main.tex", "source": "src/",
        "sources": result.get("source_manifest", []),
        "source_files": result.get("source_manifest", []),
        "pdf": result.get("deliverable", {}).get("pdf"),
        "deliverable": result.get("deliverable"),
        "build": result.get("build"), "build_report": "build_report.json",
        "static_report": "static_report.json", "log_report": "log_report.json",
        "repro_record": "repro_record.json", "changes": result.get("changes", []),
        "evidence": result.get("evidence_map", []), "evidence_map": result.get("evidence_map", []),
        "findings": result.get("findings", []), "errors": result.get("errors", []),
        "warnings": result.get("warnings", []), "limits": result.get("limits", []),
        "uncertainty": result.get("uncertainty", []),
        "converged": result.get("build", {}).get("converged"),
        "engine": result.get("build", {}).get("engine"),
    }
    results = dict(result)
    nested_limits = []
    for key in fields:
        lookup = key.lower()
        if key in case and key not in ("status", "case_id"):
            value = case[key]  # exact passthrough when the case owns a concrete field
        elif key in known:
            value = known[key]
        elif lookup in known:
            value = known[lookup]
        elif isinstance(contract, dict) and key in contract:
            value = mirror_unknown(contract[key], key, nested_limits)
        elif key in result and result[key] is not None:
            value = result[key]
        else:
            value = None
        summary[key] = value
        results[key] = value
        if value is None:
            nested_limits.append(
                f"output_contract field '{key}' was not derivable; left null for human completion")
    results.setdefault("limits", []).extend(nested_limits)
    for note in schema_limits:
        results.setdefault("limits", []).append(note)
    results["output_contract"] = summary
    # Stable de-duplication keeps idempotence without changing any declaration.
    results["limits"] = list(dict.fromkeys(str(x) for x in results.get("limits", [])))
    result.clear()
    result.update(results)


def execute(args) -> int:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        case = read_json(Path(args.case))
    except (OSError, ValueError, UnicodeError) as exc:
        return refuse(out, {}, f"case.json is not readable JSON: {exc}")
    if not isinstance(case, dict):
        return refuse(out, case, "case.json must contain a JSON object")

    # Save the contract-preserving partial before doing any expensive work.
    write_json(out / "result.json", skeleton(case))
    project = Path(args.project).resolve()
    if not project.is_dir():
        return refuse(out, case, f"project directory does not exist: {project}")
    main = locate_main(project, args.main)
    if main is None:
        return refuse(out, case, "no unique main .tex containing \\documentclass was found; "
                                 "supply --main or repair the project")
    if project not in main.parents:
        return refuse(out, case, "--main must be a file inside --project")

    for name in ("main.pdf", "main.tex", "build_report.json", "static_report.json",
                 "log_report.json", "repro_record.json", "build.stdout.log"):
        try:
            (out / name).unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            return refuse(out, case, f"cannot clear stale output {name}: {exc}")
    for name in ("preview", "round_logs"):
        if (out / name).exists():
            shutil.rmtree(out / name)

    # Static source validation runs regardless of engine availability.
    static_proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS / "static_check.py"), "--dir", str(project),
         "--out", str(out / "static_report.json")], capture_output=True, timeout=120)
    (out / "static.stdout.log").write_bytes((static_proc.stdout or b"") + (static_proc.stderr or b""))
    try:
        static = read_json(out / "static_report.json")
    except (OSError, ValueError, UnicodeError):
        static = {"issues": [], "summary": {"by_severity": {"error": 1}},
                  "error": "static checker returned no readable report"}
        write_json(out / "static_report.json", static)

    tools, engines, drivers = detect_tex.probe_all(timeout=10)
    environment = {
        "status": "ok" if engines else "no_tex",
        "engines_available": sorted(engines), "drivers_available": sorted(drivers), "tools": tools,
        "engine_policy": args.engine, "network_install": False,
        "host_python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    write_json(out / "environment.json", environment)

    limits = []
    if args.static_only or not engines:
        reason = ("static-only was explicitly requested" if args.static_only
                  else "no TeX engine is available; compilation was NOT executed")
        build = {"status": "not_compiled", "driver": None, "engine": None, "passes": [],
                 "rounds_engine": 0, "converged": None, "compilation_attempted": False,
                 "pdf_generated": False, "pdf_path": None, "convergence_rule": None,
                 "honest_note": reason}
        builder_code = 2
        limits.append(reason + "; static checks are not a substitute for compilation")
    else:
        build, builder_code = run_builder(main, project, out, args)
        if not build.get("compilation_attempted"):
            limits.append("no compilation was executed; see build_report.json")
    write_json(out / "build_report.json", build)

    log_path = main.with_suffix(".log")
    if log_path.is_file():
        log_proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPTS / "parse_log.py"), str(log_path),
             "--blg", "auto", "--out", str(out / "log_report.json")],
            capture_output=True, timeout=120)
        (out / "logparse.stdout.log").write_bytes((log_proc.stdout or b"") + (log_proc.stderr or b""))
    if not (out / "log_report.json").exists():
        write_json(out / "log_report.json", {
            "errors": [], "warnings": [], "summary": {"error_count": 0, "warning_count": 0},
            "limits": ["no compiler log exists; log diagnostics were not performed"]})

    # Copy the real PDF only if this run's report points at an existing file.
    pdf_delivered = None
    reported_pdf = build.get("pdf_path")
    if reported_pdf and Path(reported_pdf).is_file() and build.get("compilation_attempted"):
        shutil.copyfile(reported_pdf, out / "main.pdf")
        pdf_delivered = "main.pdf"
    elif (out / "main.pdf").exists():
        (out / "main.pdf").unlink()

    sources = source_files(project, main)
    deliver_sources(project, main, out, sources)
    repro = repro_record.build_record(
        str(main), str(log_path) if log_path.is_file() else None,
        str(out / "build_report.json"), str(project))
    # A stochastic runtime measurement is not used as a semantic finding.
    repro["environment_record"] = "environment.json"
    repro["source_manifest"] = sources
    write_json(out / "repro_record.json", repro)

    log_report = read_json(out / "log_report.json")
    errors = log_report.get("errors") or []
    warnings = log_report.get("warnings") or []
    issues = [x for x in static.get("issues", []) if isinstance(x, dict)]
    static_errors = [x for x in issues if x.get("severity") == "error"]
    strict_success = bool(build.get("compilation_attempted") and build.get("converged") is True
                          and pdf_delivered and not static_errors and not errors)
    status = "success" if strict_success else "partial"
    changes = changes_from(args.changes)
    previews = sorted(p.name for p in (out / "preview").glob("*.png")) if (out / "preview").exists() else []
    uncertainty = list(limits)
    if static_errors:
        uncertainty.append(f"{len(static_errors)} static source error(s) remain")
    if errors:
        uncertainty.append(f"{len(errors)} compiler log error(s) remain")
    if build.get("converged") is not True:
        uncertainty.append("strict convergence was not proved; PDF existence alone is not accepted")

    result = skeleton(case)
    result.update({
        "status": status, "section": "latex_build",
        "compilation_attempted": bool(build.get("compilation_attempted")),
        "pdf_generated": bool(pdf_delivered),
        "deliverable": {"main_tex": "main.tex" if (out / "main.tex").exists() else None,
                        "source_dir": "src/", "pdf": pdf_delivered, "preview": previews,
                        "source_file_count": len(sources)},
        "build": {"driver": build.get("driver"), "engine": build.get("engine"),
                  "rounds": build.get("rounds_engine", len(build.get("passes") or [])),
                  "converged": build.get("converged"),
                  "convergence_rule": build.get("convergence_rule"),
                  "status": build.get("status"),
                  "fls_present": any(p.get("fls_present") for p in build.get("passes") or []),
                  "log_blockers": build.get("log_blockers")},
        "source_manifest": sources, "changes": changes,
        "evidence_map": [
            {"kind": "source_inputs", "locator": "repro_record.json#source_manifest", "count": len(sources)},
            {"kind": "static_source_checks", "locator": "static_report.json#issues",
             "errors": len(static_errors), "issues": len(issues)},
            {"kind": "compile_rounds", "locator": "build_report.json#passes",
             "attempted": bool(build.get("compilation_attempted"))},
            {"kind": "root_cause_localization", "locator": "log_report.json#errors",
             "errors": len(errors), "warnings": len(warnings)},
            {"kind": "reproducibility", "locator": "repro_record.json#tool",
             "packages": "repro_record.json#packages", "fonts": "repro_record.json#fonts"},
        ],
        "static_summary": static.get("summary", {}), "errors": errors, "warnings": warnings,
        "findings": issues + errors + warnings + ([
            {"rule": "texcase.not_converged", "severity": "high",
             "message": "strict compile convergence was not proved"}] if build.get("converged") is not True else []),
        "limits": list(dict.fromkeys(result.get("limits", []) + limits)),
        "uncertainty": list(dict.fromkeys(uncertainty)),
        "boundary": {"limits": list(dict.fromkeys(limits)),
                     "uncertainty": list(dict.fromkeys(uncertainty)),
                     "changes": changes,
                     "human_review": ["resolve high-severity findings before accepting a partial result"]},
    })
    if not pdf_delivered:
        result["limits"].append("no PDF was delivered by this run; do not describe it as compiled")
    result["limits"] = list(dict.fromkeys(result["limits"]))
    apply_contract(result, case)
    write_json(out / "result.json", result)
    print(json.dumps({"status": status, "case_id": result.get("case_id"),
                      "wrote": str(out / "result.json"), "pdf": pdf_delivered,
                      "converged": build.get("converged"),
                      "engine": build.get("engine")}, ensure_ascii=False))
    if strict_success:
        return 0
    if static_errors or errors or (build.get("compilation_attempted") and builder_code not in (0, 2)):
        return 4
    return 3


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="actual case.json, never a prepared answer")
    parser.add_argument("--project", required=True, help="real, editable LaTeX project directory")
    parser.add_argument("--main", help="main .tex relative to project (otherwise detect)")
    parser.add_argument("--out", required=True, help="deliverable directory")
    parser.add_argument("--changes", help="optional JSON list of real source edits")
    parser.add_argument("--engine", default="auto",
                        choices=["auto", "latexmk", "pdflatex", "xelatex", "lualatex", "tectonic"])
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--time-budget", type=float, default=360.0)
    parser.add_argument("--static-only", action="store_true",
                        help="exercise static fallback explicitly; never claims compilation")
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args(argv)
    if args.max_rounds < 2 or args.max_rounds > 20 or args.time_budget <= 0:
        return refuse(Path(args.out).resolve(), {},
                      "--max-rounds must be 2..20 and --time-budget must be positive")
    try:
        return execute(args)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as exc:
        try:
            case = read_json(Path(args.case))
        except Exception:
            case = {}
        return refuse(Path(args.out).resolve(), case,
                      f"pipeline could not complete: {exc.__class__.__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
