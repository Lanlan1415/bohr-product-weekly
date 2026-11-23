#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""材料清点脚本：登记输入目录中的全部材料文件，输出 materials_register.md。

用途：学术语言润色任务的第 1 步——先弄清"手里有什么材料、能不能读出文本层"，
再决定润色策略。每个文件分配来源编号 S1, S2, ...，供后续事实/来源映射使用。

用法：
    python inventory.py --input /input --output /app/work/materials_register.md

约束（玻尔产品周赛统一规范）：
- 仅使用 Python 标准库；读取文本一律 utf-8-sig；
- 只读输入目录，绝不修改输入文件；结果只写到 --output 指定路径；
- 不依赖当前工作目录（CWD），所有路径均以命令行参数为准；
- PDF 文本层探测优先调用 pdftotext（若系统存在），失败一律降级为"仅登记"，
  不因此中断整个清点流程。
"""

import argparse
import os
import shutil
import subprocess
import sys

TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".tsv", ".xml", ".tex",
             ".yaml", ".yml", ".html", ".htm", ".rst", ".bib"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def classify(ext):
    if ext == ".pdf":
        return "PDF"
    if ext in TEXT_EXTS:
        return "文本"
    if ext in IMAGE_EXTS:
        return "图像"
    return "其他"


def probe_text(path):
    """尝试以 utf-8-sig 读取文本文件，返回 (是否可读, 说明)。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            head = f.read(200000)
        return True, "可读，约 %d 字符（前 200KB 采样）" % len(head)
    except UnicodeDecodeError:
        return False, "非 UTF-8 编码或含二进制段，需人工转码"
    except OSError as exc:
        return False, "读取失败：%s" % exc


def probe_pdf(path):
    """尝试用 pdftotext 探测 PDF 文本层；不可用时降级为仅登记。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return False, "系统无 pdftotext，仅登记（可用 pdf-text-tool 另行解析）"
    try:
        proc = subprocess.run(
            [exe, path, "-"], capture_output=True, timeout=120)
        out = proc.stdout.decode("utf-8-sig", errors="replace").strip()
        if proc.returncode == 0 and len(out) > 50:
            return True, "文本层可提取，约 %d 字符" % len(out)
        return False, "pdftotext 无可用输出（可能是扫描件，需要 OCR）"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "pdftotext 调用失败（%s），仅登记" % exc


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="清点输入目录材料，生成带来源编号的 materials_register.md")
    parser.add_argument("--input", required=True, help="输入材料目录（只读）")
    parser.add_argument("--output", required=True, help="登记表输出路径（.md）")
    args = parser.parse_args()

    in_dir = os.path.abspath(args.input)
    if not os.path.isdir(in_dir):
        print("[FAIL] 输入目录不存在：%s" % in_dir)
        return 1

    entries = []
    for root, _dirs, files in os.walk(in_dir):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, in_dir).replace(os.sep, "/")
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            ext = os.path.splitext(name)[1].lower()
            kind = classify(ext)
            if kind == "文本":
                ok, note = probe_text(full)
            elif kind == "PDF":
                ok, note = probe_pdf(full)
            else:
                ok, note = False, "非文本材料，仅登记（如需内容请用对应工具解析）"
            entries.append({
                "path": rel, "size": size, "kind": kind,
                "readable": ok, "note": note,
            })
    entries.sort(key=lambda e: e["path"])
    for i, e in enumerate(entries, 1):
        e["sid"] = "S%d" % i

    lines = []
    lines.append("# 材料登记表（materials_register）")
    lines.append("")
    lines.append("- 输入目录：`%s`" % in_dir.replace(os.sep, "/"))
    lines.append("- 文件总数：%d" % len(entries))
    lines.append("- 说明：本表由 inventory.py 自动生成；来源编号 S# 在后续证据挂接、"
                 "evidence_map 与 result.json 中保持一致，不得中途重排。")
    lines.append("")
    lines.append("| 来源编号 | 相对路径 | 类型 | 大小（字节） | 文本可读性 | 备注 |")
    lines.append("|---|---|---|---|---|---|")
    for e in entries:
        lines.append("| %s | %s | %s | %d | %s | %s |" % (
            e["sid"], e["path"], e["kind"], e["size"],
            "是" if e["readable"] else "否", e["note"]))
    lines.append("")
    lines.append("## 后续动作")
    lines.append("")
    lines.append("1. 对'文本可读性=否'的条目，用 pdf-text-tool / ocr-tool 补解析，"
                 "解析结果另存到工作目录并在本表备注；仍读不出的在 result.json 的"
                 " uncertainty 中说明。")
    lines.append("2. 逐篇确认每篇论文的 DOI / 标题 / 作者归属，尤其不要把清单中"
                 "第一篇的根 DOI 套到第二篇（见 task.md 输入修订）。")
    lines.append("3. 若存在 corpus-manifest.json，以其列出的 DOI、来源哈希与许可证"
                 "为准核对本表。")
    lines.append("")

    out_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("[OK] 已登记 %d 个文件 -> %s" % (len(entries), out_path))
    for e in entries:
        print("  %s  %-8s %-6s %s" % (
            e["sid"], e["kind"], "可读" if e["readable"] else "登记", e["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
