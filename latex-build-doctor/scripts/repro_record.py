#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repro_record.py -- generate a reproducible-build record for a LaTeX run.

Collects, from evidence that actually exists (build report, .log, files on
disk), everything another person needs to rebuild the same artifact:

  * tool name/version/path   (re-probed via `--version`, never guessed)
  * document class + loaded packages with versions (extracted from the .log)
  * font files the engine actually loaded (.pfb/.otf/.ttf/.tfm from the .log)
  * exact command sequence and per-round outcome (from a build_loop.py report)
  * sha256 + size of every input source and of the final PDF

Nothing is invented: a missing piece is recorded as null with a note.

Usage:
    python -I repro_record.py --main MAIN.tex --log MAIN.log
        [--rounds rounds.json] [--workdir DIR] [--output repro.json]
        [--max-inputs 400]

Output keys (matches result.json -> result.repro_record):
    template, tool, packages, fonts, commands, rounds, converged,
    inputs, pdf, generated_at, notes
Exit codes: 0 = record produced; 3 = neither main nor log/rounds found.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PACKAGE_RE = re.compile(r"^Package: (\S+) ([0-9/]{4,10})[ ]?(v\S+)?", re.M)
CLASS_RE = re.compile(r"^Document Class: (\S+) ([0-9/]{4,10})[ ]?(v\S+)?", re.M)
FONT_FILE_RE = re.compile(r"[^\s{}()<>]*?\.(?:pfb|otf|ttf|tfm)\b", re.I)

BUILD_EXCLUDE_EXT = {
    ".aux", ".log", ".out", ".toc", ".lof", ".lot", ".bbl", ".blg", ".fls",
    ".fdb_latexmk", ".xdv", ".bcf", ".spl", ".nav", ".snm", ".vrb", ".idx",
    ".ind", ".ilg", ".glo", ".gls", ".acn", ".acr", ".alg", ".glg",
    ".glsdefs", ".listing", ".synctex.gz", ".run.xml",
}
INPUT_EXTS = {".tex", ".bib", ".cls", ".sty", ".bst", ".bbx", ".cbx", ".lbx",
              ".def", ".clo", ".fd", ".cfg", ".tikz", ".txt", ".md", ".csv",
              ".png", ".jpg", ".jpeg", ".pdf", ".eps", ".dat", ".json"}


def sha256_of(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def probe_tool(name):
    path = shutil.which(name)
    if not path:
        return {"name": name, "available": False, "version": None, "path": None}
    try:
        cp = subprocess.run([path, "--version"], capture_output=True, timeout=20)
        raw = (cp.stdout or b"") + (cp.stderr or b"")
        first = ""
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if line.strip():
                first = line.strip()[:200]
                break
        return {"name": name, "available": True, "version": first, "path": path}
    except Exception as exc:
        return {"name": name, "available": False, "version": None, "path": path,
                "error": exc.__class__.__name__}


def extract_packages(log_path):
    """(class_info, packages, fonts) from a .log; None where the log is absent."""
    if not log_path or not os.path.isfile(log_path):
        return None, None, None
    try:
        with open(log_path, "rb") as fh:
            text = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None, None, None
    class_info = None
    cm = CLASS_RE.search(text)
    if cm:
        class_info = {"class": cm.group(1), "date": cm.group(2),
                      "version": cm.group(3) or None}
    packages = []
    seen = set()
    for pm in PACKAGE_RE.finditer(text):
        name = pm.group(1)
        if name in seen:
            continue
        seen.add(name)
        packages.append({"name": name, "date": pm.group(2),
                         "version": pm.group(3) or None})
    fonts = []
    fseen = set()
    for fm in FONT_FILE_RE.finditer(text):
        f = fm.group(0)
        base = os.path.basename(f)
        if base not in fseen:
            fseen.add(base)
            fonts.append(f)
    return class_info, packages, sorted(fonts)


def collect_inputs(workdir, max_inputs):
    inputs = []
    if not workdir or not os.path.isdir(workdir):
        return inputs
    count = 0
    for root, dirs, names in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in ("round_logs", ".git")]
        for name in sorted(names):
            ext = os.path.splitext(name)[1].lower()
            if ext in BUILD_EXCLUDE_EXT:
                continue
            if ext not in INPUT_EXTS:
                continue
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > 8 * 1024 * 1024:  # skip huge assets in the hash listing
                inputs.append({"path": path, "sha256": None, "bytes": size,
                               "note": "too large; hash skipped"})
                continue
            inputs.append({"path": path, "sha256": sha256_of(path), "bytes": size})
            count += 1
            if count >= max_inputs:
                inputs.append({"note": "input list truncated at --max-inputs=%d" % max_inputs})
                return inputs
    return inputs


