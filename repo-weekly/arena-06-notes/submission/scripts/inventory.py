# -*- coding: utf-8 -*-
"""inventory.py — 材料清点脚本（阅读10：文献总结与结构化笔记）

只读清点输入目录中的科研材料，生成 materials_register.md（S1..Sn 登记）。
对每个文件记录：来源编号、文件名、类型、大小、文本层可读性。
PDF 优先尝试 pdftotext（环境 pdf-text-tool）；不可用时降级为"仅登记"，
绝不臆造文本内容。

用法：
    python inventory.py <input_dir> --out <materials_register.md>

退出码：0 成功；1 输入目录不存在或不可读；2 参数错误。
仅使用 Python 标准库；读文件一律 utf-8-sig；只读输入目录；
不依赖当前工作目录（CWD），所有路径由参数绝对给出。
"""
import argparse
import os
import shutil
import subprocess
import sys

TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".tex"}
PDF_EXTS = {".pdf"}


def sniff_text_file(path, max_bytes=65536):
    """尝试读取文本文件开头，返回 (可读, 摘要说明)。"""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="strict") as f:
            head = f.read(2000)
    except (UnicodeDecodeError, OSError) as exc:
        return False, "文本读取失败: %s" % exc
    n_chars = len(head.strip())
    if n_chars == 0:
        return False, "文件可读但前 2000 字符为空"
    return True, "文本层可读（前 %d 字符采样正常）" % n_chars


def sniff_pdf(path):
    """尝试用 pdftotext 探测 PDF 文本层；失败则降级为仅登记。"""
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return None, "环境无 pdftotext，仅登记（可读性待运行时确认）"
    try:
        proc = subprocess.run(
            [pdftotext, "-l", "2", path, "-"],
            capture_output=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "pdftotext 调用失败: %s" % exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return False, "pdftotext 报错: %s" % (err[0] if err else "未知错误")
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    if len(text) < 20:
        return False, "PDF 前两页几乎无文本层（疑似扫描件，需 OCR）"
    return True, "PDF 文本层可读（前两页提取 %d 字符）" % len(text)


def collect(input_dir):
    rows = []
    for root, _dirs, files in os.walk(input_dir):
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, input_dir).replace(os.sep, "/")
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            ext = os.path.splitext(name)[1].lower()
            if ext in TEXT_EXTS:
                ok, note = sniff_text_file(path)
                kind = "text"
            elif ext in PDF_EXTS:
                ok, note = sniff_pdf(path)
                kind = "pdf"
            else:
                ok, note = None, "非文本类型，仅登记"
                kind = ext.lstrip(".") or "unknown"
            rows.append({
                "rel": rel, "kind": kind, "size": size,
                "readable": ok, "note": note,
            })
    rows.sort(key=lambda r: r["rel"])
    return rows


def render_register(input_dir, rows):
    lines = []
    lines.append("# 材料登记表（materials_register）")
    lines.append("")
    lines.append("输入目录：`%s`" % input_dir.replace(os.sep, "/"))
    lines.append("说明：本表由 scripts/inventory.py 自动生成；编号 S1..Sn 是全文统一的来源锚点前缀。")
    lines.append("")
    lines.append("| 编号 | 文件 | 类型 | 大小(字节) | 文本层可读性 | 备注 |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        if r["readable"] is True:
            state = "可读"
        elif r["readable"] is False:
            state = "不可直接读"
        else:
            state = "未探测"
        size = str(r["size"]) if r["size"] >= 0 else "未知"
        lines.append("| S%d | %s | %s | %s | %s | %s |" % (
            i, r["rel"], r["kind"], size, state, r["note"]))
    lines.append("")
    unread = [r for r in rows if r["readable"] is False]
    if unread:
        lines.append("## 需要降级处理的材料")
        lines.append("")
        for r in unread:
            lines.append("- %s：%s" % (r["rel"], r["note"]))
        lines.append("")
        lines.append("处置建议：扫描件走 OCR；加密/权限受限文档在笔记中标注“材料不可读”，")
        lines.append("相关字段记为“未报告（材料不可读）”，不得臆造内容。")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="清点输入材料并生成 materials_register.md（只读输入目录）")
    ap.add_argument("input_dir", help="输入材料目录（绝对路径，如 /input）")
    ap.add_argument("--out", required=True,
                    help="输出登记表路径（绝对路径，如 /app/work/materials_register.md）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.input_dir):
        print("错误：输入目录不存在或不可读：%s" % args.input_dir)
        return 1
    rows = collect(args.input_dir)
    if not rows:
        print("警告：输入目录为空：%s" % args.input_dir)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    content = render_register(os.path.abspath(args.input_dir), rows)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(content)
    print("已登记 %d 个材料 -> %s" % (len(rows), args.out))
    for i, r in enumerate(rows, 1):
        print("  S%d %s (%s, %s bytes)" % (i, r["rel"], r["kind"], r["size"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
