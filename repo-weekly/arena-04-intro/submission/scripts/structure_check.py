#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""structure_check.py — 引言与相关工作的结构与引用覆盖检查（stdlib-only）。

确定性校验项（对应题面「立得住 / 分得清 / 说得实 / 对得上」）：
  1. 漏斗结构齐全且顺序正确：研究背景 -> 相关工作 -> 研究空白(缺口) -> 贡献；
  2. 相关工作对比表存在且维度齐全（方法/数据/结论/局限 至少 3 维）；
  3. 正文 [S#] 来源标记全部已在证据表登记（无幽灵引用）；登记未用给 WARN；
  4. 贡献条目数 == 缺口条目数（一一对应）；
  5. 空转铺垫检测：「近年来受到广泛关注」类口号句若无引用支撑给 WARN；
  6. 每条贡献含证据指针（图/表/节/[S#]），否则 WARN；
  7. 行文完成度（v2，WARN）：TODO/待补/占位符等未完成标记；漏斗节标题下
     无正文的空节；
  8. 相邻结果边界（v2，WARN）：贡献/缺口段中「显著优于/远超/大幅提升」类
     比较断言若无数值区间支撑，提示补最相近工作的结果区间对比
     （method_rules.md §5.1）。
  v2 新增项一律只 WARN，不把原本能通过的草稿判 FAIL。

用法（绝对路径调用，不依赖 CWD，只读输入文件）：
  python3 /skills/weekly-skill/scripts/structure_check.py \
      --draft /app/output/manuscript.md \
      --evidence /app/output/evidence_map.md \
      --output /app/output/structure_check_report.md

退出码：0 = 无 ERROR；1 = 存在 ERROR 或输入不可读。
"""
import argparse
import os
import re
import sys

SECTION_PATTERNS = {
    "background": re.compile(
        r"^\s{0,3}#{1,6}\s*[\d\.、\s]*(研究背景|引言|绪论|Introduction|Background)\b", re.M | re.I),
    "related": re.compile(
        r"^\s{0,3}#{1,6}\s*[\d\.、\s]*(相关工作|相关研究|文献综述|Related\s+Work|Literature\s+Review)\b",
        re.M | re.I),
    "gap": re.compile(
        r"^\s{0,3}#{1,6}\s*[\d\.、\s]*(研究空白|研究缺口|问题提出|Research\s+Gap|Motivation|问题与挑战)\b",
        re.M | re.I),
    "contrib": re.compile(
        r"^\s{0,3}#{1,6}\s*[\d\.、\s]*((本文)?(主要)?贡献|Contributions?|贡献与(论文)?结构)\b",
        re.M | re.I),
}
TABLE_DIMS = {
    "方法": re.compile(r"方法|路线|模型|Method|Approach", re.I),
    "数据": re.compile(r"数据|语料|实验设置|基准|Dataset|Benchmark|Data", re.I),
    "结论": re.compile(r"结论|结果|效果|Findings?|Results?", re.I),
    "局限": re.compile(r"局限|不足|缺点|适用条件|Limitation|Weakness", re.I),
}
SMARK = re.compile(r"\[S(\d+)\]")
SREG = re.compile(r"(?:^|[\s|>])\**S(\d+)\**[\s:|：]")
LIST_ITEM = re.compile(r"^\s*(?:\d+\s*[\.、\)]|[-*•])\s+\S")
SLOGAN = re.compile(r"(近年来|近些年|随着[^。；\n]{0,30}(快速|迅猛|蓬勃)?发展)"
                    r"[^。；\n]{0,40}(广泛关注|越来越多|日益|热点|备受)")
EVIDENCE_PTR = re.compile(r"(图\s*\d|表\s*\d|Fig\.?\s*\d|Table\s*\d|第\s*[一二三四五六七八九十\d]+\s*节"
                          r"|Section\s*\d|\[S\d+\]|附录)", re.I)
# v2：行文完成度与相邻结果边界（均只产生 WARN）
INCOMPLETE = re.compile(r"TODO|FIXME|XXX+|待补|待完善|待填写|占位符|此处补", re.I)
CMP_CLAIM = re.compile(r"显著(优于|提升|提高|降低|超过)|远超|大幅(提升|提高|降低|超过)"
                       r"|明显(优于|高于|低于)")
# 数值边界形态：小数 / 区间 / 百分数（「图 1」「缺口 2」这类序号不算数值边界）
NUM_VAL = re.compile(r"\d+\.\d+|\d+\s*[-–—~～]\s*\d+|\d+\s*%")


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def section_span(text, key):
    """返回 (起始, 结束) 字符区间；结束为下一个同级或更高级标题，找不到返回 None。"""
    m = SECTION_PATTERNS[key].search(text)
    if not m:
        return None
    level = len(re.match(r"\s{0,3}(#{1,6})", text[m.start():]).group(1))
    nxt = re.compile(r"^\s{0,3}#{1,%d}\s" % level, re.M).search(text, m.end())
    return (m.start(), nxt.start() if nxt else len(text))


def count_list_items(block):
    return sum(1 for line in block.splitlines() if LIST_ITEM.match(line))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="引言漏斗结构、对比表维度、[S#] 登记、贡献-缺口对应的确定性检查。")
    ap.add_argument("--draft", required=True, help="引言/相关工作成稿（utf-8 文本）绝对路径")
    ap.add_argument("--evidence", required=True, help="证据表/来源映射文件绝对路径")
    ap.add_argument("--output", required=True, help="检查报告 markdown 输出绝对路径")
    args = ap.parse_args(argv)

    for p in (args.draft, args.evidence):
        if not os.path.isfile(p):
            print("[FAIL] 输入文件不存在: %s" % p)
            return 1
    try:
        draft = read_text(args.draft)
        evidence = read_text(args.evidence)
    except OSError as e:
        print("[FAIL] 输入读取失败: %s" % e)
        return 1

    errors, warns = [], []

    # 1. 漏斗四段齐全且顺序正确
    pos = {}
    for key in ("background", "related", "gap", "contrib"):
        m = SECTION_PATTERNS[key].search(draft)
        if not m:
            errors.append("漏斗结构缺段：未找到「%s」对应标题" %
                          {"background": "研究背景/引言", "related": "相关工作",
                           "gap": "研究空白/缺口", "contrib": "贡献"}[key])
        else:
            pos[key] = m.start()
    if len(pos) == 4:
        order = ["background", "related", "gap", "contrib"]
        if [pos[k] for k in order] != sorted(pos[k] for k in order):
            errors.append("漏斗顺序错误：应按 研究背景 -> 相关工作 -> 研究空白 -> 贡献 排列")

    # 2. 对比表维度
    tables = re.findall(r"((?:^\|.*\|\s*$\n?){2,})", draft, re.M)
    dim_ok = None
    for tb in tables:
        header = tb.splitlines()[0]
        dims = [name for name, pat in TABLE_DIMS.items() if pat.search(header)]
        if len(dims) >= 3:
            dim_ok = dims
            break
    if not tables:
        errors.append("相关工作缺对比表（markdown 表格，维度含 方法/数据/结论/局限）")
    elif dim_ok is None:
        errors.append("对比表维度不足：表头需覆盖 方法/数据/结论/局限 中至少 3 维")

    # 3. [S#] 登记核对
    registered = {int(m.group(1)) for m in SREG.finditer(evidence)}
    used = {int(m.group(1)) for m in SMARK.finditer(draft)}
    if not used:
        errors.append("正文未使用任何 [S#] 来源标记——论断须挂来源")
    ghosts = sorted(used - registered)
    if ghosts:
        errors.append("幽灵来源：正文 [S#] 未在证据表登记: %s"
                      % ", ".join("S%d" % g for g in ghosts))
    idle = sorted(registered - used)
    if idle:
        warns.append("已登记但正文未引用: %s（确认是否应覆盖或移出证据表）"
                     % ", ".join("S%d" % s for s in idle))

    # 4. 贡献-缺口一一对应
    gap_span = section_span(draft, "gap")
    con_span = section_span(draft, "contrib")
    if gap_span and con_span:
        n_gap = count_list_items(draft[gap_span[0]:gap_span[1]])
        n_con = count_list_items(draft[con_span[0]:con_span[1]])
        if n_gap == 0 or n_con == 0:
            errors.append("缺口或贡献未以列表条目呈现（缺口 %d 条 / 贡献 %d 条），"
                          "无法核对一一对应" % (n_gap, n_con))
        elif n_gap != n_con:
            errors.append("贡献-缺口数量不一致：缺口 %d 条 vs 贡献 %d 条（应一一对应）"
                          % (n_gap, n_con))

    # 5. 空转铺垫（口号句无引用支撑）
    for m in SLOGAN.finditer(draft):
        line_start = draft.rfind("\n", 0, m.start()) + 1
        line_end = draft.find("\n", m.end())
        line = draft[line_start: line_end if line_end > 0 else len(draft)]
        if not SMARK.search(line) and not re.search(r"\[\d+\]", line):
            warns.append("疑似空转铺垫且无引用支撑：「%s…」——改写为指向具体脉络/问题的表述"
                         % re.sub(r"\s+", " ", line.strip())[:40])

    # 6. 贡献条目证据指针
    if con_span:
        for line in draft[con_span[0]:con_span[1]].splitlines():
            if LIST_ITEM.match(line) and not EVIDENCE_PTR.search(line):
                warns.append("贡献条目缺证据指针（图/表/节/[S#]）：「%s」"
                             % line.strip()[:40])

    # 7. 行文完成度（v2，仅 WARN）
    seen_inc = set()
    for m in INCOMPLETE.finditer(draft):
        line_start = draft.rfind("\n", 0, m.start()) + 1
        line_end = draft.find("\n", m.end())
        line = draft[line_start: line_end if line_end > 0 else len(draft)]
        key = re.sub(r"\s+", " ", line.strip())[:40]
        if key in seen_inc:
            continue
        seen_inc.add(key)
        warns.append("疑似未完成行文标记：「%s…」——交付前须替换为成稿文字" % key)
        if len(seen_inc) >= 5:
            break
    for key, label in (("background", "研究背景/引言"), ("related", "相关工作"),
                       ("gap", "研究空白/缺口"), ("contrib", "贡献")):
        sp = section_span(draft, key)
        if sp:
            body_lines = [ln for ln in draft[sp[0]:sp[1]].splitlines()[1:]
                          if ln.strip()]
            if not body_lines:
                warns.append("空节：「%s」标题下无正文——行文未完成" % label)

    # 8. 相邻结果边界（v2，仅 WARN）：比较断言须挂数值区间
    for sec_key in ("gap", "contrib"):
        sp = section_span(draft, sec_key)
        if not sp:
            continue
        for line in draft[sp[0]:sp[1]].splitlines():
            if CMP_CLAIM.search(line) and not NUM_VAL.search(line):
                warns.append("比较断言缺数值边界：「%s」——按 method_rules §5.1 补"
                             "最相近工作的结果区间对比（如「S4 报告 0.78–0.80；本文 "
                             "0.81–0.83（表 2）」）" % line.strip()[:40])

    L = []
    L.append("# 引言与相关工作结构检查报告")
    L.append("")
    L.append("- 成稿: `%s`" % args.draft)
    L.append("- 证据表: `%s`" % args.evidence)
    L.append("- 结论: ERROR %d 项 / WARN %d 项 -> **%s**"
             % (len(errors), len(warns), "FAIL" if errors else "PASS"))
    L.append("")
    L.append("## ERROR（必须修复）")
    L += ["%d. %s" % (i, e) for i, e in enumerate(errors, 1)] or ["（无）"]
    L.append("")
    L.append("## WARN（建议处理，处理不了的在不确定性中说明）")
    L += ["%d. %s" % (i, w) for i, w in enumerate(warns, 1)] or ["（无）"]
    L.append("")
    L.append("## 修复指引")
    L.append("- 漏斗各段写法与反例见 references/funnel_writing_guide.md；")
    L.append("- 对比表填法见 templates/related_work_table_template.md；")
    L.append("- 缺口须由已引文献的共同限制/未覆盖场景/冲突结论推出，并写反例界定；")
    L.append("- 贡献条目与缺口逐条对应，每条挂证据指针（图/表/节）。")

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    except OSError as e:
        print("[FAIL] 报告写入失败 %s: %s" % (args.output, e))
        return 1

    print("[结构检查] ERROR=%d WARN=%d -> %s"
          % (len(errors), len(warns), "FAIL" if errors else "PASS"))
    for e in errors:
        print("  [ERROR] %s" % e)
    for w in warns[:20]:
        print("  [WARN ] %s" % w)
    print("[报告] %s" % args.output)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
