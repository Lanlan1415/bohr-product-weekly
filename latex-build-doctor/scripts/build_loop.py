#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_loop.py -- run the fixed compile-round protocol until references converge.

Protocol (see references/build-protocol.md for the full rationale):
  * latexmk available  -> `latexmk -pdf ...` is one round; repeat until our own
    aux-label-hash convergence check passes (max-rounds cap applies).
  * no latexmk         -> pdflatex/xelatex/lualatex rounds: pass 1, then
    bibtex/biber if the run has bibliography data, then pass 2 and pass 3;
    further passes only while the aux label set keeps changing.
  * tectonic           -> `tectonic MAIN.tex` is one round (it runs the needed
    passes internally); the same hash check applies.

Convergence rule (strict): last two rounds exited 0, the \\newlabel set hash of
the .aux tree is identical between those rounds, and the last log contains no
"Rerun to get ..." / "Label(s) may have changed" warnings.

Budget: the whole run respects --time-budget seconds (default 900). When the
budget runs out the loop stops and honestly records time_budget_exceeded=true;
it never fabricates a converged result.

Usage:
    python -I build_loop.py MAIN.tex [--engine auto] [--workdir DIR]
        [--max-rounds 6] [--time-budget 900] [--report FILE] [--keep-logs DIR]
        [--make-preview DIR] [--miktex-installer auto|none]

Exit codes: 0 = a PDF was produced (converged or not, see JSON "converged");
1 = compile failed (no PDF); 2 = engine missing (run detect_tex.py first);
3 = bad arguments. JSON report is printed to stdout (and --report FILE).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RERUN_MARKERS = (
    "Rerun to get",
    "Label(s) may have changed",
    "Package rerunfilecheck Warning",
    "Rerun LaTeX",
)

NEWLABEL_RE = re.compile(r"\\newlabel\{")
INPUT_AUX_RE = re.compile(r"\\@input\{([^}]+)\}")
BIBDATA_RE = re.compile(r"\\bibdata\{")

ARTIFACT_EXTS = {
    ".aux", ".log", ".out", ".toc", ".lof", ".lot", ".bbl", ".blg", ".fls",
    ".fdb_latexmk", ".xdv", ".bcf", ".run.xml", ".spl", ".synctex.gz", ".nav",
    ".snm", ".vrb", ".idx", ".ind", ".ilg", ".glo", ".gls", ".acn", ".acr",
    ".alg", ".glg", ".glsdefs", ".listing",
}


# --------------------------------------------------------------------------
# aux label-set hashing (convergence detection core)
# --------------------------------------------------------------------------

