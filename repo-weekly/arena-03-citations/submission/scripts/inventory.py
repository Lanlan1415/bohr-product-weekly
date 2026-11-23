#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inventory.py — 清点输入目录材料，生成 materials_register.md（stdlib-only）。

只读输入目录，不修改任何输入文件；输出写到 --output 指定路径。
按绝对路径调用，不依赖当前工作目录（CWD）：

  python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md

文本层可读性探测策略（逐级降级）：
  1. 纯文本类扩展名：直接以 utf-8-sig 试读前 4KB；
  2. PDF：优先调用环境自带 pdftotext（pdf-text-tool）；不可用则尝试 pypdf / PyPDF2；
     仍不可用则降级为「仅登记」，绝不臆造内容；
  3. 其他二进制（docx/pptx/图片等）：仅登记，交由相应渲染工具处理。

退出码：0 = 清点完成（允许部分文件不可读）；1 = 输入目录不存在或输出无法写入。
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys

TEXT_EXTS = {".txt", ".md", ".tex", ".bib", ".ris", ".enw", ".nbib", ".ciw",
             ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".yaml", ".yml"}
PDF_EXTS = {".pdf"}
OFFICE_EXTS = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp"}


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0
    return "%d B" % n


def probe_text(path):
    """返回 (是否可读, 备注)。以 utf-8-sig 试读，失败则按 latin-1 兜底判断为疑似乱码。"""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="strict") as f:
            head = f.read(4096)
        return True, "utf-8 可读，前 4KB 共 %d 字符" % len(head)
    except (UnicodeDecodeError, ValueError):
        try:
            with open(path, "rb") as f:
                head = f.read(4096)
            head.decode("latin-1")
            return False, "非 utf-8 编码或含二进制内容，需转码后再读"
        except OSError as e:
            return False, "读取失败: %s" % e
    except OSError as e:
        return False, "读取失败: %s" % e


def probe_pdf(path):
    """逐级降级探测 PDF 文本层。"""
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-l", "2", path, "-"],
                               capture_output=True, timeout=60)
            txt = r.stdout.decode("utf-8", errors="replace")
            if r.returncode == 0 and len(txt.strip()) > 20:
                return True, "pdftotext 可读，前两页约 %d 字符" % len(txt.strip())
            if r.returncode == 0:
                return False, "pdftotext 未提取到文本（疑为扫描件，需 ocr-tool）"
            return False, "pdftotext 返回码 %d（文件可能损坏）" % r.returncode
        except (OSError, subprocess.TimeoutExpired):
            pass
    for modname in ("pypdf", "PyPDF2"):
        try:
            mod = __import__(modname)
            reader = mod.PdfReader(path)
            n = len(reader.pages)
            sample = ""
            for pg in reader.pages[:2]:
                sample += (pg.extract_text() or "")
            if len(sample.strip()) > 20:
                return True, "%s 可读，%d 页，前两页约 %d 字符" % (modname, n, len(sample.strip()))
            return False, "%s 可读但无文本层（疑为扫描件，需 ocr-tool）" % modname
        except ImportError:
            continue
        except Exception as e:  # 文件损坏等
            return False, "%s 解析失败: %s" % (modname, e)
    return False, "无可用 PDF 文本工具，仅登记"


def classify(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTS:
        return "文本", probe_text(path)
    if ext in PDF_EXTS:
        return "PDF", probe_pdf(path)
    if ext in OFFICE_EXTS:
        return "Office 文档", (False, "仅登记（用 office-renderer 处理）")
    if ext in IMG_EXTS:
        return "图片", (False, "仅登记（必要时用 ocr-tool）")
    return "其他", (False, "仅登记")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="清点输入目录材料并生成 materials_register.md（只读输入目录）。")
    ap.add_argument("--input", default="/input",
                    help="输入目录（默认 /input），只读，不会被修改")
    ap.add_argument("--output", required=True,
                    help="输出 materials_register.md 的绝对路径")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.input):
        print("[FAIL] 输入目录不存在: %s" % args.input)
        return 1

    rows = []
    for dirpath, _dirnames, filenames in os.walk(args.input):
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, args.input).replace(os.sep, "/")
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            kind, (readable, note) = classify(full)
            rows.append((rel, kind, size, readable, note))

    rows.sort(key=lambda r: r[0])
    lines = []
    lines.append("# 材料登记表 materials_register")
    lines.append("")
    lines.append("- 输入目录: `%s`（只读）" % args.input)
    lines.append("- 生成时间: %s" % datetime.datetime.now().isoformat(timespec="seconds"))
    lines.append("- 文件总数: %d；文本层可读: %d；需其他工具/仅登记: %d"
                 % (len(rows), sum(1 for r in rows if r[3]), sum(1 for r in rows if not r[3])))
    lines.append("")
    lines.append("| 编号 | 相对路径 | 类型 | 大小 | 文本层可读 | 备注 |")
    lines.append("|---|---|---|---|---|---|")
    for i, (rel, kind, size, readable, note) in enumerate(rows, 1):
        lines.append("| M%d | %s | %s | %s | %s | %s |"
                     % (i, rel, kind, human_size(size) if size >= 0 else "?",
                        "是" if readable else "否", note.replace("|", "\\|")))
    lines.append("")
    lines.append("> 说明：本表只做登记与可读性探测，不修改输入目录中的任何文件；"
                 "不可读条目后续用对应工具（pdf-text-tool / ocr-tool / office-renderer）处理，"
                 "不得以文件名臆测内容。")

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir and not os.path.isdir(outdir):
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as e:
            print("[FAIL] 无法创建输出目录 %s: %s" % (outdir, e))
            return 1
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        print("[FAIL] 输出写入失败 %s: %s" % (args.output, e))
        return 1

    print("[PASS] 清点完成: %d 个文件 -> %s" % (len(rows), args.output))
    for i, (rel, kind, size, readable, note) in enumerate(rows, 1):
        print("  M%d %-8s %-6s %s" % (i, kind, "可读" if readable else "登记", rel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
