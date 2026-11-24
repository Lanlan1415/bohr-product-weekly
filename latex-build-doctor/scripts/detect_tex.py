#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detect_tex.py -- probe the local TeX toolchain and report it as JSON.

Probes engines (pdflatex, xelatex, lualatex, tectonic), the build driver
(latexmk) and bibliography tools (bibtex, biber) via PATH lookup plus
`--version`. Never installs anything; never guesses a version it could not
read.

Usage:
    python -I detect_tex.py [--out FILE] [--timeout N]

Exit codes:
    0  at least one LaTeX engine found
    3  no engine found (install hints printed together with the JSON)

Output (single JSON object on stdout):
{
  "status": "ok" | "no_tex",
  "engines_available": ["pdflatex", "latexmk"],
  "tools": {"pdflatex": {"available": true, "version": "...", "path": "..."}},
  "recommended": {"driver": "latexmk", "command": "latexmk -pdf ..."},
  "install_hints": ["..."]
}
"""
import argparse
import json
import shutil
import subprocess
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS = [
    ("pdflatex", "--version", "engine"),
    ("xelatex", "--version", "engine"),
    ("lualatex", "--version", "engine"),
    ("latexmk", "--version", "driver"),
    ("tectonic", "--version", "engine"),
    ("bibtex", "--version", "bib"),
    ("biber", "--version", "bib"),
]
ENGINE_NAMES = {"pdflatex", "xelatex", "lualatex", "tectonic"}

INSTALL_HINTS = [
    "TeX Live (Linux/macOS/Windows): https://tug.org/texlive/ -- full engine set; then `tlmgr install latexmk`",
    "MiKTeX (Windows/macOS): https://miktex.org/ -- `miktex packages install latexmk` (or use the console UI)",
    "Tectonic (single self-contained binary): https://tectonic-typesetting.github.io/ -- no admin rights needed",
    "No TeX available? This skill still runs static_check.py (structure/reference/table checks without compiling).",
]


def _run_version(path, flag, timeout):
    """Run `<tool> --version` and return the first non-empty output line."""
    try:
        cp = subprocess.run(
            [path, flag], capture_output=True, timeout=timeout
        )
        raw = (cp.stdout or b"") + (cp.stderr or b"")
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line:
                return line[:200]
        return None
    except Exception as exc:  # timeout, permission, OS error
        return "probe failed: %s" % exc.__class__.__name__


def probe_all(timeout=20):
    tools = {}
    for name, flag, role in TOOLS:
        entry = {"role": role, "available": False, "version": None, "path": None}
        path = shutil.which(name)
        if path:
            entry["path"] = path
            ver = _run_version(path, flag, timeout)
            entry["version"] = ver
            # "probe failed" means the binary exists but could not be executed
            entry["available"] = bool(ver) and not ver.startswith("probe failed")
        tools[name] = entry
    engines = sorted(n for n in ENGINE_NAMES if tools[n]["available"])
    drivers = [n for n in ("latexmk",) if tools[n]["available"]]
    return tools, engines, drivers


def recommend(engines, drivers):
    if "latexmk" in drivers:
        if "pdflatex" in engines:
            cmd = "latexmk -pdf -interaction=nonstopmode -file-line-error MAIN.tex"
        elif "xelatex" in engines:
            cmd = "latexmk -xelatex -interaction=nonstopmode -file-line-error MAIN.tex"
        else:
            cmd = "latexmk -pdf -interaction=nonstopmode -file-line-error MAIN.tex"
        return {"driver": "latexmk", "command": cmd}
    for eng in ("pdflatex", "xelatex", "lualatex", "tectonic"):
        if eng in engines:
            if eng == "tectonic":
                return {"driver": "tectonic", "command": "tectonic MAIN.tex"}
            return {"driver": "manual", "command": "%s -interaction=nonstopmode -file-line-error MAIN.tex" % eng}
    return {"driver": None, "command": None}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Probe pdflatex/latexmk/tectonic/xelatex availability and versions (JSON output)."
    )
    ap.add_argument("--out", metavar="FILE", help="also write the JSON report to FILE")
    ap.add_argument("--timeout", type=int, default=20, help="per-tool probe timeout in seconds (default 20)")
    args = ap.parse_args(argv)

    tools, engines, drivers = probe_all(args.timeout)
    if engines:
        status = "ok"
        rc = 0
    else:
        status = "no_tex"
        rc = 3

    report = {
        "status": status,
        "engines_available": engines,
        "drivers_available": drivers,
        "tools": tools,
        "recommended": recommend(engines, drivers),
        "install_hints": INSTALL_HINTS if rc == 3 else [],
        "exit_code": rc,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            print("warn: could not write --out %s: %s" % (args.out, exc), file=sys.stderr)
    if rc == 3:
        print(
            "NOTE: no LaTeX engine found (exit 3). The skill must honestly record "
            "status=cannot_determine for compilation and fall back to static_check.py.",
            file=sys.stderr,
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
