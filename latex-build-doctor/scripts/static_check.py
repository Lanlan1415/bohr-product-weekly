#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""static_check.py -- degraded static checks for LaTeX sources (no TeX needed).

Runs entirely on the source text with only the Python standard library. Use it
when no TeX engine exists, or as a cheap pre-pass before compiling. It checks:

  * \\begin{X} / \\end{Y} pairing (stack-based, verbatim/comment aware)
  * brace balance ({} escapes respected)
  * math mode $ / $$ / \\( \\) / \\[ \\] pairing
  * \\ref family vs \\label matching (document-wide), duplicate labels
  * \\cite keys vs thebibliography \\bibitem and .bib keys
  * tabular column spec vs per-row & counts (rough check; \\multicolumn aware)
  * bare non-ASCII characters vs declared CJK/UTF-8 support
  * file encoding (strict UTF-8 decodability), missing \\documentclass

Usage:
    python -I static_check.py FILE.tex [FILE2.tex ...] [--out FILE] [--fail-on-error]
    python -I static_check.py --dir SRCDIR [...]

Output: one JSON object {files, issues:[{file,line,check,severity,message,fix_hint}], summary}.
Exit codes: 0 = checks ran; 3 = no input files found. --fail-on-error exits 1
when any severity=error issue was found (useful in CI); default is 0.
"""
import argparse
import bisect
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

VERBATIM_ENVS = {
    "verbatim", "verbatim*", "Verbatim", "Verbatim*", "minted", "lstlisting",
    "alltt", "filecontents", "filecontents*", "spverbatim",
}
ENV_RE = re.compile(r"\\(begin|end)\{([A-Za-z@]+\*?)\}")
TABLE_ENV_PREFIXES = ("tabular", "tabularx", "longtable", "tabu", "longtabu")
LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
REF_RE = re.compile(
    r"\\(?:ref|pageref|eqref|autoref|vref|Vref|cref|Cref|cpageref|Cpageref)\*?"
    r"(?:\[[^\]]*\])?\{([^{}]+)\}"
)
CITE_RE = re.compile(
    r"\\(?:cite|Cite|citep|citet|citealt|citealp|citeauthor|citeyear|citeyearpar|"
    r"parencite|textcite|pncite|tncite|autocite|footcite|footcitetext|"
    r"Citep|Citet|citeal|nocite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}"
)
BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^{}]+)\}")
BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\{([^{}]+)\}")
ADDBIBRESOURCE_RE = re.compile(r"\\(?:addbibresource|addglobalbib|addsectionbib)\[?[^\]]*\]?\{([^{}]+)\}")
BIBKEY_RE = re.compile(r"@\s*[A-Za-z]+\s*\{\s*([^,\s{}]+)\s*,")
NONVERBATIM_COMMENT_WARNING = "checks ignore verbatim/comment content by design"


# --------------------------------------------------------------------------
# preprocessing: blank out comments and verbatim content, preserve structure
# --------------------------------------------------------------------------

def preprocess(text):
    """Return (clean_text) where comments and verbatim bodies are replaced by
    spaces (line/column structure preserved)."""
    lines = text.splitlines()
    out_lines = []
    verbatim_env = None
    for line in lines:
        out = []
        j = 0
        L = len(line)
        if verbatim_env is not None:
            marker = "\\end{" + verbatim_env + "}"
            idx = line.find(marker)
            if idx >= 0:
                out.append(" " * idx)
                out.append(line[idx:])
                verbatim_env = None
            else:
                out.append(" " * L)
            out_lines.append("".join(out))
            continue
        while j < L:
            ch = line[j]
            if ch == "\\" and line.startswith("\\begin{", j):
                close = line.find("}", j + 7)
                if close != -1:
                    name = line[j + 7:close]
                    out.append(line[j:close + 1])
                    j = close + 1
                    if name in VERBATIM_ENVS:
                        verbatim_env = name
                        out.append(" " * (L - j))
                        j = L
                    continue
                out.append(ch)
                j += 1
                continue
            if ch == "\\" and line.startswith("\\verb", j):
                k = j + 5
                if k < L and line[k] == "*":
                    k += 1
                if k < L:
                    delim = line[k]
                    end = line.find(delim, k + 1)
                    if end == -1:
                        out.append(" " * (L - j))
                        j = L
                    else:
                        out.append(line[j:k + 1] + " " * (end - k - 1) + line[end])
                        j = end + 1
                    continue
                out.append(ch)
                j += 1
                continue
            if ch == "\\":
                if j + 1 < L:
                    out.append(line[j:j + 2])
                    j += 2
                else:
                    out.append(ch)
                    j += 1
                continue
            if ch == "%":
                out.append(" " * (L - j))
                j = L
                continue
            out.append(ch)
            j += 1
        out_lines.append("".join(out))
    return "\n".join(out_lines)


def line_index(clean_text):
    starts = [0]
    pos = clean_text.find("\n")
    while pos != -1:
        starts.append(pos + 1)
        pos = clean_text.find("\n", pos + 1)
    return starts


def line_of(starts, pos):
    return bisect.bisect_right(starts, pos)


def skip_group(text, i):
    """text[i] == '{'; return index just past the matching '}' (or len)."""
    depth = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


# --------------------------------------------------------------------------
# individual scans (each returns list of issue dicts, without 'file')
# --------------------------------------------------------------------------

def scan_envs(clean_text):
    issues = []
    stack = []
    starts = line_index(clean_text)
    for m in ENV_RE.finditer(clean_text):
        ln = line_of(starts, m.start())
        kind, name = m.group(1), m.group(2)
        if kind == "begin":
            stack.append((name, ln))
        else:
            if not stack:
                issues.append({
                    "line": ln, "check": "env_extra_end", "severity": "error",
                    "message": "\\end{%s} has no matching \\begin{%s}" % (name, name),
                    "fix_hint": "Delete this \\end{%s} or add the \\begin{%s} it belongs to." % (name, name),
                })
            else:
                top_name, top_ln = stack.pop()
                if top_name != name:
                    issues.append({
                        "line": ln, "check": "env_mismatch", "severity": "error",
                        "message": "\\begin{%s} (line %d) is closed by \\end{%s}" % (top_name, top_ln, name),
                        "fix_hint": "Change this to \\end{%s} (or fix the \\begin at line %d); nested environments must close innermost first." % (top_name, top_ln),
                    })
    for name, ln in stack:
        issues.append({
            "line": ln, "check": "env_unclosed", "severity": "error",
            "message": "\\begin{%s} (line %d) is never closed" % (name, ln),
            "fix_hint": "Add \\end{%s} at the right place (check nesting order)." % name,
        })
    return issues


def scan_braces(clean_text):
    issues = []
    stack = []
    starts = line_index(clean_text)
    i = 0
    n = len(clean_text)
    while i < n:
        ch = clean_text[i]
        if ch == "\n":
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            stack.append(line_of(starts, i))
        elif ch == "}":
            if stack:
                stack.pop()
            else:
                issues.append({
                    "line": line_of(starts, i), "check": "brace_extra_close", "severity": "error",
                    "message": "Unmatched '}' (no open group)",
                    "fix_hint": "Delete this '}' or add the '{' it closes; note \\{ \\} are literal braces.",
                })
        i += 1
    if stack:
        issues.append({
            "line": stack[0], "check": "brace_unclosed", "severity": "error",
            "message": "%d group(s) opened with '{' but never closed (first at line %d)" % (len(stack), stack[0]),
            "fix_hint": "Close the group(s); this is the usual root cause of 'Runaway argument' errors.",
        })
    return issues


def scan_math(clean_text):
    issues = []
    starts = line_index(clean_text)
    inline_open = None
    display_open = None
    paren_open = None    # \( ...
    bracket_open = None  # \[ ...
    i = 0
    n = len(clean_text)
    while i < n:
        ch = clean_text[i]
        if ch == "\n":
            i += 1
            continue
        if ch == "\\":
            nxt = clean_text[i + 1] if i + 1 < n else ""
            if nxt == "(":
                if paren_open is None:
                    paren_open = line_of(starts, i)
                i += 2
                continue
            if nxt == ")":
                if paren_open is None:
                    issues.append({
                        "line": line_of(starts, i), "check": "math_paren_unbalanced", "severity": "error",
                        "message": "\\) without a preceding \\(",
                        "fix_hint": "Remove the stray \\) or add the missing \\( ... \\) pair.",
                    })
                paren_open = None
                i += 2
                continue
            if nxt == "[":
                if bracket_open is None:
                    bracket_open = line_of(starts, i)
                i += 2
                continue
            if nxt == "]":
                if bracket_open is None:
                    issues.append({
                        "line": line_of(starts, i), "check": "math_bracket_unbalanced", "severity": "error",
                        "message": "\\] without a preceding \\[",
                        "fix_hint": "Remove the stray \\] or add the missing \\[ ... \\] display-math pair.",
                    })
                bracket_open = None
                i += 2
                continue
            i += 2
            continue
        if ch == "$":
            if i + 1 < n and clean_text[i + 1] == "$":
                if display_open is None:
                    display_open = line_of(starts, i)
                else:
                    display_open = None
                i += 2
                continue
            if inline_open is None:
                inline_open = line_of(starts, i)
            else:
                inline_open = None
            i += 1
            continue
        i += 1
    if inline_open is not None:
        issues.append({
            "line": inline_open, "check": "math_dollar_unbalanced", "severity": "error",
            "message": "Odd number of '$' characters: inline math opened on this line never closes",
            "fix_hint": "Count the '$' delimiters; the classic root cause is a missing closing $ (often 'Missing $ inserted' at compile time).",
        })
    if display_open is not None:
        issues.append({
            "line": display_open, "check": "math_display_unbalanced", "severity": "error",
            "message": "'$$' opened on this line has no closing '$$'",
            "fix_hint": "Prefer \\[ ... \\] over $$ ... $$; close the display math.",
        })
    if paren_open is not None:
        issues.append({
            "line": paren_open, "check": "math_paren_unbalanced", "severity": "error",
            "message": "\\( opened on this line has no closing \\)",
            "fix_hint": "Close the inline math with \\).",
        })
    if bracket_open is not None:
        issues.append({
            "line": bracket_open, "check": "math_bracket_unbalanced", "severity": "error",
            "message": "\\[ opened on this line has no closing \\]",
            "fix_hint": "Close the display math with \\].",
        })
    return issues


def scan_refs(clean_text):
    issues = []
    starts = line_index(clean_text)
    labels = {}
    used = {}
    for m in LABEL_RE.finditer(clean_text):
        key = m.group(1).strip()
        ln = line_of(starts, m.start())
        if key in labels:
            issues.append({
                "line": ln, "check": "label_duplicate", "severity": "error",
                "message": "\\label{%s} defined again (first at line %d)" % (key, labels[key]),
                "fix_hint": "Duplicate labels make \\ref pick the wrong target: rename one occurrence.",
            })
        else:
            labels[key] = ln
    for m in REF_RE.finditer(clean_text):
        ln = line_of(starts, m.start())
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                used.setdefault(key, []).append(ln)
    for key, lines_used in sorted(used.items()):
        if key not in labels:
            issues.append({
                "line": lines_used[0], "check": "ref_undefined", "severity": "error",
                "message": "\\ref-family command targets '%s' but no \\label{%s} exists anywhere" % (key, key),
                "fix_hint": "Add \\label{%s} next to the target (figure/table/section/equation), or fix the key typo; after fixing, rerun the compile rounds." % key,
            })
    for key in sorted(set(labels) - set(used)):
        issues.append({
            "line": labels[key], "check": "ref_unused", "severity": "info",
            "message": "\\label{%s} is never referenced (informational)" % key,
            "fix_hint": "Keep or remove; harmless for compilation.",
        })
    return issues


def scan_cites(clean_text, file_dir, issues_out):
    """Cite keys vs thebibliography / external .bib files (document scope)."""
    issues = issues_out
    starts = line_index(clean_text)
    cited = {}
    for m in CITE_RE.finditer(clean_text):
        ln = line_of(starts, m.start())
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                cited.setdefault(key, []).append(ln)
    bibitems = {}
    for m in BIBITEM_RE.finditer(clean_text):
        key = m.group(1).strip()
        bibitems.setdefault(key, line_of(starts, m.start()))
    bib_paths = []
    for m in BIBLIOGRAPHY_RE.finditer(clean_text):
        bib_paths.extend(p.strip() for p in m.group(1).split(","))
    for m in ADDBIBRESOURCE_RE.finditer(clean_text):
        bib_paths.append(m.group(1).strip())
    bib_keys = {}
    for p in bib_paths:
        path = p if os.path.isabs(p) else os.path.join(file_dir, p)
        if not os.path.splitext(path)[1]:
            path += ".bib"
        if os.path.isfile(path):
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                text = raw.decode("utf-8", errors="replace")
            except OSError:
                continue
            for bm in BIBKEY_RE.finditer(text):
                bib_keys.setdefault(bm.group(1), p)
        else:
            issues.append({
                "line": None, "check": "bib_file_missing", "severity": "warning",
                "message": "Bibliography file '%s' referenced but not found next to the sources" % p,
                "fix_hint": "Copy the .bib into the project or fix the path in \\bibliography{...}/\\addbibresource{...}.",
            })
    known = set(bibitems) | set(bib_keys)
    if known or bib_paths:
        for key, lines_used in sorted(cited.items()):
            if key not in known:
                issues.append({
                    "line": lines_used[0], "check": "cite_undefined", "severity": "error",
                    "message": "\\cite key '%s' has no matching \\bibitem or .bib entry" % key,
                    "fix_hint": "Add the entry (key: %s) to the .bib/\\bibitem list or fix the key; 'Citation ... undefined' at compile time traces back here." % key,
                })
    elif cited:
        issues.append({
            "line": None, "check": "bib_data_absent", "severity": "warning",
            "message": "%d cited key(s) but no \\bibitem or \\bibliography/\\addbibresource found" % len(cited),
            "fix_hint": "References cannot resolve: add the bibliography source.",
        })
    return issues


# ---- tables --------------------------------------------------------------

def parse_colspec(spec):
    """Count columns in a tabular preamble; None if too exotic to judge."""
    count = 0
    i = 0
    n = len(spec)
    while i < n:
        ch = spec[i]
        if ch in "lcr":
            count += 1
            i += 1
        elif ch in "pmbw":
            count += 1
            i += 1
            if i < n and spec[i] == "{":
                i = skip_group(spec, i)
        elif ch == "X":
            count += 1
            i += 1
        elif ch == "|":
            i += 1
        elif ch == " ":
            i += 1
        elif ch == "*":
            # *{n}{cols}
            if i + 1 < n and spec[i + 1] == "{":
                end1 = skip_group(spec, i + 1)
                inner = spec[i + 2:end1 - 1]
                if end1 < n and spec[end1] == "{":
                    end2 = skip_group(spec, end1)
                    body = spec[end1 + 1:end2 - 1]
                    try:
                        reps = int(inner.strip())
                    except ValueError:
                        return None
                    sub = parse_colspec(body)
                    if sub is None:
                        return None
                    count += reps * sub
                    i = end2
                    continue
                return None
            return None
        elif ch in "@!><":
            i += 1
            if i < n and spec[i] == "{":
                i = skip_group(spec, i)
        elif ch in "SV":  # siunitx S columns / val optionally with {...}
            count += 1
            i += 1
            if i < n and spec[i] == "{":
                i = skip_group(spec, i)
        else:
            return None
    return count


ROW_SPLIT_RE = re.compile(r"\\\\(?:\[[^\]]*\])?\*?")
HLINE_ONLY_RE = re.compile(r"^(?:\\(hline|midrule|toprule|bottomrule|hdashline|cline\s*\{[^}]*\}|cmidrule(lr)?(?:\{[^}]*\})?\{[^}]*\}|endhead|endfoot|endlastfoot|endfirsthead|noalign\s*\{[^}]*\}|rowcolor\{[^}]*\}|arraystretch|space|vspace\*?\{[^}]*\})\s*)+$")
MULTICOL_RE = re.compile(r"\\multicolumn\s*\{(\d+)\}")


def count_ampersands(row):
    """Top-level '&' count and multicolumn spans. Returns (cells, spans, has_multicolumn)."""
    amp = 0
    depth = 0
    i = 0
    n = len(row)
    cells = []
    cur_start = 0
    while i < n:
        ch = row[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "&" and depth == 0:
            amp += 1
            cells.append(row[cur_start:i])
            cur_start = i + 1
        i += 1
    cells.append(row[cur_start:])
    spans = 0
    has_multicolumn = False
    for cell in cells:
        m = MULTICOL_RE.search(cell.strip())
        if m and cell.strip().startswith("\\multicolumn"):
            spans += int(m.group(1))
            has_multicolumn = True
        else:
            spans += 1
    return amp + 1, spans, has_multicolumn


def find_matching_env_end(text, name, from_pos):
    """Index just past the \\end{name} matching the env assumed open at from_pos."""
    depth = 1
    for m in ENV_RE.finditer(text, from_pos):
        if m.group(2) == name:
            if m.group(1) == "begin":
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    return m.end()
    return None


def scan_table_region(text, issues, line_offset=0):
    """Check one tabular-like environment; text must start at \\begin{...}.
    line_offset = number of '\\n' to prepend conceptually (for nested checks).
    Returns the end index of the environment within `text`."""
    starts = line_index("\n" * line_offset + text)
    head = re.match(r"\s*\\begin\{([A-Za-z@]+\*?)\}", text)
    if not head:
        return 0
    name = head.group(1)
    begin_ln = line_of(starts, head.start())
    pos = head.end()
    n = len(text)
    while pos < n and text[pos] in " \t\n":
        pos += 1
    if pos < n and text[pos] == "[":
        close = text.find("]", pos)
        pos = close + 1 if close != -1 else head.end()
        while pos < n and text[pos] in " \t\n":
            pos += 1
    if pos >= n or text[pos] != "{":
        issues.append({
            "line": begin_ln, "check": "table_spec_unknown", "severity": "info",
            "message": "\\begin{%s} column spec not found in the expected place; rough check skipped" % name,
            "fix_hint": "No action needed; the check is heuristic.",
        })
        return head.end()
    spec_end = skip_group(text, pos)
    spec = text[pos + 1:spec_end - 1]
    ncols = parse_colspec(spec)
    end_idx = find_matching_env_end(text, name, spec_end)
    if end_idx is None:
        return spec_end  # unclosed: the env scan already reports it
    content = text[spec_end:end_idx]
    if ncols is None:
        issues.append({
            "line": begin_ln, "check": "table_spec_unknown", "severity": "info",
            "message": "Column spec '%s' uses syntax this rough check cannot count; skipped" % spec.strip()[:60],
            "fix_hint": "No action needed; verify columns manually.",
        })
        return end_idx
    # blank nested table environments (same length) and check them separately
    nested_spans = []
    work = content
    search_from = 0
    while True:
        found = None
        for mm in ENV_RE.finditer(work, search_from):
            if mm.group(1) == "begin" and any(mm.group(2).startswith(p) for p in TABLE_ENV_PREFIXES):
                found = mm
                break
        if found is None:
            break
        inner_end = find_matching_env_end(work, found.group(2), found.end())
        if inner_end is None:
            search_from = found.end()
            continue
        nested_spans.append(work[found.start():inner_end])
        work = work[:found.start()] + " " * (inner_end - found.start()) + work[inner_end:]
        search_from = found.start()
    # row splitting on the blanked copy
    row_bounds = []
    prev = 0
    for mm in ROW_SPLIT_RE.finditer(work):
        row_bounds.append((prev, mm.start()))
        prev = mm.end()
    row_bounds.append((prev, len(work)))
    for ridx, (a, b) in enumerate(row_bounds):
        row = work[a:b].replace("\n", " ")
        stripped = row.strip()
        if not stripped:
            continue
        if HLINE_ONLY_RE.match(stripped):
            continue
        cells, spans, has_mc = count_ampersands(row)
        total = spans if has_mc else cells
        if total != ncols:
            row_line = line_of(starts, spec_end + a)
            issues.append({
                "line": row_line, "check": "table_column_mismatch", "severity": "warning",
                "message": "Row %d in %s (spec '%s', %d column%s) has %s cell(s); rough check" % (
                    ridx + 1, name, spec.strip()[:30], ncols,
                    "" if ncols == 1 else "s", total),
                "fix_hint": "Fix the number of '&' in this row or the column spec; 'Extra alignment tab has been changed to \\cr' traces back here.",
            })
    # recurse into nested tables (pad with newlines so internal lines map upward)
    for span in nested_spans:
        pad = line_of(starts, spec_end) - 1
        scan_table_region(span, issues, line_offset=pad)
    return end_idx


def scan_tables(clean_text, issues):
    while True:
        found = None
        for m in ENV_RE.finditer(clean_text):
            if m.group(1) == "begin" and any(m.group(2).startswith(p) for p in TABLE_ENV_PREFIXES):
                found = m
                break
        if found is None:
            break
        consumed = scan_table_region(clean_text[found.start():], issues)
        if consumed <= 0:
            consumed = found.end() - found.start()
        # blank the region (same length) so it is not processed again
        clean_text = (clean_text[:found.start()]
                      + " " * consumed
                      + clean_text[found.start() + consumed:])
    return


# ---- encoding / unicode --------------------------------------------------

def scan_encoding_and_unicode(path, raw_bytes, clean_text, issues):
    try:
        raw_bytes.decode("utf-8")
        utf8_ok = True
    except UnicodeDecodeError:
        utf8_ok = False
    if not utf8_ok:
        issues.append({
            "line": None, "check": "encoding_suspect", "severity": "warning",
            "message": "File is NOT valid UTF-8 (probably GBK/Latin-1); pdflatex with \\usepackage[utf8]{inputenc} will fail",
            "fix_hint": "Re-save the file as UTF-8 (no BOM), or adapt the inputenc declaration.",
        })
    non_ascii_lines = []
    starts = line_index(clean_text)
    for idx, ch in enumerate(clean_text):
        if ord(ch) > 127:
            ln = line_of(starts, idx)
            if ln not in non_ascii_lines:
                non_ascii_lines.append(ln)
    if non_ascii_lines:
        preamble = clean_text.split("\\begin{document}")[0]
        cjk_support = bool(re.search(
            r"ctex|xeCJK|CJKutf8|luatexja|fontspec|inputenc\]{?utf8|\\usepackage\[utf8", preamble, re.I))
        issues.append({
            "line": non_ascii_lines[0], "check": "non_ascii", "severity": "info" if cjk_support else "warning",
            "message": "%d line(s) contain non-ASCII characters (first at line %d); %s" % (
                len(non_ascii_lines), non_ascii_lines[0],
                "declared CJK/UTF-8 support found in preamble" if cjk_support
                else "no CJK/UTF-8 declaration found in preamble"),
            "fix_hint": ("For pdflatex keep \\usepackage[utf8]{inputenc} and \\DeclareUnicodeCharacter for stragglers; "
                         "for CJK prefer xelatex/lualatex + ctex/xeCJK. 'Unicode character ... not set up' comes from this."),
        })
    return issues


# --------------------------------------------------------------------------
def check_file(path, doc_scope):
    """Static checks for one file. doc_scope collects document-wide data."""
    issues = []
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        issues.append({"line": None, "check": "read_error", "severity": "error",
                       "message": "cannot read file: %s" % exc, "fix_hint": ""})
        return issues, ""
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    clean = preprocess(text)
    issues.extend(scan_envs(clean))
    issues.extend(scan_braces(clean))
    issues.extend(scan_math(clean))
    issues.extend(scan_refs(clean))
    scan_tables(clean, issues)
    scan_encoding_and_unicode(path, raw, clean, issues)
    if not re.search(r"\\documentclass\b", clean):
        issues.append({
            "line": None, "check": "missing_documentclass", "severity": "error",
            "message": "No \\documentclass found; this cannot be a compilable main file",
            "fix_hint": "Add \\documentclass{...} (or treat this file as a sub-file included by the main file).",
        })
    elif "\\begin{document}" not in clean:
        issues.append({
            "line": None, "check": "missing_document_env", "severity": "warning",
            "message": "\\documentclass present but \\begin{document} missing",
            "fix_hint": "Wrap the body in \\begin{document} ... \\end{document}.",
        })
    doc_scope["cite_sources"].append((path, os.path.dirname(os.path.abspath(path)), clean))
    return issues, clean


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Static LaTeX source checks (env/brace/math pairing, ref-label, tables, encoding) without a TeX engine."
    )
    ap.add_argument("files", nargs="*", help=".tex files to check")
    ap.add_argument("--dir", help="check every .tex under this directory (round_logs excluded)")
    ap.add_argument("--out", metavar="FILE", help="write the JSON report to FILE")
    ap.add_argument("--fail-on-error", action="store_true", help="exit 1 when severity=error issues exist")
    args = ap.parse_args(argv)

    paths = list(args.files)
    if args.dir:
        for root, dirs, names in os.walk(args.dir):
            dirs[:] = [d for d in dirs if d not in ("round_logs",)]
            for name in sorted(names):
                if name.lower().endswith(".tex"):
                    paths.append(os.path.join(root, name))
    paths = [p for p in dict.fromkeys(paths) if os.path.isfile(p)]
    if not paths:
        print(json.dumps({"error": "no input .tex files found"}, ensure_ascii=False))
        return 3

    doc_scope = {"cite_sources": []}
    all_issues = []
    checked = []
    for p in paths:
        issues, _clean = check_file(p, doc_scope)
        checked.append(os.path.abspath(p))
        for it in issues:
            it["file"] = os.path.abspath(p)
            all_issues.append(it)
    # Document-wide reference checks: a child file may cite a label in main or
    # another included chapter. Per-file checks above are replaced here so a
    # real multi-file project is never punished for its boundaries.
    all_issues = [it for it in all_issues
                  if it.get("check") not in {"ref_undefined", "ref_unused", "label_duplicate"}]
    labels = {}
    used = {}
    has_main = False
    for path, _fdir, clean in doc_scope["cite_sources"]:
        if re.search(r"\\documentclass\b", clean):
            has_main = True
        starts = line_index(clean)
        for m in LABEL_RE.finditer(clean):
            key = m.group(1).strip()
            ln = line_of(starts, m.start())
            if key in labels:
                first_file, first_line = labels[key]
                all_issues.append({
                    "file": os.path.abspath(path), "line": ln, "check": "label_duplicate",
                    "severity": "error",
                    "message": "\\label{%s} defined again (first at %s:%d)" % (key, first_file, first_line),
                    "fix_hint": "Rename one occurrence across the project; duplicate labels make \\ref ambiguous.",
                })
            else:
                labels[key] = (os.path.abspath(path), ln)
        for m in REF_RE.finditer(clean):
            ln = line_of(starts, m.start())
            for key in m.group(1).split(","):
                key = key.strip()
                if key:
                    used.setdefault(key, []).append((os.path.abspath(path), ln))
    for key, locations in sorted(used.items()):
        if key not in labels:
            path, ln = locations[0]
            all_issues.append({
                "file": path, "line": ln, "check": "ref_undefined", "severity": "error",
                "message": "\\ref-family command targets '%s' but no project-level \\label{%s} exists" % (key, key),
                "fix_hint": "Add \\label{%s} beside the target or fix the key, then rebuild until stable." % key,
            })
    if not has_main:
        # No unrelated downgrade: absence of a main document is still an error.
        pass
    else:
        for it in all_issues:
            if it.get("check") == "missing_documentclass":
                it["severity"] = "info"
                it["message"] = "included source has no \\documentclass (valid when it is a child file)"
                it["fix_hint"] = "Check this file through the containing main document; it need not compile alone."

    # document-wide cite checks
    for path, fdir, clean in doc_scope["cite_sources"]:
        cite_issues = []
        scan_cites(clean, fdir, cite_issues)
        for it in cite_issues:
            it["file"] = os.path.abspath(path)
            all_issues.append(it)
    all_issues.sort(key=lambda it: (it["file"], it.get("line") is None, it.get("line") or 0))

    sev_counts = {"error": 0, "warning": 0, "info": 0}
    check_counts = {}
    for it in all_issues:
        sev_counts[it["severity"]] = sev_counts.get(it["severity"], 0) + 1
        check_counts[it["check"]] = check_counts.get(it["check"], 0) + 1

    report = {
        "files": checked,
        "issues": all_issues,
        "summary": {
            "file_count": len(checked),
            "issue_count": len(all_issues),
            "by_severity": sev_counts,
            "by_check": check_counts,
            "note": "rough/heuristic checks are labeled in each message; verbatim and comment content is excluded",
        },
    }
    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
        except OSError as exc:
            print("warn: could not write --out: %s" % exc, file=sys.stderr)
    if args.fail_on_error and sev_counts["error"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
