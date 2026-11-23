#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 结构清点与章节树抽取（文献文档解析技能，stdlib-only）。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/pdf_survey.py \
        --pdf /input/paper.pdf \
        --output /app/work/survey

行为：
  1. 结构清点（纯字节级启发式，不依赖第三方库）：
     页数、图片对象数、字体对象数、是否加密、是否含书签大纲标题；
  2. 若 pdftotext 可用：导出 -layout 与 -raw 两份全文文本到输出目录，
     统计每页字符量，判定文字层有无；缺失 pdftotext 时降级为"仅结构清点"并登记；
  3. 从 -layout 文本中按编号模式（1 / 1.1 / 1.1.1）与常见未编号章节名
     抽取章节树，写出 section_tree.md（启发式结果，需人工抽查）；
  4. 异常分级：blocker（加密等阻断）/ major（无文字层等）/ minor（页数不一致、
     疑似多栏等），写入 survey.json 的 anomalies 数组；
  5. v2 新增——OCR 页覆盖清单：逐页统计非空白字符量，列出**哪些页必须走 OCR**
     （ocr_pages 数组 + ocr_coverage.md 人类可读声明，须照抄进主产物的
     "OCR 页覆盖声明"，禁止跳过 OCR 页却声称全覆盖）；
  6. v2 新增——表格区域几何登记：按"行内大间隙"启发式定位候选表格区域
     （页码 + 行区间 + 列间隙 x 位置），写出 table_registry.md 并登记进
     survey.json 的 table_regions，供表格结构还原指回（traceable geometry）；
  7. v2 新增——分块处理：--first-page/--last-page 透传给 pdftotext 的 -f/-l，
     900 秒预算下大 PDF 按页块分次清点，导出的 layout/raw 文本落盘复用，
     禁止对同一 PDF 重复全量提取（dense-page 重复解析是已知的预算杀手）。

退出码：0 清点完成（即使存在异常，异常只写入报告）；1 致命错误
（文件不存在、不是 PDF、输出目录不可写）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

RE_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")
RE_PAGES_COUNT = re.compile(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", re.S)
RE_IMAGE = re.compile(rb"/Subtype\s*/Image(?![A-Za-z])")
RE_BASEFONT = re.compile(rb"/BaseFont")
RE_TITLE = re.compile(rb"/Title\s*\(((?:\\.|[^\\)])*)\)")

# 常见未编号章节名（英中），用于章节树抽取
UNNUMBERED_HEADS = (
    "abstract", "summary", "keywords", "key words", "introduction",
    "background", "methods", "methodology", "materials and methods",
    "experimental", "experiments", "results", "discussion",
    "results and discussion", "conclusion", "conclusions",
    "acknowledgement", "acknowledgements", "acknowledgment",
    "references", "bibliography", "supporting information",
    "appendix", "supplementary",
    "摘要", "关键词", "关键字", "引言", "绪论", "实验部分", "实验",
    "结果与讨论", "结果", "讨论", "结论", "致谢", "参考文献", "附录",
)

# 编号章节行：如 "1 Introduction"、"2.3 Results and discussion"、"3.1.2 xxx"
RE_NUMBERED_HEAD = re.compile(
    r"^\s{0,12}([1-9]\d{0,1}(?:\.\d{1,2}){0,3})[.)]?\s{1,4}(\S.{1,78}?)\s*$")
# 疑似多栏：行内部出现 >=3 个连续空格分隔的两段文字
RE_COL_GAP = re.compile(r"\S\s{3,}\S")


def unescape_pdf_literal(raw):
    """还原 PDF 字面字符串中的转义序列。"""
    out = bytearray()
    i = 0
    mapping = {110: 10, 114: 13, 116: 9, 98: 8, 102: 12, 40: 40, 41: 41, 92: 92}
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):
            n = raw[i + 1]
            if n in mapping:
                out.append(mapping[n]); i += 2; continue
            if 48 <= n <= 55:  # 至多 3 位八进制
                j = i + 1
                digits = []
                while j < len(raw) and len(digits) < 3 and 48 <= raw[j] <= 55:
                    digits.append(raw[j]); j += 1
                out.append(int(bytes(digits), 8) & 0xFF); i = j; continue
            out.append(n); i += 2; continue
        out.append(c); i += 1
    return bytes(out)


