#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mapping_check.py — 原编号 ↔ 新编号双向映射表校验（stdlib-only）。

引用插入/删除/合并/重排之后，必须交付一张**可执行**的编号映射表
（模板见 templates/numbering_map_template.md），使评审与作者能从新编号
找回原编号（回溯），也能从原编号查到去向（保留/合并/删除）。本脚本校验：

  ERROR：
  1. 同一原编号出现两次且去向冲突（映射不是函数）；
  2. 两个「保留」条目的新编号相同（碰撞，双向映射不成立）；
  3. 保留条目的新编号不构成 1..N 连续序列（断号）；
  4. 给了 --manuscript 时：正文引用的 [n] 不在映射表保留集合内
     （正文编号与映射表脱节）。
  WARN：
  5. 被删除/被合并的原编号（提示确认均已在 change_log 记录）；
  6. 未提供 --manuscript（无法核对正文一致性）。

用法（绝对路径调用，不依赖 CWD，只读输入文件）：
  python3 /skills/weekly-skill/scripts/mapping_check.py \
      --map /app/output/numbering_map.md \
      --manuscript /app/output/manuscript_revised.md \
      --output /app/output/mapping_check_report.md

退出码：0 = 映射表自洽（允许 WARN）；1 = 存在 ERROR 或输入不可读。
"""
import argparse
import os
import re
import sys

NUM_MARK = re.compile(r"\[(\d[\d\s,，、\-–—]*)\]")


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def parse_map(text):
    """解析映射表。支持 markdown 表格行与原教旨文本行两种形态：
      | 原编号 | 新编号 | 去向 | 备注 |   （新编号列可填 - 表示删除）
      3 -> 2 保留 / 3 -> - 删除
    返回 [(old:int, new:int|None, action:str, 行号)]，表头/分隔行自动跳过。
    """
    rows = []
    for ln, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        cells = None
        if s.startswith("|"):
            parts = [c.strip().strip("*") for c in s.strip("|").split("|")]
            if len(parts) >= 2 and re.fullmatch(r"\d+", parts[0] or ""):
                cells = parts
        else:
            m = re.match(r"^(\d+)\s*(?:->|→|=>)\s*(\d+|-|—)\s*(.*)$", s)
            if m:
                cells = [m.group(1), m.group(2), m.group(3)]
        if not cells:
            continue
        old = int(cells[0])
        new = None if cells[1] in ("-", "—", "") else int(cells[1])
        action = cells[2] if len(cells) > 2 else ("保留" if new is not None else "删除")
        if new is None:
            action = action or "删除"
        rows.append((old, new, action, ln))
    return rows


def expand(tok):
    out = set()
    for part in re.split(r"[,，、]", tok):
        part = part.strip()
        m = re.match(r"^(\d+)\s*[-–—]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b <= 9999:
                out.update(range(a, b + 1))
        elif part.isdigit():
            out.add(int(part))
    return out


def split_body(text):
    m = None
    for m in re.finditer(r"^[#\s\d\.、]*(?:参考文献|REFERENCES?|References)\s*[:：]?\s*$",
                         text, re.M):
        pass
    return text[:m.start()] if m else text


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="原编号<->新编号双向映射表校验：函数性/无碰撞/连续性/与正文一致。")
    ap.add_argument("--map", required=True, dest="map_path",
                    help="编号映射表（markdown 或文本）绝对路径")
    ap.add_argument("--manuscript", default=None,
                    help="修订稿绝对路径（可选；提供则核对正文 [n] 与映射一致）")
    ap.add_argument("--output", required=True, help="校验报告 markdown 输出绝对路径")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.map_path):
        print("[FAIL] 映射表不存在: %s" % args.map_path)
        return 1
    try:
        map_text = read_text(args.map_path)
    except OSError as e:
        print("[FAIL] 映射表读取失败: %s" % e)
        return 1

    rows = parse_map(map_text)
    errors, warns = [], []
    if not rows:
        errors.append("映射表未解析出任何数据行（期望 | 原编号 | 新编号 | 去向 | 或 '3 -> 2 保留'）")

    # 1. 函数性：同一原编号去向冲突
    by_old = {}
    for old, new, action, ln in rows:
        if old in by_old and by_old[old][0] != new:
            errors.append("原编号 [%d] 出现冲突去向：新号 %s（行 %d） vs %s（行 %d）"
                          % (old, by_old[old][0], by_old[old][1], new, ln))
        by_old.setdefault(old, (new, ln))

    # 2. 碰撞：两个保留条目共用新编号
    by_new = {}
    for old, new, action, ln in rows:
        if new is None:
            continue
        if new in by_new:
            errors.append("新编号 [%d] 碰撞：原编号 [%d]（行 %d）与 [%d]（行 %d）同为保留去向，"
                          "双向映射不成立" % (new, by_new[new][0], by_new[new][1], old, ln))
        else:
            by_new[new] = (old, ln)

    # 3. 连续性：保留新编号应为 1..N
    retained_new = sorted(by_new)
    if retained_new:
        expect = list(range(1, len(retained_new) + 1))
        if retained_new != expect:
            errors.append("保留条目的新编号不连续：实际 %s，应为 %s（断号须整体重排）"
                          % (retained_new, expect))

    # 5. 删除/合并提示
    dropped = [(old, action) for old, new, action, _ln in rows if new is None]
    if dropped:
        warns.append("被删除/合并的原编号：%s——确认每条均已在 change_log 写明理由"
                     % ", ".join("[%d](%s)" % (o, a or "删除") for o, a in dropped))

    # 4. 与正文一致性
    if args.manuscript:
        if not os.path.isfile(args.manuscript):
            errors.append("稿件不存在: %s" % args.manuscript)
        else:
            try:
                body = split_body(read_text(args.manuscript))
                cited = set()
                for m in NUM_MARK.finditer(body):
                    cited |= expand(m.group(1))
                stray = sorted(cited - set(by_new))
                if stray:
                    errors.append("正文引用的 %s 不在映射表保留集合内——正文编号与映射表脱节"
                                  % ", ".join("[%d]" % n for n in stray))
            except OSError as e:
                errors.append("稿件读取失败: %s" % e)
    else:
        warns.append("未提供 --manuscript，跳过正文 [n] 与映射表一致性核对")

    L = []
    L.append("# 编号映射表校验报告")
    L.append("")
    L.append("- 映射表: `%s`（%d 行映射）" % (args.map_path, len(rows)))
    L.append("- 稿件: `%s`" % (args.manuscript or "（未提供）"))
    L.append("- 结论: ERROR %d 项 / WARN %d 项 -> **%s**"
             % (len(errors), len(warns), "FAIL" if errors else "PASS"))
    L.append("")
    L.append("## ERROR（必须修复）")
    L += ["%d. %s" % (i, e) for i, e in enumerate(errors, 1)] or ["（无）"]
    L.append("")
    L.append("## WARN（建议处理）")
    L += ["%d. %s" % (i, w) for i, w in enumerate(warns, 1)] or ["（无）"]
    L.append("")
    L.append("## 双向映射要求")
    L.append("- 正向（原→新）：每个原编号有且仅有一个去向（保留新号 / 并入某条 / 删除）；")
    L.append("- 反向（新→原）：每个新编号恰好对应一个保留的原编号，无碰撞、无断号；")
    L.append("- 正文、图表注、附录中的 [n] 必须全部落在映射表保留集合内。")

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    except OSError as e:
        print("[FAIL] 报告写入失败 %s: %s" % (args.output, e))
        return 1

    print("[映射校验] 映射行=%d ERROR=%d WARN=%d -> %s"
          % (len(rows), len(errors), len(warns), "FAIL" if errors else "PASS"))
    for e in errors:
        print("  [ERROR] %s" % e)
    for w in warns[:20]:
        print("  [WARN ] %s" % w)
    print("[报告] %s" % args.output)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
