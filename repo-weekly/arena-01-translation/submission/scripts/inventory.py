#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""材料清点脚本（文献翻译技能）：清点输入目录并生成材料登记表。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/inventory.py \
        --input /input \
        --output /app/work/materials_register.md

行为：
  * 逐个登记输入目录中的文件：编号 S1..Sn、文件名、类型、大小；
  * 对 PDF 尝试探测文本层：优先调用 pdftotext（PATH 或 --pdftotext 指定），
    判断"有文字层 / 疑似无文字层（扫描件）"——这决定后续翻译的原文获取路线；
  * 对纯文本/Markdown 统计字符数与行数，便于估算分段翻译工作量；
  * v2 新增——多栏版面警告：文字层正常但行内大间隙比例高时，
    在登记表中提示"疑似多栏版面"，分段前必须先验证栏序；
  * pdftotext 不可用或执行失败时降级为"仅登记"，绝不中断清点；
  * 只读输入目录，不做任何修改；输出写到 --output 指定路径。

约束：仅使用 Python 标准库；读取文本一律 utf-8-sig；不访问网络。
退出码：0 成功；1 参数错误 / 输入目录不存在 / 输出不可写。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

# 疑似多栏：行内部出现 >=3 个连续空格分隔的两段文字（v2 多栏版面警告）
RE_COL_GAP = re.compile(r"\S\s{3,}\S")

KIND_MAP = {
    ".pdf": "PDF 文档",
    ".md": "Markdown 文本",
    ".txt": "纯文本",
    ".json": "JSON 数据",
    ".csv": "表格(CSV)",
    ".tsv": "表格(TSV)",
    ".xml": "XML 数据",
    ".png": "图片(PNG)",
    ".jpg": "图片(JPEG)",
    ".jpeg": "图片(JPEG)",
    ".html": "HTML 页面",
    ".docx": "Word 文档",
    ".tex": "LaTeX 源文件",
}

TEXT_EXTS = (".md", ".txt", ".tsv", ".csv", ".tex", ".html")


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0
    return "%d B" % n


def probe_pdf_text_layer(pdf_path, pdftotext, pages=3, timeout=60):
    """用 pdftotext 探测 PDF 前几页文本层；任何失败降级为登记说明。"""
    if not pdftotext:
        return ("未探测（pdftotext 不可用，仅登记）", 0)
    try:
        proc = subprocess.run(
            [pdftotext, "-layout", "-l", str(pages), "-enc", "UTF-8", pdf_path, "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ("探测失败（%s），仅登记" % type(exc).__name__, 0)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = err[0] if err else "未知错误"
        return ("探测失败（pdftotext: %s），疑似加密或损坏，仅登记" % detail, 0)
    text = proc.stdout.decode("utf-8", "replace")
    nchars = sum(1 for ch in text if not ch.isspace())
    # v2 新增：多栏版面警告——行内大间隙成列出现即提示先验证栏序再分段
    gap_lines = sum(1 for ln in text.splitlines() if RE_COL_GAP.search(ln))
    total_lines = max(len([ln for ln in text.splitlines() if ln.strip()]), 1)
    col_note = ""
    if nchars >= 50 and gap_lines / total_lines > 0.15:
        col_note = ("；⚠ 疑似多栏版面（约 %.0f%% 行含大间隙）：分段前必须验证栏序"
                    "（左栏读完→右栏），禁止照抄文本流物理顺序"
                    % (100.0 * gap_lines / total_lines))
    if nchars >= 50:
        return ("有文字层（前 %d 页约 %d 字符），可直接分段翻译%s"
                % (pages, nchars, col_note), nchars)
    return ("疑似无文字层/扫描件（前 %d 页仅 %d 字符），需 OCR 后再译" % (pages, nchars), nchars)


def probe_text_file(fpath):
    """统计纯文本文件的字符数与行数（utf-8-sig 读取）。"""
    try:
        with open(fpath, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return "读取失败（编码非 UTF-8？），仅登记"
    nchars = sum(1 for ch in text if not ch.isspace())
    nlines = text.count("\n") + 1
    return "约 %d 字符 / %d 行" % (nchars, nlines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="清点输入目录，生成材料登记表 materials_register.md（stdlib-only）")
    parser.add_argument("--input", required=True,
                        help="输入目录绝对路径，例如 /input（只读）")
    parser.add_argument("--output", required=True,
                        help="登记表输出绝对路径，例如 /app/work/materials_register.md")
    parser.add_argument("--pdftotext", default=None,
                        help="pdftotext 可执行文件绝对路径（缺省自动在 PATH 中查找）")
    args = parser.parse_args(argv)

    in_dir = os.path.abspath(args.input)
    if not os.path.isdir(in_dir):
        sys.stderr.write("[inventory] 错误：输入目录不存在或不是目录：%s\n" % in_dir)
        return 1

    pdftotext = args.pdftotext or shutil.which("pdftotext")

    entries = []
    for name in sorted(os.listdir(in_dir)):
        fpath = os.path.join(in_dir, name)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(name)[1].lower()
        kind = KIND_MAP.get(ext, "其他(%s)" % (ext or "无扩展名"))
        size = os.path.getsize(fpath)
        note = ""
        if ext == ".pdf":
            note, _ = probe_pdf_text_layer(fpath, pdftotext)
        elif ext in TEXT_EXTS:
            note = probe_text_file(fpath)
        entries.append((name, kind, size, note))

    lines = []
    lines.append("# 材料登记表（materials_register）")
    lines.append("")
    lines.append("- 输入目录：`%s`" % in_dir.replace(os.sep, "/"))
    lines.append("- 文件总数：%d" % len(entries))
    lines.append("- pdftotext：%s" % (pdftotext if pdftotext else "未找到（PDF 仅登记，未探测文本层）"))
    lines.append("- 说明：本表由 scripts/inventory.py 自动生成；输入目录全程只读。")
    lines.append("")
    lines.append("| 编号 | 文件名 | 类型 | 大小 | 文本层/规模 |")
    lines.append("|---|---|---|---|---|")
    for i, (name, kind, size, note) in enumerate(entries, start=1):
        lines.append("| S%d | %s | %s | %s | %s |"
                     % (i, name, kind, human_size(size), note or "-"))
    lines.append("")
    lines.append("## 后续动作提示")
    lines.append("")
    lines.append("- 原文获取路线：有文字层 PDF/纯文本 → 直接分段编号（步骤 2）；扫描件 → 先 OCR，且 OCR 错字不擅自改。")
    lines.append("- 若有术语表类文件（.tsv/.csv/.md），在步骤 3 优先采用为既有术语来源并登记。")
    lines.append("- case.json 必须另有 contract_notes.md 逐字段记录 output_contract（主流程步骤 0）。")
    lines.append("")

    out_path = os.path.abspath(args.output)
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except OSError as exc:
        sys.stderr.write("[inventory] 错误：输出不可写：%s（%s）\n" % (out_path, exc))
        return 1

    print("[inventory] 已登记 %d 个文件 -> %s" % (len(entries), out_path))
    for i, (name, kind, size, note) in enumerate(entries, start=1):
        print("  S%d  %s  %s  %s  %s" % (i, name, kind, human_size(size), note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