def decode_pdf_string(raw):
    """把 PDF 字符串字节解码为可读文本（UTF-16 带 BOM 优先）。"""
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", "replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", "replace")


def extract_outline_titles(data, limit=60):
    """从原始字节中启发式提取书签大纲 /Title 条目。"""
    titles = []
    for m in RE_TITLE.finditer(data):
        text = decode_pdf_string(unescape_pdf_literal(m.group(1))).strip()
        if text and text not in titles:
            titles.append(text)
        if len(titles) >= limit:
            break
    return titles


def run_pdftotext(pdftotext, mode, pdf_path, out_path, timeout=300,
                  first_page=None, last_page=None):
    """运行 pdftotext，返回 (成功与否, 文本, 错误信息)。

    first_page/last_page 透传给 pdftotext 的 -f/-l，用于大 PDF 分块提取。
    """
    cmd = [pdftotext, mode, "-enc", "UTF-8"]
    if first_page is not None:
        cmd += ["-f", str(first_page)]
    if last_page is not None:
        cmd += ["-l", str(last_page)]
    cmd += [pdf_path, out_path]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (False, "", "%s: %s" % (type(exc).__name__, exc))
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        return (False, "", err or "pdftotext 返回非零退出码")
    try:
        with open(out_path, "r", encoding="utf-8-sig") as fh:
            return (True, fh.read(), "")
    except OSError as exc:
        return (False, "", "读取 pdftotext 输出失败：%s" % exc)


def per_page_stats(layout_text, first_page=1, min_chars=20):
    """逐页统计非空白字符量，判定每页路线（文字层 / 需 OCR）。

    返回 (page_stats, ocr_pages)：
      page_stats = [{"page": n, "chars": c, "route": "text"|"ocr-candidate"}]
      ocr_pages  = 需走 OCR 的物理页码列表（OCR 页覆盖清单的数据源）
    pdftotext 每页以 \\f 收尾；first_page 为页块起始物理页码（分块处理时 >1）。
    """
    pages = layout_text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    stats = []
    for i, ptext in enumerate(pages):
        nchars = sum(1 for ch in ptext if not ch.isspace())
        stats.append({
            "page": first_page + i,
            "chars": nchars,
            "route": "text" if nchars >= min_chars else "ocr-candidate",
        })
    ocr_pages = [p["page"] for p in stats if p["route"] == "ocr-candidate"]
    return stats, ocr_pages


def detect_table_regions(layout_text, first_page=1, max_regions=200):
    """表格区域几何登记（启发式）：连续"行内大间隙"行聚成候选表格区域。

    返回 [{"region_id", "page", "line_span", "gap_columns", "rows"}]：
      - page/line_span：区域在文本视图中的可溯源位置；
      - gap_columns：行内大间隙的 x 起始列（近似列边界，traceable geometry）；
      - rows：区域内文本行数。
    候选区域需人工/视觉复核确认是否真为表格（method_rules §3、§9）。
    """
    regions = []
    pages = layout_text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    for pidx, ptext in enumerate(pages):
        run_start = None
        run_lines = []
        lines = ptext.splitlines()
        for lno, line in enumerate(lines + [""]):
            gaps = [m.start() for m in re.finditer(r"\S\s{3,}(?=\S)", line)] if line else []
            if len(gaps) >= 1 and line.strip():
                if run_start is None:
                    run_start = lno
                    run_lines = []
                run_lines.append((lno, gaps))
            else:
                if run_lines and len(run_lines) >= 2:
                    # 至少 2 个连续大间隙行才算候选表格区域
                    col_pos = sorted({g for _lno, gs in run_lines[:5] for g in gs})
                    regions.append({
                        "region_id": "T%03d" % (len(regions) + 1),
                        "page": first_page + pidx,
                        "line_span": [run_start + 1, run_lines[-1][0] + 1],
                        "gap_columns": col_pos[:12],
                        "rows": len(run_lines),
                    })
                run_start = None
                run_lines = []
        if len(regions) >= max_regions:
            break
    return regions[:max_regions]


