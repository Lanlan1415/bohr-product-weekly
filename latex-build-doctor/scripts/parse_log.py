#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_log.py -- parse a TeX .log (and optionally BibTeX/Biber .blg) into a
categorized error/warning localization table.

Unlike eyeballing the console, this reports ALL errors and warnings (not just
the first one), each classified by root cause with a fix hint. Categories and
fix templates are kept in sync with references/error-playbook.md.

Usage:
    python -I parse_log.py BUILD.log [--out FILE] [--blg FILE|auto]

Output: one JSON object:
{
  "log": "...", "engine_hint": "This is pdfTeX ...",
  "errors":   [{"file","line","message","category","fix_hint","file_source"}],
  "warnings": [{"file","line","message","category","fix_hint","file_source"}],
  "summary":  {"error_count","warning_count","categories":{...},
               "rerun_needed","has_errors"}
}

Exit codes: 0 = parsed (with or without errors); 3 = log file missing.
Error/warning items are data for the model's fix loop -- the skill must not
stop at the first error.
"""
import argparse
import json
import os
import re
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MAX_PRINT_LINE = 79  # classic TeX wraps log lines at this width

# error first-line variants: "./main.tex:12: Undefined control sequence."
# (colons allowed inside the path so drive letters like C:/... still match)
FILE_LINE_ERROR_RE = re.compile(
    r"^(?P<file>[^\s()!]+?\.(?:tex|sty|cls|ltx|clo|fd|cfg|def|dtx|bbl|bbx|cbx|lbx)):(?P<line>\d+):\s?(?P<msg>.*)$"
)
ERROR_KEYWORD_RE = re.compile(
    r"^(Undefined control sequence|LaTeX Error|Package\s+\S+\s+Error|Class\s+\S+\s+Error|"
    r"Missing\s|Extra\s|Display math|Bad math|Runaway argument|Paragraph ended|File ended while|"
    r"Too many\s|Command \\\\|Environment\s+\S+\s+undefined|Float\(s\)|"
    r"Unicode character|Improper\s|Misplaced\s|Argument of\s|Emergency stop|Fatal error|"
    r"Something's wrong|Illegal\s|No pages of output|Not in outer par mode|I can't find file)"
)
LINE_IN_ERROR_RE = re.compile(r"\bl\.(\d+)")
INPUT_LINE_RE = re.compile(r"on input line (\d+)")
LINES_RANGE_RE = re.compile(r"at lines (\d+)--(\d+)|detected at line (\d+)")

# ---- root-cause classification (error side) -----------------------------
# Order matters: first match wins. Keep in sync with references/error-playbook.md.
ERROR_RULES = [
    ("missing_package",
     re.compile(r"File `[^']+\.sty' not found", re.I),
     "Package not installed: TeX Live -> tlmgr install <pkg>; MiKTeX -> miktex packages install <pkg>; "
     "also check \\usepackage spelling. Or compile with MiKTeX --enable-installer."),
    ("missing_class",
     re.compile(r"File `[^']+\.cls' not found", re.I),
     "Template class missing: copy the .cls (and its .def/.clo/.fd companions) next to the main file "
     "or install the full template bundle; check \\documentclass spelling."),
    ("missing_file",
     re.compile(r"I can't find file|File `[^']+' not found|No file `[^']+'", re.I),
     "Input file missing or path wrong: check \\input/\\include/\\includegraphics path, case sensitivity, "
     "and that the working directory is the one holding the file."),
    ("undefined_control_sequence",
     re.compile(r"Undefined control sequence"),
     "Macro misspelled or never defined; or the package that defines it is not loaded "
     "(e.g. \\eqref needs amsmath, \\ SI needs siunitx). Look at the fragment shown after l.<n>."),
    ("math_mode_error",
     re.compile(r"Missing \$ inserted|Bad math environment delimiter|Display math should end with|"
                r"Missing \\right|Extra \\right|Bad use of \\\\|\\left|Double superscript"),
     "Math/material mode conflict: math-only command used in text (wrap in $...$ or \\(...\\)), "
     "or text-only content inside math; check \\left/\\right pairing."),
    ("environment_mismatch",
     re.compile(r"ended by \\end\{|Extra \\end\{|Environment\s+\S+\s+undefined|\\begin\{[^}]*\} ended by"),
     "\\begin{X} closed by \\end{Y} (or environment never defined): fix the name pair; "
     "nested environments must close innermost first."),
    ("runaway_argument",
     re.compile(r"Runaway argument|Paragraph ended before|File ended while scanning|"
                r"Missing \} inserted|Missing \{ inserted|has an extra \}"),
     "Unbalanced brace or a blank line inside a command argument: close the {..} opened earlier; "
     "blank lines are not allowed inside most arguments (use \\par-free content)."),
    ("table_column_mismatch",
     re.compile(r"Extra alignment tab|Misplaced alignment tab character"),
     "Row has more/fewer & cells than the tabular preamble declares; fix the column spec "
     "or the row (also check \\multicolumn spans)."),
    ("unicode_error",
     re.compile(r"Unicode character .{0,40} not set up|Invalid UTF-8 byte|inputenc Error|"
                r"Package utf8x Error"),
     "Character the engine cannot typeset: pdflatex -> declare with \\DeclareUnicodeCharacter or use "
     "xelatex/lualatex + ctex/fontspec for CJK; re-save the file as UTF-8."),
    ("float_problem",
     re.compile(r"Float\(s\) lost|Too many unprocessed floats"),
     "Float placed where it cannot be shipped out (e.g. inside a box/minipage): move \\begin{figure} "
     "to top level; or add more \\clearpage/[!t] placement."),
    ("emergency_stop",
     re.compile(r"Emergency stop|Fatal error"),
     "TeX gave up after earlier (often missing-file) errors: fix the FIRST error in the table, "
     "not this one."),
    ("font_problem",
     re.compile(r"Font .* not found|Font shape .* undefined.*using"),
     "Requested font unavailable: install the font package or switch to a declared font family."),
    ("other", None,
     "Read the error text and the l.<n> context fragment; map to the closest category in "
     "references/error-playbook.md."),
]

# ---- root-cause classification (warning side) ---------------------------
WARNING_RULES = [
    ("undefined_reference",
     re.compile(r"Reference `[^']+' .*undefined|There were undefined references", re.I),
     "\\ref/\\pageref target has no \\label (or the label comes later in the text and another "
     "compile round is needed): add the \\label or rerun."),
    ("undefined_citation",
     re.compile(r"Citation `[^']+' .*undefined|There were undefined citations|"
                r"empty `thebibliography' environment", re.I),
     "\\cite key not resolved: check the key spelling against the .bib/.bibitem, ensure the bib "
     "step ran (bibtex/biber) and two more compile rounds follow."),
    ("rerun_needed",
     re.compile(r"Rerun to get|Label\(s\) may have changed|rerunfilecheck|Rerun LaTeX"),
     "Cross-reference/citation data changed: run another compile round (build_loop.py does this "
     "automatically until the aux label hash is stable)."),
    ("multiply_defined_label",
     re.compile(r"Label `[^']+' multiply defined"),
     "The same \\label{key} appears twice: rename one occurrence (duplicate labels break \\ref)."),
    ("overfull_box",
     re.compile(r"^Overfull \\hbox"), None),  # hint filled below
    ("underfull_box",
     re.compile(r"^Underfull \\[hv]box"), None),
    ("font_problem",
     re.compile(r"LaTeX Font Warning|Font shape .*undefined|Size substitution"),
     "Font shape substitution: usually cosmetic; install the family or accept the substitution."),
    ("bibliography_problem",
     re.compile(r"Package natbib Warning|Package biblatex Warning|BibTeX warning|biber warning"),
     "Bibliography backend reports a data problem (missing field, duplicate key, style issue): "
     "fix the .bib entry, then re-run the bib step."),
    ("package_warning",
     re.compile(r"Package\s+\S+\s+Warning|Class\s+\S+\s+Warning"),
     "Package-level warning: read the package name in the message; usually formatting advice, "
     "fix only if it affects required output."),
]

BOX_HINT_OVER = "Content wider than the line/column: allow a line break, use \\\\linebreak, tighten spacing, or widen the box; do NOT hide it with tiny fonts or graphicx scaling."
BOX_HINT_UNDER = "Loose spacing from forced breaks (\\\\\\\\, \\\\linebreak, sloppy par): remove the forced break or use \\\\looseness=-1; cosmetic unless the template forbids it."

ENGINE_RE = re.compile(r"^This is (pdfTeX|XeTeX|LuaTeX|LuaHBTeX|pTeX)[^\n]*")

# a detail block stops as soon as a warning/box/page marker appears, so
# warnings after an error are never swallowed into the error detail
DETAIL_BREAK_RE = re.compile(
    r"^(LaTeX (Font )?Warning|Package\s+\S+\s+Warning|Class\s+\S+\s+Warning|"
    r"Overfull|Underfull|\[|\(Rerun )"
)


# --------------------------------------------------------------------------
def merge_wrapped_lines(lines):
    """Undo TeX's 79-column log wrapping: pdflatex hard-wraps at exactly
    MAX_PRINT_LINE columns, so only a line of exactly that length continues
    on the next line. Joining on >= caused unbounded cascades that swallowed
    every following warning into one giant line."""
    merged = []
    buf = None
    for raw in lines:
        line = raw.rstrip("\n")
        if buf is not None:
            line = buf + line
            buf = None
        if len(line) == MAX_PRINT_LINE:
            buf = line
            continue
        merged.append(line)
    if buf is not None:
        merged.append(buf)
    return merged


class FileStack(object):
    """Heuristic current-file tracking from the (file ... ) nesting in the log."""

    OPEN_RE = re.compile(
        r"\(((?:[A-Za-z]:)?[^\s()]{1,200}?\.(?:tex|sty|cls|fd|clo|def|cfg|aux|bbl|bbx|cbx|lbx|ltx|dtx))\b"
    )

    def __init__(self):
        self.stack = []

    def feed(self, line):
        """Process one line, maintaining the stack (best effort)."""
        pos = 0
        while True:
            m_open = self.OPEN_RE.search(line, pos)
            m_close = line.find(")", pos)
            if m_open and (m_close == -1 or m_open.start() < m_close):
                self.stack.append(m_open.group(1))
                pos = m_open.end()
            elif m_close != -1:
                if self.stack:
                    self.stack.pop()
                pos = m_close + 1
            else:
                break
        # pop entries opened on earlier lines and closed by ')' count drift:
        # heuristic only; we cap the stack to keep it sane
        if len(self.stack) > 64:
            del self.stack[32:]

    def current_tex(self):
        for name in reversed(self.stack):
            if name.lower().endswith((".tex", ".ltx")):
                return name
        return self.stack[-1] if self.stack else None


def classify(message, is_error):
    rules = ERROR_RULES if is_error else WARNING_RULES
    for category, pattern, hint in rules:
        if pattern is None:
            continue
        m = pattern.search(message)
        if m:
            extra = ""
            if category == "overfull_box":
                hint = BOX_HINT_OVER
            elif category == "underfull_box":
                hint = BOX_HINT_UNDER
            if category == "missing_package":
                pm = re.search(r"File `([^']+\.sty)' not found", message)
                if pm:
                    extra = " (package: %s)" % pm.group(1)
            return category, (hint or "") + extra
    cat, pattern, hint = rules[-1]
    return cat, hint


def extract_line(message, detail):
    m = INPUT_LINE_RE.search(message)
    if m:
        return int(m.group(1))
    m = LINES_RANGE_RE.search(message)
    if m:
        return int(m.group(1) or m.group(3))
    m = LINE_IN_ERROR_RE.search(detail)
    if m:
        return int(m.group(1))
    return None


def parse_log_text(text):
    """Return (errors, warnings, engine_hint) from a full .log text."""
    lines = merge_wrapped_lines(text.splitlines())
    errors = []
    warnings = []
    engine_hint = None
    stack = FileStack()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if engine_hint is None:
            m = ENGINE_RE.match(line)
            if m:
                engine_hint = line.strip()[:120]

        is_file_line_error = False
        msg = None
        err_file = None
        err_line = None
        fm = FILE_LINE_ERROR_RE.match(line)
        if fm and (ERROR_KEYWORD_RE.match(fm.group("msg")) or
                   fm.group("msg").startswith(("LaTeX Error", "Package ", "Class "))):
            is_file_line_error = True
            err_file = fm.group("file")
            err_line = int(fm.group("line"))
            msg = fm.group("msg")
        elif line.startswith("! "):
            msg = line[2:].strip()
        elif line == "!":
            msg = "(empty error message line)"

        if msg is not None:
            # capture the detail block: subsequent lines until a blank line
            # (after at least one content line) or the next error marker
            detail_lines = []
            j = i + 1
            while j < n:
                nxt = lines[j]
                if nxt.startswith("! ") or nxt == "!" or FILE_LINE_ERROR_RE.match(nxt):
                    break
                if DETAIL_BREAK_RE.match(nxt):
                    break
                if not detail_lines and nxt.startswith("l."):
                    detail_lines.append(nxt)
                    j += 1
                    continue
                if nxt.strip() == "":
                    if detail_lines:
                        break
                    j += 1
                    continue
                detail_lines.append(nxt)
                j += 1
                if len(detail_lines) >= 8:
                    break
            i = j - 1  # outer loop will i += 1
            detail = "\n".join(detail_lines)
            lnum = LINE_IN_ERROR_RE.search(detail)
            if err_line is None and lnum:
                err_line = int(lnum.group(1))
            file_src = "log_prefix" if err_file else None
            if err_file is None:
                cur = stack.current_tex()
                if cur:
                    err_file = cur
                    file_src = "paren_stack_heuristic"
                else:
                    err_file = "unknown"
                    file_src = "default"
            category, hint = classify(msg, is_error=True)
            errors.append({
                "file": err_file,
                "line": err_line,
                "message": msg[:400],
                "detail": detail[:600] if detail else "",
                "category": category,
                "fix_hint": hint,
                "file_source": file_src,
            })
        else:
            # warnings and box notices
            wmsg = None
            if line.startswith("LaTeX Warning: "):
                wmsg = line[len("LaTeX Warning: "):].strip()
            elif line.startswith("LaTeX Font Warning: "):
                wmsg = line[len("LaTeX Font Warning: "):].strip()
            else:
                pm = re.match(r"^(Package|Class) (\S+) Warning: (.*)$", line)
                if pm:
                    wmsg = "%s %s Warning: %s" % (pm.group(1), pm.group(2), pm.group(3).strip())
                else:
                    bm = re.match(r"^(Overfull|Underfull) \\([hv])box \(([^)]*)\)(.*)$", line)
                    if bm:
                        wmsg = line.strip()
            if wmsg:
                stack.feed(line)
                category, hint = classify(wmsg, is_error=False)
                wline = extract_line(wmsg, "")
                src = "default"
                cur = stack.current_tex()
                warnings.append({
                    "file": cur or "unknown",
                    "line": wline,
                    "message": wmsg[:400],
                    "category": category,
                    "fix_hint": hint or "",
                    "file_source": src,
                })
            else:
                stack.feed(line)
        i += 1
    return errors, warnings, engine_hint


def parse_blg_text(text, backend="bibtex"):
    """Parse BibTeX/Biber .blg output into warning/error items."""
    items = []
    if backend == "biber":
        for line in text.splitlines():
            if "WARN - " in line:
                items.append({"type": "warning", "category": "bibliography_problem",
                              "message": ("biber " + line.strip())[:400],
                              "file": None, "line": None,
                              "fix_hint": "Fix the .bib/.bcf data named in the message, then re-run biber."})
            elif "ERROR - " in line:
                items.append({"type": "error", "category": "bibliography_problem",
                              "message": ("biber " + line.strip())[:400],
                              "file": None, "line": None,
                              "fix_hint": "Biber failed: check data source syntax and the .bib entries cited."})
        return items
    # classic BibTeX
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Warning--"):
            items.append({"type": "warning", "category": "bibliography_problem",
                          "message": s[:400], "file": None, "line": None,
                          "fix_hint": "BibTeX data warning (usually a missing/duplicate field): fix the entry named, re-run bibtex + 2 compile rounds."})
        elif "---line" in s or s.startswith("I was expecting") or s.startswith("I found no "):
            items.append({"type": "error", "category": "bibliography_problem",
                          "message": s[:400], "file": None, "line": None,
                          "fix_hint": "BibTeX error: look for the entry/line number in the message and fix the .bib syntax; "
                                      "'I found no \\\\bibdata' means the compile round before bibtex was skipped."})
    return items


def parse_log_file(log_path, blg_path=None):
    try:
        with open(log_path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        return {"error": "cannot read log: %s" % exc}
    text = raw.decode("utf-8", errors="replace")
    if "\x00" in text[:2000]:  # UTF-16 log (rare, some editors)
        text = raw.decode("utf-16-le", errors="replace")
    errors, warnings, engine_hint = parse_log_text(text)
    if blg_path == "auto":
        cand = os.path.splitext(log_path)[0] + ".blg"
        blg_path = cand if os.path.isfile(cand) else None
    blg_items = []
    if blg_path and os.path.isfile(blg_path):
        try:
            with open(blg_path, "rb") as fh:
                blg_text = fh.read().decode("utf-8", errors="replace")
        except OSError:
            blg_text = ""
        backend = "biber" if "biber" in blg_text[:200].lower() or re.search(r"^\[.+\] ", blg_text, re.M) else "bibtex"
        blg_items = parse_blg_text(blg_text, backend=backend)
    for item in blg_items:
        if item["type"] == "error":
            errors.append({"file": item["file"], "line": item["line"],
                           "message": item["message"], "detail": "",
                           "category": item["category"], "fix_hint": item["fix_hint"],
                           "file_source": "blg"})
        else:
            warnings.append({"file": item["file"], "line": item["line"],
                             "message": item["message"], "category": item["category"],
                             "fix_hint": item["fix_hint"], "file_source": "blg"})

    categories = {}
    for it in errors + warnings:
        categories[it["category"]] = categories.get(it["category"], 0) + 1
    rerun_needed = any(w["category"] == "rerun_needed" for w in warnings)
    return {
        "log": os.path.abspath(log_path),
        "engine_hint": engine_hint,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "categories": categories,
            "rerun_needed": rerun_needed,
            "has_errors": bool(errors),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Parse a TeX .log into a categorized error/warning localization table (all errors, not just the first)."
    )
    ap.add_argument("log", help="path to the .log file")
    ap.add_argument("--blg", default=None, help="path to BibTeX/Biber .blg, or 'auto' to probe next to the log")
    ap.add_argument("--out", metavar="FILE", help="also write the JSON report to FILE")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.log):
        print(json.dumps({"error": "log file not found: %s" % args.log}, ensure_ascii=False))
        return 3
    report = parse_log_file(args.log, args.blg)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            print("warn: could not write --out: %s" % exc, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