def collect_aux_labels(aux_path, seen=None):
    """Collect normalized \\newlabel lines from an .aux file and its children.

    Returns a list of strings; children referenced via \\@input{x.aux} are
    included (recursively, cycle-safe). Missing files contribute nothing.
    """
    if seen is None:
        seen = set()
    real = os.path.realpath(aux_path)
    if real in seen or not os.path.isfile(aux_path):
        return []
    seen.add(real)
    labels = []
    try:
        with open(aux_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = " ".join(raw.split())
                if not line:
                    continue
                if NEWLABEL_RE.search(line):
                    labels.append(line)
                else:
                    m = INPUT_AUX_RE.search(line)
                    if m:
                        child = m.group(1)
                        child_path = os.path.join(os.path.dirname(aux_path), child)
                        labels.extend(collect_aux_labels(child_path, seen))
    except OSError:
        pass
    return labels


def aux_label_hash(aux_path):
    """MD5 over the sorted unique \\newlabel set of the aux tree."""
    labels = sorted(set(collect_aux_labels(aux_path)))
    digest = hashlib.md5()
    for lab in labels:
        digest.update(lab.encode("utf-8", errors="replace"))
    return digest.hexdigest()


def log_has_rerun(log_path):
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return False
    return any(marker in text for marker in RERUN_MARKERS)


_LOG_BLOCKER_RE = re.compile(
    r"(?:^|[.\n])(?:LaTeX|Package\s+\S+|Class\s+\S+)\s+Error|"
    r"Undefined control sequence|Emergency stop|Fatal error|"
    r"Citation `[^']+'[^\n]*undefined|Reference `[^']+'[^\n]*undefined|"
    r"There were undefined (?:references|citations)|No pages of output",
    re.IGNORECASE | re.MULTILINE,
)


def log_blockers(log_path):
    """Actual items that forbid a strict convergence claim.

    ``None`` means no readable log and therefore no positive verification.  An
    empty list is evidence, not a default: it is returned only after parsing a
    real final log and finding no errors or unresolved citation/reference.
    """
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    return sorted(set(m.group(0).strip()[:240] for m in _LOG_BLOCKER_RE.finditer(text)))


def build_state_hash(aux_path, workdir, main_base):
    """Hash reference/citation and bibliography state, not just label lines.

    This is the small, inspectable counterpart of latexmk's dependency database:
    aux citations/labels, the generated bbl, and table-of-contents state all have
    to stabilise.  Volatile log timing and PDF metadata are deliberately absent.
    """
    aux_path = os.fspath(aux_path)
    workdir = os.fspath(workdir)
    h = hashlib.sha256()
    paths = [aux_path]
    for ext in (".bbl", ".toc", ".out", ".lof", ".lot"):
        paths.append(os.path.join(workdir, main_base + ext))
    for path in paths:
        h.update(os.path.basename(path).encode("utf-8"))
        if not os.path.isfile(path):
            h.update(b"<missing>")
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            h.update(b"<unreadable>")
            continue
        for raw in lines:
            line = " ".join(raw.split())
            if not line or line.startswith("%"):
                continue
            if path.endswith(".aux") and not re.search(
                    r"\\(?:newlabel|bibcite|citation|abx@aux@cite|bibdata|bibstyle|@input)\b", line):
                continue
            h.update(line.encode("utf-8", errors="replace"))
            h.update(b"\n")
    return h.hexdigest()


def choose_engine(main_tex, engine_pref="auto"):
    """Choose and record the real driver/engine, respecting Unicode/CJK input."""
    def have(name):
        return shutil.which(name) is not None

    if engine_pref == "latexmk":
        return ("latexmk", None) if have("latexmk") else (None, None)
    if engine_pref in ("pdflatex", "xelatex", "lualatex"):
        return ("manual", engine_pref) if have(engine_pref) else (None, None)
    if engine_pref == "tectonic":
        return ("tectonic", None) if have("tectonic") else (None, None)

    source = ""
    try:
        with open(main_tex, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError:
        pass
    unicode_needed = bool(re.search(
        r"\\(?:usepackage|RequirePackage)(?:\[[^]]*\])?\{(?:ctex|xeCJK|fontspec|luatexja)[^}]*\}"
        r"|\\documentclass(?:\[[^]]*\])?\{ctex|[^\x00-\x7f]", source))
    preference = (["xelatex", "lualatex", "pdflatex"] if unicode_needed
                  else ["pdflatex", "xelatex", "lualatex"])
    chosen = next((eng for eng in preference if have(eng)), None)
    if have("latexmk") and chosen:
        return ("latexmk", chosen)
    if chosen:
        return ("manual", chosen)
    if have("tectonic"):
        return ("tectonic", None)
    return (None, None)


def find_engine(engine_pref, main_tex=None):
    """Backward-compatible engine entry point used by the baseline selftest."""
    return choose_engine(main_tex or "", engine_pref)


def build_engine_cmd(driver, engine, main_name, miktex_installer):
    """Command list for one compile round."""
    if driver == "latexmk":
        if engine == "xelatex":
            flag = "-xelatex"
        elif engine == "lualatex":
            flag = "-lualatex"
        else:
            flag = "-pdf"
        return ["latexmk", flag, "-recorder", "-bibtex",
                "-interaction=nonstopmode", "-file-line-error", main_name]
    if driver == "tectonic":
        return ["tectonic", "--outfmt", "pdf", main_name]
    cmd = [engine, "-recorder", "-interaction=nonstopmode", "-file-line-error"]
    if miktex_installer == "auto":
        cmd.append("--enable-installer")  # MiKTeX: auto-install missing packages
    cmd.append(main_name)
    return cmd


def bib_command(main_base, workdir):
    """Pick biber (biblatex/.bcf) or bibtex (classic \\bibliography). Returns None if no bib data."""
    bcf = os.path.join(workdir, main_base + ".bcf")
    aux = os.path.join(workdir, main_base + ".aux")
    if os.path.isfile(bcf) and shutil.which("biber"):
        return ["biber", main_base]
    if os.path.isfile(aux):
        try:
            with open(aux, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
        if BIBDATA_RE.search(text) and shutil.which("bibtex"):
            return ["bibtex", main_base]
    return None


# --------------------------------------------------------------------------
# subprocess with budget
# --------------------------------------------------------------------------

def run_cmd(cmd, cwd, timeout):
    t0 = time.monotonic()
    try:
        cp = subprocess.run(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        out = cp.stdout.decode("utf-8", errors="replace")[-4000:] if cp.stdout else ""
        return {"exit_code": cp.returncode, "seconds": round(time.monotonic() - t0, 2),
                "stdout_tail": out, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "seconds": round(time.monotonic() - t0, 2),
                "stdout_tail": "", "timed_out": True}
    except OSError as exc:
        return {"exit_code": None, "seconds": round(time.monotonic() - t0, 2),
                "stdout_tail": "spawn failed: %s" % exc, "timed_out": False}


# --------------------------------------------------------------------------
# optional PDF -> PNG preview (honest: records the method or unavailable)
# --------------------------------------------------------------------------

def make_preview(pdf_path, out_dir, max_pages=3):
    """Try pdftoppm / magick / gswin64c / gs / mutool to rasterize the PDF."""
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    attempts = []
    if shutil.which("pdftoppm"):
        attempts.append(
            (["pdftoppm", "-png", "-r", "110", "-f", "1", "-l", str(max_pages),
              pdf_path, os.path.join(out_dir, stem + "_page")], "pdftoppm"))
    if shutil.which("magick"):
        attempts.append(
            (["magick", "-density", "110", "%s[0-%d]" % (pdf_path, max_pages - 1),
              os.path.join(out_dir, stem + "_page.png")], "magick"))
    for gs in ("gswin64c", "gs"):
        if shutil.which(gs):
            attempts.append(
                ([gs, "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", "-r110",
                  "-dFirstPage=1", "-dLastPage=%d" % max_pages,
                  "-sOutputFile=" + os.path.join(out_dir, stem + "_page-%02d.png"),
                  pdf_path], gs))
    if shutil.which("mutool"):
        attempts.append(
            (["mutool", "draw", "-o", os.path.join(out_dir, stem + "_page.png"),
              "-r", "110", pdf_path, "1-%d" % max_pages], "mutool"))
    for cmd, method in attempts:
        res = run_cmd(cmd, cwd=None, timeout=120)
        pngs = sorted(f for f in os.listdir(out_dir)
                      if f.startswith(stem + "_page") and f.endswith(".png"))
        if res["exit_code"] == 0 and pngs:
            return {"method": method, "files": pngs, "out_dir": out_dir}
    return {"method": None, "files": [], "out_dir": out_dir,
            "note": "no rasterizer (pdftoppm/magick/ghostscript/mutool) found; "
                    "PDF itself is still delivered"}


# --------------------------------------------------------------------------
# main loop
# --------------------------------------------------------------------------

def run_build(main_tex, driver, engine, workdir, max_rounds, time_budget,
              miktex_installer, keep_logs):
    """Execute the round protocol. Returns the report dict."""
    main_name = os.path.basename(main_tex)
    main_base = os.path.splitext(main_name)[0]
    aux_path = os.path.join(workdir, main_base + ".aux")
    log_path = os.path.join(workdir, main_base + ".log")
    pdf_path = os.path.join(workdir, main_base + ".pdf")

    passes = []
    label_hashes = []
    state_hashes = []
    started = time.monotonic()

    def elapsed():
        return time.monotonic() - started

    def remaining():
        return max(0.0, time_budget - elapsed())

    def record(kind, cmd, res):
        entry = {
            "index": len(passes) + 1,
            "kind": kind,           # engine | bib
            "tool": cmd[0],
            "args": cmd,
            "exit_code": res["exit_code"],
            "seconds": res["seconds"],
            "timed_out": res["timed_out"],
        }
        if os.path.isfile(log_path):
            try:
                shutil.copyfile(log_path, os.path.join(keep_logs, "round_%02d.log" % entry["index"]))
                entry["log"] = os.path.join(keep_logs, "round_%02d.log" % entry["index"])
            except OSError:
                entry["log"] = log_path
        if kind == "engine":
            h = aux_label_hash(aux_path) if os.path.isfile(aux_path) else None
            entry["aux_labels_hash"] = h
            label_hashes.append(h)
            state_h = build_state_hash(aux_path, workdir, main_base)
            entry["build_state_hash"] = state_h
            entry["fls_present"] = os.path.isfile(os.path.join(workdir, main_base + ".fls"))
            entry["log_blockers"] = log_blockers(log_path) if os.path.isfile(log_path) else None
            state_hashes.append(state_h)
        passes.append(entry)
        return entry

    def engine_round():
        cmd = build_engine_cmd(driver, engine, main_name, miktex_installer)
        res = run_cmd(cmd, workdir, timeout=max(5.0, remaining()))
        return record("engine", cmd, res)

    def bib_round():
        cmd = bib_command(main_base, workdir)
        if not cmd:
            return False
        res = run_cmd(cmd, workdir, timeout=max(5.0, remaining()))
        record("bib", cmd, res)
        return True

    time_budget_exceeded = False
    consecutive_fail = 0
    engine_passes_done = 0

    if driver == "manual":
        # pass 1
        engine_round()
        engine_passes_done += 1
        consecutive_fail = 0 if passes[-1]["exit_code"] == 0 else 1
        # bibliography pass (no-op unless .bcf or \\bibdata in the aux is present)
        bib_round()
        # pass 2 and pass 3
        for _ in range(2):
            if remaining() <= 1:
                time_budget_exceeded = True
                break
            engine_round()
            engine_passes_done += 1
            consecutive_fail = consecutive_fail + 1 if passes[-1]["exit_code"] != 0 else 0
            if consecutive_fail >= 2:
                break
        # extra rounds while labels keep changing
        while (not time_budget_exceeded and not consecutive_fail >= 2
               and engine_passes_done < max_rounds and remaining() > 1):
            last_exit = passes[-1]["exit_code"]
            rerun = log_has_rerun(log_path)
            stable = (len(state_hashes) >= 2 and state_hashes[-1] == state_hashes[-2])
            blockers = log_blockers(log_path)
            if last_exit == 0 and stable and not rerun and blockers == []:
                break  # strict convergence: all generated state is stable and resolved
            engine_round()
            engine_passes_done += 1
            consecutive_fail = consecutive_fail + 1 if passes[-1]["exit_code"] != 0 else 0
    else:
        # latexmk / tectonic: one invocation is one round
        while engine_passes_done < max_rounds and not time_budget_exceeded:
            if remaining() <= 1:
                time_budget_exceeded = True
                break
            engine_round()
            engine_passes_done += 1
            last = passes[-1]
            if last["exit_code"] is not None and last["exit_code"] != 0:
                consecutive_fail += 1
            else:
                consecutive_fail = 0
            if consecutive_fail >= 2:
                break
            rerun = log_has_rerun(log_path)
            stable = (len(state_hashes) >= 2 and state_hashes[-1] == state_hashes[-2])
            blockers = log_blockers(log_path)
            if last["exit_code"] == 0 and stable and not rerun and blockers == []:
                break
            if last["exit_code"] == 0 and engine_passes_done >= max_rounds:
                break
            if last["exit_code"] == 0 and engine_passes_done == 1 and max_rounds >= 2:
                continue  # run a second round to confirm all generated state is stable

    # convergence verdict. A PDF on disk is not itself evidence of convergence.
    converged = None
    convergence_rule = None
    last_exit = passes[-1]["exit_code"] if passes else None
    rerun_needed = log_has_rerun(log_path) if os.path.isfile(log_path) else None
    blockers = log_blockers(log_path) if os.path.isfile(log_path) else None
    stable = (len(state_hashes) >= 2 and state_hashes[-1] == state_hashes[-2]
              and state_hashes[-1] is not None)
    if last_exit == 0 and stable and rerun_needed is False and blockers == []:
        converged = True
        convergence_rule = ("strict: exit=0, aux/citation/bibliography/TOC state hash stable "
                            "across last 2 engine rounds, no rerun warnings, no unresolved "
                            "citations/references or log errors")
    elif last_exit == 0 and rerun_needed is False and blockers == [] and passes:
        converged = None
        convergence_rule = ("unverified: exit=0 and no rerun warning, but dependency state "
                            "did not prove stable or the log could not prove resolution")
    elif passes:
        converged = False
        convergence_rule = "failed: last round exit=%s or rerun warnings remain" % last_exit

    if elapsed() > time_budget:
        time_budget_exceeded = True

    pdf_ok = os.path.isfile(pdf_path)
    if last_exit == 0 and pdf_ok:
        status = "success" if converged else ("unconverged" if converged is None else "failed")
        if converged is None:
            status = "partial"
        if time_budget_exceeded and not converged:
            status = "partial"
    elif pdf_ok:
        status = "partial"   # PDF exists from an earlier round but last round errored
    elif time_budget_exceeded:
        status = "time_budget_exceeded"
    else:
        status = "failed"

    return {
        "main": os.path.abspath(main_tex),
        "workdir": os.path.abspath(workdir),
        "driver": driver,
        "engine": engine,
        "protocol": ("latexmk/tectonic rounds" if driver in ("latexmk", "tectonic")
                     else "pdflatex-protocol: pass1 -> bibtex/biber -> pass2 -> pass3 (+ extras)"),
        "passes": passes,
        "rounds_engine": engine_passes_done,
        "label_hashes": label_hashes,
        "state_hashes": state_hashes,
        "converged": converged,
        "convergence_rule": convergence_rule,
        "rerun_needed": rerun_needed,
        "log_blockers": blockers,
        "status": status,
        "pdf_path": pdf_path if pdf_ok else None,
        "time_budget_seconds": time_budget,
        "elapsed_seconds": round(elapsed(), 2),
        "time_budget_exceeded": time_budget_exceeded,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run the fixed LaTeX compile-round protocol with aux-label convergence detection."
    )
    ap.add_argument("main", nargs="?", help="path to the main .tex file")
    ap.add_argument("--dir", help="work directory (default: directory of MAIN)")
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "latexmk", "pdflatex", "xelatex", "lualatex", "tectonic"],
                    help="engine/driver preference (default auto: latexmk > pdflatex > xelatex > lualatex > tectonic)")
    ap.add_argument("--max-rounds", type=int, default=6, help="max engine rounds (default 6)")
    ap.add_argument("--time-budget", type=float, default=900.0, help="total wall-clock budget in seconds (default 900)")
    ap.add_argument("--report", metavar="FILE", help="write the JSON report to FILE")
    ap.add_argument("--keep-logs", metavar="DIR", help="save per-round .log snapshots here (default: <workdir>/round_logs)")
    ap.add_argument("--make-preview", metavar="DIR", help="rasterize the final PDF to PNGs here (best effort)")
    ap.add_argument("--miktex-installer", default="none", choices=["none", "auto"],
                    help="'auto' passes MiKTeX --enable-installer so missing packages install instead of failing")
    args = ap.parse_args(argv)

    if not args.main:
        ap.error("MAIN.tex is required (or use --dir with a single \\documentclass .tex).")
        return 3
    main_tex = args.main
    if not os.path.isfile(main_tex):
        # try to locate inside --dir
        if args.dir:
            cand = os.path.join(args.dir, args.main)
            if os.path.isfile(cand):
                main_tex = cand
        if not os.path.isfile(main_tex):
            print(json.dumps({"status": "failed", "error": "main file not found: %s" % args.main},
                             ensure_ascii=False))
            return 3
    workdir = args.dir or os.path.dirname(os.path.abspath(main_tex))
    keep_logs = args.keep_logs or os.path.join(workdir, "round_logs")
    os.makedirs(keep_logs, exist_ok=True)

    driver, engine = find_engine(args.engine, main_tex)
    if driver is None:
        report = {
            "main": os.path.abspath(main_tex), "workdir": os.path.abspath(workdir),
            "driver": None, "engine": None, "passes": [], "rounds_engine": 0,
            "converged": False, "status": "cannot_determine", "pdf_path": None,
            "compilation_attempted": False, "pdf_generated": False,
            "error": "no TeX engine found for preference '%s'; run detect_tex.py" % args.engine,
            "honest_note": "compilation was NOT executed; do not claim a PDF result",
        }
        text = json.dumps(report, ensure_ascii=False, indent=2)
        print(text)
        if args.report:
            try:
                with open(args.report, "w", encoding="utf-8") as fh:
                    fh.write(text + "\n")
            except OSError as exc:
                print("warn: could not write --report: %s" % exc, file=sys.stderr)
        return 2

    report = run_build(main_tex, driver, engine, workdir, args.max_rounds,
                       args.time_budget, args.miktex_installer, keep_logs)
    report["compilation_attempted"] = True
    report["pdf_generated"] = bool(report.get("pdf_path"))

    if report.get("pdf_path") and args.make_preview:
        report["preview"] = make_preview(report["pdf_path"], args.make_preview)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        try:
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            print("warn: could not write --report: %s" % exc, file=sys.stderr)

    if report["status"] in ("success", "unconverged"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
