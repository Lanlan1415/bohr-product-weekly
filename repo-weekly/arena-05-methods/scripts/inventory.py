#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inventory.py — 材料清点：扫描输入目录，生成 materials_register.md（材料登记表）。

用法：
    python3 /skills/weekly-skill/scripts/inventory.py --input /input --out /app/work/materials_register.md

规则：
- 只读输入目录，不修改任何输入文件；
- 文本类文件用 utf-8-sig 试读以判断文本层可读性；
- PDF 若系统存在 pdftotext 则试抽前两页文本层，否则降级为“仅登记（无文本层判定工具）”；
- 仅使用 Python 标准库；不依赖网络；不依赖当前工作目录（CWD）。

退出码：0 成功；1 失败（如输入目录不存在、输出路径不可写）。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

TEXT_EXTS = {
    ".txt", ".md", ".tex", ".bib", ".json", ".yaml", ".yml", ".csv", ".tsv",
    ".log", ".cfg", ".ini", ".toml", ".py", ".sh", ".xml", ".html", ".htm",
    ".sty", ".cls", ".ipynb", ".r", ".m", ".c", ".cpp", ".h", ".java",
}
SAMPLE_CHARS = 2000


def classify_text_file(path):
    """返回 (状态字符串, 摘要首行)。用 utf-8-sig 试读。"""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="strict") as f:
            sample = f.read(SAMPLE_CHARS)
        first = next((ln.strip() for ln in sample.splitlines() if ln.strip()), "")
        return "文本可读", first[:120]
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                sample = f.read(SAMPLE_CHARS)
            first = next((ln.strip() for ln in sample.splitlines() if ln.strip()), "")
            return "部分可读(含非法字节)", first[:120]
        except OSError as exc:
            return f"不可读({exc})", ""
    except OSError as exc:
        return f"不可读({exc})", ""


def classify_pdf(path):
    """尝试用 pdftotext 抽取文本层；无工具则降级登记。"""
    tool = shutil.which("pdftotext")
    if not tool:
        return "仅登记(无pdftotext,文本层未判定)", ""
    tmpdir = tempfile.mkdtemp(prefix="inv_")
    tmpout = os.path.join(tmpdir, "out.txt")
    try:
        proc = subprocess.run(
            [tool, "-l", "2", path, tmpout],
            capture_output=True, timeout=60,
        )
        if proc.returncode == 0 and os.path.exists(tmpout):
            with open(tmpout, "r", encoding="utf-8-sig", errors="replace") as f:
                sample = f.read(SAMPLE_CHARS)
            if sample.strip():
                first = next((ln.strip() for ln in sample.splitlines() if ln.strip()), "")
                return "PDF文本层可读", first[:120]
            return "PDF无文本层(可能为扫描件,需OCR)", ""
        return "pdftotext抽取失败(退出码%s)" % proc.returncode, ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return "pdftotext异常(%s)" % exc, ""
    finally:
        try:
            if os.path.exists(tmpout):
                os.remove(tmpout)
            os.rmdir(tmpdir)
        except OSError:
            pass


def scan(input_dir):
    rows = []
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, input_dir).replace(os.sep, "/")
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            ext = os.path.splitext(name)[1].lower()
            if ext == ".pdf":
                status, first = classify_pdf(path)
            elif ext in TEXT_EXTS:
                status, first = classify_text_file(path)
            else:
                status, first = "二进制/未识别类型(仅登记)", ""
            rows.append((rel, ext or "(无扩展名)", size, status, first))
    return rows


def render_register(input_dir, rows):
    lines = []
    lines.append("# 材料登记表（materials_register）")
    lines.append("")
    lines.append("扫描目录：`%s`" % input_dir.replace(os.sep, "/"))
    lines.append("")
    lines.append("| # | 相对路径 | 类型 | 大小(字节) | 可读性 | 首行摘要 |")
    lines.append("|---|----------|------|-----------|--------|----------|")
    for i, (rel, ext, size, status, first) in enumerate(rows, 1):
        first = first.replace("|", "\\|")
        lines.append("| S%d | `%s` | %s | %d | %s | %s |" % (i, rel, ext, size, status, first))
    lines.append("")
    lines.append("> 说明：编号 S1..Sn 即后文 [S#] 来源标记的材料编号；"
                 "“仅登记”的文件需人工或借助环境工具（pdf-text-tool / ocr-tool）进一步读取。")
    return "\n".join(lines) + "\n"


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="材料清点：扫描输入目录并生成 materials_register.md（stdlib-only，只读输入）。"
    )
    parser.add_argument("--input", required=True, help="输入材料目录，如 /input")
    parser.add_argument("--out", required=True, help="输出登记表路径，如 /app/work/materials_register.md")
    args = parser.parse_args(argv)

    input_dir = os.path.abspath(args.input)
    if not os.path.isdir(input_dir):
        print("错误：输入目录不存在：%s" % input_dir, file=sys.stderr)
        return 1

    rows = scan(input_dir)
    if not rows:
        print("警告：输入目录为空：%s" % input_dir, file=sys.stderr)

    out_path = os.path.abspath(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(render_register(input_dir, rows))
    except OSError as exc:
        print("错误：无法写出登记表：%s" % exc, file=sys.stderr)
        return 1

    print("已登记材料 %d 项 -> %s" % (len(rows), out_path.replace(os.sep, "/")))
    for rel, ext, size, status, _ in rows:
        print("  [%s] %s (%s, %d bytes)" % (status, rel.replace(os.sep, "/"), ext, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
