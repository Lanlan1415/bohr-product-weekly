"""Web-page body extraction: cut navigation, ads, related-article and reference-list
noise out of reader-supplied page text, and keep every kept paragraph's original
position so a translation can be traced back to the page.

The input is the text a reader (or a fetch step) got from the page — this module is
the 正文识别 half of web reading: what stays, what goes, and why, with the full cut
list recorded instead of silent deletion. Footnote and page-furniture lines are cut
as their own classes, so a reader can audit exactly what was removed and why.
"""

from __future__ import annotations

import re

# Line shapes that are never body text on a paper page. Each is a reason, not a
# regex to silently delete on: every cut is recorded with its matched text.
NOISE_PATTERNS = (
    ("nav", re.compile(r"^(首页|目录|导航|搜索|登录|注册|订阅|分享|下载 PDF|下一篇|上一篇|"
                       r"订阅期刊|Related articles?|Navigation|Search|Sign in|Subscribe|"
                       r"Download PDF|Skip to (main )?content|Back to top)\s*$", re.I)),
    ("ads", re.compile(r"(广告|Advertisement|Sponsored|Promoted|广告链接)\s*$", re.I)),
    ("related", re.compile(r"^(相关文章|Related|You may also like|类似论文|推荐阅读)\b.*$", re.I)),
    ("citation-list", re.compile(r"^\[\d+\]\s|^\d{1,3}\.\s+[A-Z][a-z]+ [A-Z]")),
    ("citation-list",
     re.compile(r"^[A-Z][a-z]+ [A-Z](?:'s)? [a-z(].*\(19|20\d{2}\)")),  # APA: Author A (2020) ...
    ("footnote", re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳¹²³⁴⁵⁶⁷⁸⁹⁰]"
                            r"|^(注\s*[：:]|注释\s*[：:]|Notes?\s*[：:]|※)")),
    ("page-furniture", re.compile(r"^(第\s*\d+\s*页|Page \d+ of \d+|共\s*\d+\s*页|"
                                  r"Copyright|©|All rights reserved|版权所有)", re.I)),
)

# Lines that OPEN a reference section: from here to the next heading (or EOF) is a
# citation list, whichever style each line uses.
REFERENCE_SECTION_HEADING = re.compile(
    r"^(References|参考文献|Reference list|Bibliography|文献列表)\s*$", re.I)

HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+\S.{0,58}|\d+\.\s+\S.{0,58}|"
    r"(Abstract|Introduction|Background|Methods|Materials and methods|Results|"
    r"Discussion|Conclusion|Conclusions|References|Acknowledg(e)?ments?|"
    r"摘要|引言|背景|方法|材料与方法|结果|讨论|结论|致谢)\s*)$", re.I)


def _is_heading(text: str) -> bool:
    s = text.strip()
    if len(s) <= 60 and not s.endswith((".", "。", "！", "？", "?", "!")):
        if HEADING_RE.match(s):
            return True
    return False


def _is_caption(text: str) -> bool:
    return bool(re.match(r"^(图|表|Figure|Table|Fig\.)\s*\d+", text.strip(), re.I))


def classify_line(line: str) -> str:
    """body / noise with the matched class name, so the cut list can name each cut."""
    s = str(line or "").strip()
    if not s:
        return "blank"
    for name, pat in NOISE_PATTERNS:
        if pat.search(s):
            return name
    return "body"


def extract_body(text: str) -> dict:
    """Split page text into kept body paragraphs and a recorded cut list.

    Paragraphs keep their original index (the position on the page), so a per-paragraph
    translation can always point back to the exact source paragraph. Consecutive body
    lines merge into one paragraph; headings (short lines ending without punctuation,
    or numbered headings) stay as their own paragraphs with the heading flag; captions
    (Figure/Table lines) stay as their own paragraphs with the caption flag.
    """
    kept: list[dict] = []
    cuts: list[dict] = []
    buffer: list[tuple[int, str]] = []

    def flush():
        if not buffer:
            return
        idxs = [i for i, _ in buffer]
        text = " ".join(s for _, s in buffer)
        kept.append({"first_line": idxs[0], "last_line": idxs[-1],
                     "text": text, "heading": _is_heading(text)})
        buffer.clear()

    in_ref_section = False
    for i, raw in enumerate(str(text or "").splitlines()):
        # A References/参考文献 heading opens a span that is a citation list until the
        # next heading — the span closes there, so an Appendix after References stays.
        is_heading_line = _is_heading(raw.strip())
        if in_ref_section and is_heading_line and \
                not REFERENCE_SECTION_HEADING.match(raw.strip()):
            in_ref_section = False
        if REFERENCE_SECTION_HEADING.match(raw.strip()):
            flush()
            cuts.append({"line": i, "class": "citation-list",
                         "text": raw.strip()[:80]})
            in_ref_section = True
            continue
        kind = "citation-list" if in_ref_section and not is_heading_line else classify_line(raw)
        if kind == "blank":
            flush()
            continue
        if kind == "body":
            if _is_heading(raw.strip()):
                # A heading forms its own paragraph immediately: merging it into the
                # following body text would hide the segment a translation targets.
                flush()
                buffer.append((i, raw.strip()))
                flush()
                continue
            if _is_caption(raw.strip()):
                flush()
                kept.append({"first_line": i, "last_line": i, "text": raw.strip(),
                             "heading": False, "caption": True})
                continue
            buffer.append((i, raw.strip()))
            continue
        flush()
        cuts.append({"line": i, "class": kind, "text": raw.strip()[:80]})
    flush()

    return {"body": kept, "cuts": cuts,
            "lines_total": len(str(text or "").splitlines()),
            "lines_kept": len(kept)}