def build_record(main_tex=None, log_path=None, rounds_path=None, workdir=None,
                 max_inputs=400):
    notes = []
    # --- rounds / commands
    rounds_data = None
    if rounds_path:
        try:
            with open(rounds_path, "r", encoding="utf-8", errors="replace") as fh:
                rounds_data = json.load(fh)
        except (OSError, ValueError) as exc:
            notes.append("rounds report unreadable: %s" % exc)
            rounds_data = None
    commands = []
    if rounds_data and isinstance(rounds_data.get("passes"), list):
        for p in rounds_data["passes"]:
            commands.append({"tool": p.get("tool"), "args": p.get("args"),
                             "exit_code": p.get("exit_code"),
                             "seconds": p.get("seconds"),
                             "kind": p.get("kind")})
    else:
        notes.append("no build_loop.py report given (--rounds): command sequence unavailable")

    # --- tools actually used
    tools_used = []
    if rounds_data:
        for name in dict.fromkeys(p.get("tool") for p in rounds_data.get("passes", []) if p.get("tool")):
            tools_used.append(probe_tool(name))
    elif main_tex:
        # no rounds report: at least record that a probe was attempted
        notes.append("no rounds report: probing the default engines honestly (may be unavailable)")
        for name in ("latexmk", "pdflatex"):
            tools_used.append(probe_tool(name))
    else:
        notes.append("no --main and no --rounds: tool versions not probed")

    # --- packages / fonts / class from the log
    class_info, packages, fonts = extract_packages(log_path)
    if log_path and not os.path.isfile(log_path):
        notes.append("log not found (%s): packages/fonts unknown" % log_path)

    # --- inputs + pdf
    wd = workdir or (os.path.dirname(os.path.abspath(main_tex)) if main_tex else None)
    inputs = collect_inputs(wd, max_inputs)
    if rounds_data and rounds_data.get("pdf_path"):
        generated_pdf = os.path.realpath(rounds_data["pdf_path"])
        # The reported build output is not a source input merely because .pdf
        # is also a legitimate figure extension elsewhere in the project.
        inputs = [item for item in inputs
                  if not item.get("path") or os.path.realpath(item["path"]) != generated_pdf]
    if not inputs:
        notes.append("no input files found in workdir: %s" % wd)
    pdf_info = None
    if rounds_data and rounds_data.get("pdf_path"):
        pdf_path = rounds_data["pdf_path"]
        if os.path.isfile(pdf_path):
            pdf_info = {"path": pdf_path, "sha256": sha256_of(pdf_path),
                        "bytes": os.path.getsize(pdf_path)}
        else:
            notes.append("pdf reported by build loop is missing on disk: %s" % pdf_path)

    return {
        "template": class_info or ({"class": None, "note": "not extracted (no log)"} if not log_path else {"class": None, "note": "no Document Class line in log"}),
        "tool": tools_used if tools_used else None,
        "packages": packages if packages is not None else None,
        "fonts": fonts if fonts is not None else None,
        "commands": commands if commands else None,
        "rounds": {
            "count": rounds_data.get("rounds_engine") if rounds_data else None,
            "converged": rounds_data.get("converged") if rounds_data else None,
            "convergence_rule": rounds_data.get("convergence_rule") if rounds_data else None,
            "time_budget_exceeded": rounds_data.get("time_budget_exceeded") if rounds_data else None,
            "elapsed_seconds": rounds_data.get("elapsed_seconds") if rounds_data else None,
        } if rounds_data else None,
        "inputs": inputs,
        "pdf": pdf_info,
        "generated_at": None,
        "deterministic_record": True,
        "notes": notes + ["wall-clock generation time is intentionally not fabricated or serialized; "
                          "the platform's native trace is the runtime timestamp authority"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generate a reproducible-build record (tools, packages, fonts, commands, hashes) from real evidence."
    )
    ap.add_argument("--main", help="path to the main .tex file")
    ap.add_argument("--log", help="path to the final .log file")
    ap.add_argument("--rounds", help="path to the build_loop.py JSON report")
    ap.add_argument("--workdir", help="directory to hash input files from (default: dir of --main)")
    ap.add_argument("--output", help="write the JSON record to this file (also printed)")
    ap.add_argument("--max-inputs", type=int, default=400)
    args = ap.parse_args(argv)

    if not (args.main or args.log or args.rounds):
        print(json.dumps({"error": "nothing to record: give --main and/or --log and/or --rounds"},
                         ensure_ascii=False))
        return 3
    record = build_record(args.main, args.log, args.rounds, args.workdir,
                          args.max_inputs)
    out = json.dumps(record, ensure_ascii=False, indent=2)
    print(out)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
        except OSError as exc:
            print("warn: could not write --output: %s" % exc, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