def extract_section_tree(text):
    """从全文中抽取章节树（启发式）。

    返回列表 [(level, number, title)]；level 从 1 起，未编号章节 level=1。
    """
    tree = []
    seen_unnumbered = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 90:
            continue
        m = RE_NUMBERED_HEAD.match(line)
        if m:
            num, title = m.group(1), m.group(2).strip()
            # 排除正文句子：以标点结尾或词数过多的行不像标题
            if title[-1] in ".,;，。；：" or len(title.split()) > 12:
                continue
            level = num.count(".") + 1
            tree.append((level, num, title))
            continue
        low = stripped.lower().rstrip(".:")
        if low in UNNUMBERED_HEADS and low not in seen_unnumbered:
            seen_unnumbered.add(low)
            tree.append((1, "", stripped.rstrip(".:")))
    return tree


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PDF 结构清点与章节树抽取（stdlib-only，pdftotext 可选）")
    parser.add_argument("--pdf", required=True, help="待清点 PDF 的绝对路径")
    parser.add_argument("--output", required=True,
                        help="输出目录绝对路径，例如 /app/work/survey")
    parser.add_argument("--pdftotext", default=None,
                        help="pdftotext 绝对路径（缺省自动在 PATH 中查找）")
    parser.add_argument("--min-chars-per-page", type=int, default=20,
                        help="判定有文字层的每页平均非空白字符下限（默认 20）")
    parser.add_argument("--first-page", type=int, default=None,
                        help="只清点从该页起的页块（透传 pdftotext -f；大 PDF 分块用）")
    parser.add_argument("--last-page", type=int, default=None,
                        help="只清点至该页为止（透传 pdftotext -l；大 PDF 分块用）")
    args = parser.parse_args(argv)

    pdf_path = os.path.abspath(args.pdf)
    if not os.path.isfile(pdf_path):
        sys.stderr.write("[pdf_survey] 错误：文件不存在：%s\n" % pdf_path)
        return 1
    out_dir = os.path.abspath(args.output)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        sys.stderr.write("[pdf_survey] 错误：输出目录不可创建：%s（%s）\n" % (out_dir, exc))
        return 1

    with open(pdf_path, "rb") as fh:
        data = fh.read()
    if b"%PDF" not in data[:1024]:
        sys.stderr.write("[pdf_survey] 错误：文件头不含 %%PDF，不是有效 PDF：%s\n" % pdf_path)
        return 1

    anomalies = []

    # ---- 1. 字节级结构清点 ----
    encrypted = b"/Encrypt" in data
    if encrypted:
        anomalies.append({
            "level": "blocker", "code": "ENCRYPTED",
            "detail": "检测到 /Encrypt：PDF 加密，常规文本提取会失败；"
                      "需先确认权限/解除加密，否则转 OCR 或登记 partial。"})

    page_count = len(RE_PAGE.findall(data))
    count_candidates = [int(m.group(1)) for m in RE_PAGES_COUNT.finditer(data)]
    if count_candidates:
        page_count = max(page_count, max(count_candidates))
    image_count = len(RE_IMAGE.findall(data))
    font_count = len(RE_BASEFONT.findall(data))
    outline_titles = extract_outline_titles(data)

    # ---- 2. pdftotext 文本层 ----
    pdftotext = args.pdftotext or shutil.which("pdftotext")
    text_layer = None
    layout_chars = raw_chars = 0
    text_pages = 0
    layout_text = ""
    page_stats, ocr_pages, table_regions = [], [], []
    base = os.path.splitext(os.path.basename(pdf_path))[0]

    if pdftotext is None:
        anomalies.append({
            "level": "minor", "code": "NO_PDFTOTEXT",
            "detail": "未找到 pdftotext，本次仅做字节级结构清点；"
                      "文本层判断与章节树抽取降级为“未执行”。"
                      "fallback 路线：pdf-render-tool 渲染页面 → OCR；"
                      "若环境预装 PyMuPDF，可在交互中作为提取 fallback"
                      "（本脚本保持 stdlib-only，不硬依赖）。"})
    else:
        ok_l, layout_text, err_l = run_pdftotext(
            pdftotext, "-layout", pdf_path, os.path.join(out_dir, base + ".layout.txt"),
            first_page=args.first_page, last_page=args.last_page)
        ok_r, raw_text, err_r = run_pdftotext(
            pdftotext, "-raw", pdf_path, os.path.join(out_dir, base + ".raw.txt"),
            first_page=args.first_page, last_page=args.last_page)
        if not ok_l:
            anomalies.append({
                "level": "major", "code": "EXTRACT_FAIL",
                "detail": ("pdftotext -layout 执行失败：%s；疑似加密/损坏。"
                           "fallback 路线：pdf-render-tool 渲染页面 → OCR；"
                           "若环境预装 PyMuPDF 可在交互中作为提取 fallback。"
                           "按异常流程处理，不得猜测内容。"
                           % (err_l.strip().splitlines()[0] if err_l.strip()
                              else "pdftotext 失败"))})
        else:
            layout_chars = sum(1 for ch in layout_text if not ch.isspace())
            # pdftotext 每页以 \f 收尾（含末页），故 \f 数即页数；无 \f 时按有无文本兜底
            text_pages = layout_text.count("\f") or (1 if layout_text.strip() else 0)
            denom = max(text_pages, 1)
            text_layer = (layout_chars / denom) >= args.min_chars_per_page
            if not text_layer:
                anomalies.append({
                    "level": "major", "code": "NO_TEXT_LAYER",
                    "detail": "每页平均非空白字符 %.1f < %d：疑似扫描件/图片型 PDF，"
                              "须转 OCR 路线且所有 OCR 文本置信度从 low 起标。"
                              % (layout_chars / denom, args.min_chars_per_page)})
            if ok_r:
                raw_chars = sum(1 for ch in raw_text if not ch.isspace())
                if layout_chars and abs(raw_chars - layout_chars) / max(layout_chars, 1) > 0.3:
                    anomalies.append({
                        "level": "minor", "code": "ORDER_RISK",
                        "detail": "-raw 与 -layout 字符量差异 >30%%：版面复杂，"
                                  "阅读顺序必须逐页人工抽查。"})
            gap_lines = sum(1 for ln in layout_text.splitlines() if RE_COL_GAP.search(ln))
            total_lines = max(len([ln for ln in layout_text.splitlines() if ln.strip()]), 1)
            if gap_lines / total_lines > 0.15:
                anomalies.append({
                    "level": "minor", "code": "MULTI_COLUMN",
                    "detail": "约 %.0f%% 文本行含大间隙：疑似多栏版面，"
                              "必须按栏切分并验证栏序，禁止直接通读拼接。"
                              % (100.0 * gap_lines / total_lines)})
            if page_count and text_pages and abs(text_pages - page_count) > 0:
                anomalies.append({
                    "level": "minor", "code": "PAGE_MISMATCH",
                    "detail": "字节级页数 %d 与文本页数 %d 不一致（启发式）："
                              "可能存在缺页、空白页或对象流压缩，需人工核对。"
                              % (page_count, text_pages)})

            # ---- 2b. OCR 页覆盖清单 + 表格区域几何登记（v2）----
            page_stats, ocr_pages = per_page_stats(
                layout_text, first_page=(args.first_page or 1),
                min_chars=args.min_chars_per_page)
            if text_layer and ocr_pages:
                anomalies.append({
                    "level": "major", "code": "PARTIAL_TEXT_LAYER",
                    "detail": "以下页面文字层极稀，必须走 OCR 并在交付中显式列出："
                              "p.%s。禁止跳过这些页却声称全覆盖。"
                              % ", ".join(str(p) for p in ocr_pages[:40])})
            table_regions = detect_table_regions(
                layout_text, first_page=(args.first_page or 1))
            if table_regions:
                anomalies.append({
                    "level": "minor", "code": "TABLE_REGIONS",
                    "detail": "登记 %d 个候选表格区域（见 table_registry.md）："
                              "表格块必须指回 region_id，图片型表格标 [NOT_READABLE]。"
                              % len(table_regions)})

    # ---- 2c. ocr_coverage.md（OCR 页覆盖声明，须照抄进主产物）----
    cov_path = os.path.join(out_dir, "ocr_coverage.md")
    cov_lines = ["# OCR 页覆盖声明（由 pdf_survey.py 生成，须照抄进 parsed_document.md）", ""]
    if not page_stats:
        cov_lines.append("- 文本层未提取（pdftotext 不可用或失败）：本声明无法自动给出页级清单，")
        cov_lines.append("  必须人工逐页判定哪些页走 OCR，并在此补全后照抄进主产物。")
    else:
        cov_lines.append("- 判定阈值：每页非空白字符 ≥ %d 视为有文字层。" % args.min_chars_per_page)
        cov_lines.append("")
        cov_lines.append("| 页码 | 非空白字符数 | 路线 |")
        cov_lines.append("|---|---|---|")
        for p in page_stats:
            cov_lines.append("| p.%d | %d | %s |"
                             % (p["page"], p["chars"],
                                "文字层直提" if p["route"] == "text" else "**必须 OCR**"))
        cov_lines.append("")
        if ocr_pages:
            cov_lines.append("**走 OCR 的页（必须显式列出，禁止漏报）：p.%s**"
                             % ", p.".join(str(p) for p in ocr_pages))
            cov_lines.append("")
            cov_lines.append("这些页的全部文本 conf 从 low 起标，且须经视觉复核"
                             "（pdf-render-tool 渲染页面人工检查）并留痕。")
        else:
            cov_lines.append("本次清点范围内没有需要走 OCR 的页。")
        if args.first_page or args.last_page:
            cov_lines.append("")
            cov_lines.append("> 注意：本次为分块清点（页块 p.%s–p.%s），"
                             "合并各块清单后才是全文 OCR 页覆盖声明。"
                             % (args.first_page or 1, args.last_page or "末"))
    cov_lines.append("")
    try:
        with open(cov_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(cov_lines))
    except OSError as exc:
        sys.stderr.write("[pdf_survey] 错误：写 ocr_coverage.md 失败：%s\n" % exc)
        return 1

    # ---- 2d. table_registry.md（表格区域几何登记）----
    reg_path = os.path.join(out_dir, "table_registry.md")
    reg_lines = ["# 表格区域几何登记（启发式候选，需人工/视觉复核）", ""]
    if table_regions:
        reg_lines.append("| region_id | 页码 | 文本行区间 | 近似列间隙 x 位置 | 行数 |")
        reg_lines.append("|---|---|---|---|---|")
        for r in table_regions:
            reg_lines.append("| %s | p.%d | %d–%d | %s | %d |"
                             % (r["region_id"], r["page"],
                                r["line_span"][0], r["line_span"][1],
                                ", ".join(str(x) for x in r["gap_columns"]), r["rows"]))
        reg_lines.append("")
        reg_lines.append("用法：步骤 4 解析表格时，每个表格块在 evidence_map 中指回对应 "
                         "region_id；确认不是表格的区域标记“已排除”。")
    else:
        reg_lines.append("- 未检测到候选表格区域（或文本层未提取）。")
    reg_lines.append("")
    try:
        with open(reg_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(reg_lines))
    except OSError as exc:
        sys.stderr.write("[pdf_survey] 错误：写 table_registry.md 失败：%s\n" % exc)
        return 1

    # ---- 3. 章节树抽取 ----
    tree = extract_section_tree(layout_text) if layout_text else []
    tree_path = os.path.join(out_dir, "section_tree.md")
    tree_lines = ["# 章节树（启发式抽取，需人工抽查）", ""]
    if outline_titles:
        tree_lines.append("## PDF 书签大纲（/Title 原始条目）")
        tree_lines.append("")
        for t in outline_titles:
            tree_lines.append("- %s" % t)
        tree_lines.append("")
    tree_lines.append("## 正文扫描得到的章节标题")
    tree_lines.append("")
    if tree:
        for level, num, title in tree:
            indent = "  " * (level - 1)
            label = ("%s %s" % (num, title)) if num else title
            tree_lines.append("%s- %s" % (indent, label))
    else:
        tree_lines.append("- （未抽到；可能无文字层或标题模式不匹配，降级为人工通读定位）")
    tree_lines.append("")
    try:
        with open(tree_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(tree_lines))
    except OSError as exc:
        sys.stderr.write("[pdf_survey] 错误：写章节树失败：%s\n" % exc)
        return 1

    # ---- 4. survey.json ----
    survey = {
        "pdf": pdf_path.replace(os.sep, "/"),
        "file_size_bytes": len(data),
        "page_count_heuristic": page_count,
        "image_object_count": image_count,
        "font_object_count": font_count,
        "encrypted": encrypted,
        "outline_titles": outline_titles,
        "pdftotext": pdftotext or None,
        "text_layer_present": text_layer,
        "layout_chars": layout_chars,
        "raw_chars": raw_chars,
        "text_pages": text_pages,
        "page_range": {"first_page": args.first_page, "last_page": args.last_page},
        "page_stats": page_stats,
        "ocr_pages": ocr_pages,
        "ocr_coverage_statement": (
            "走 OCR 的页：p.%s" % ", p.".join(str(p) for p in ocr_pages)
            if ocr_pages else "本次清点范围内没有需要走 OCR 的页"),
        "table_regions": table_regions,
        "section_headings_found": len(tree),
        "anomalies": anomalies,
        "notes": "页数/对象数均为字节级启发式统计；对象流压缩时可能低估，"
                 "结论以人工抽查为准。本脚本只读输入文件。"
                 "ocr_pages 为必须走 OCR 的页码清单，须照抄进主产物的 OCR 页覆盖声明。",
    }
    survey_path = os.path.join(out_dir, "survey.json")
    try:
        with open(survey_path, "w", encoding="utf-8") as fh:
            json.dump(survey, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        sys.stderr.write("[pdf_survey] 错误：写 survey.json 失败：%s\n" % exc)
        return 1

    print("[pdf_survey] %s" % pdf_path)
    print("  页数(启发式): %d | 图片对象: %d | 字体对象: %d | 加密: %s"
          % (page_count, image_count, font_count, "是" if encrypted else "否"))
    print("  文字层: %s | 章节标题: %d 个 | 书签: %d 条"
          % ("未检测" if text_layer is None else ("有" if text_layer else "无/极稀"),
             len(tree), len(outline_titles)))
    for a in anomalies:
        print("  异常[%s] %s: %s" % (a["level"], a["code"], a["detail"]))
    if page_stats:
        print("  OCR 页覆盖: %s"
              % ("需 OCR 的页 p.%s" % ", p.".join(str(p) for p in ocr_pages)
                 if ocr_pages else "无需 OCR 页（本页块）"))
        print("  候选表格区域: %d 个（table_registry.md）" % len(table_regions))
    print("  输出: %s , %s , %s , %s" % (survey_path, tree_path, cov_path, reg_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
