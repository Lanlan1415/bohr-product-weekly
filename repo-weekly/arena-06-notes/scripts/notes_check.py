# -*- coding: utf-8 -*-
"""notes_check.py — 结构化笔记字段完整性与证据锚点检查（阅读10 专用）

对笔记 Markdown 做确定性检查：
  1. 必备章节齐全：分层摘要三级（一句话/一段/详细）、研究问题、方法与条件、
     数据与材料、主要结果、局限与适用边界、未报告与不确定项、可复用要素、
     论断→证据映射。
  2. 证据锚点合法：锚点形如 [S1 p.3 §2.1] / [S2 fig.2] / [S1 表1]，
     必须引用 materials_register.md 中已登记的 S 编号，且带定位信息
     （页码/章节/段落/图表之一），不允许只写 [S1] 这种笼统出处。
  3. 论断→证据映射区中每条论断（表格行或列表项）必须带至少一个合法锚点。
  4. “未报告与不确定项”必须显式填写（至少一条，或明确写“无”）。
  5. 主要结果中的数值论断（含数字+单位/%/p 值）建议同行带锚点（WARN）。
  6. （v2，仅 WARN）章节完整性：章节摘要须覆盖论文全部章节；提供
     --section-map 时逐节比对，缺节只 WARN 不 FAIL（校验器校准纪律）。
  7. （v2，仅 WARN）复合定位建议：统计"页+章节+行区间"等多类定位组合的
     锚点比例，全为单一定位时给出升级建议。

用法：
    python notes_check.py --notes <notes.md> [--register <materials_register.md>]
                          [--section-map <section_map.md>] [--strict]

退出码：0 全部通过（允许 WARN）；1 存在 FAIL；2 参数错误。
（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json 与笔记产物，未修复项记入 uncertainty / skipped_reason——
退出码不作为交付门禁。
仅使用 Python 标准库；读文件一律 utf-8-sig；只读输入文件；
不依赖当前工作目录（CWD）。
"""
import argparse
import os
import re
import sys

# 必备章节：检查项名 -> 匹配标题用的正则（对标题文本做 search）
REQUIRED_SECTIONS = [
    ("分层摘要-一句话", r"一句话摘要|一句话总结"),
    ("分层摘要-一段", r"一段摘要|一段话摘要"),
    ("分层摘要-详细", r"详细摘要|详版摘要"),
    ("研究问题", r"研究问题|研究目标"),
    ("方法与条件", r"方法与(前提)?条件|方法与实验条件|方法条件"),
    ("数据与材料", r"数据与材料|数据(集)?与(实验)?材料|数据来源"),
    ("主要结果", r"主要结果|主要发现|结果与发现"),
    ("局限与适用边界", r"局限|限制与适用|局限与适用边界"),
    ("未报告与不确定项", r"未报告|不确定项"),
    ("可复用要素", r"可复用要素|可复用资源"),
    ("论断证据映射", r"论断.{0,4}证据映射|论断.{0,4}证据对照|claim.{0,12}evidence"),
]

# 锚点：[S1 p.3 §2.1] / [S2 fig.2] / [S1 表1] / [S1 ¶3] / [S3 第5页]
# v2 增补：行区间定位 L12-15 / L12（抽取文本中的稳定行区间）
ANCHOR_RE = re.compile(r"\[S(\d+)\s*[:：]?\s*([^\[\]\n]{0,120}?)\]")
LOCATOR_RE = re.compile(
    r"p{1,2}\.?\s*\d|第?\s*\d+\s*页|§|fig\.?|Fig\.?|图\s*\d|表\s*\d|¶"
    r"|段落?\s*\d|行\s*\d|L\s*\d+(\s*[-–—~]\s*\d+)?|式\s*\(|eq\.?"
    r"|附录|Appendix", re.IGNORECASE)
# v2 复合定位分类（用于"页+章节+行区间"复合锚点建议，WARN 级）
LOCATOR_KINDS = {
    "页": re.compile(r"p{1,2}\.?\s*\d|第?\s*\d+\s*页", re.IGNORECASE),
    "章节": re.compile(r"§"),
    "段落": re.compile(r"¶|段落?\s*\d"),
    "图表": re.compile(r"fig\.?|Fig\.?|图\s*\d|表\s*\d|式\s*\(|eq\.?", re.IGNORECASE),
    "行区间": re.compile(r"L\s*\d+|行\s*\d"),
}
SECTION_MAP_RE = re.compile(r"§?\s*(\d+(?:\.\d+)?)")
# 数值论断：数字+单位/%/显著性
NUMERIC_CLAIM_RE = re.compile(
    r"\d+(\.\d+)?\s*(%|％|℃|°C|K|MPa|GPa|kPa|Pa|meV|eV|nm|μm|um|mm|cm|mM|mol|g/L|mg|kg"
    r"|min|mV/dec|mV|mA|kV|kA|V|A|W|kJ|J|GHz|MHz|kHz|Hz|ppm|h|s"
    r"|倍|个|组|例)|p\s*[<≤=]\s*0?\.\d+|\d+(\.\d+)?\s*±")
REG_ROW_RE = re.compile(r"^\|\s*S(\d+)\s*\|", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$", re.MULTILINE)


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def split_sections(text):
    """返回 [(标题, 起始, 终止)] 与 {标题: 正文}。"""
    matches = list(HEADING_RE.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(2)] = text[start:end]
    return sections


def find_section(sections, pattern):
    rx = re.compile(pattern, re.IGNORECASE)
    for title, body in sections.items():
        if rx.search(title):
            return title, body
    return None, None


def find_section_span(text, pattern):
    """层级感知取节：返回 (标题, 正文)，正文延伸到同级或更高级标题为止
    （与 split_sections 不同，保留子标题内容）。"""
    rx = re.compile(pattern, re.IGNORECASE)
    matches = list(HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        if not rx.search(m.group(2)):
            continue
        level = len(m.group(1))
        end = len(text)
        for n in matches[i + 1:]:
            if len(n.group(1)) <= level:
                end = n.start()
                break
        return m.group(2), text[m.end():end]
    return None, None


def load_registered_ids(register_path):
    text = read_text(register_path)
    return set(int(x) for x in REG_ROW_RE.findall(text))


def claim_lines(body):
    """论断区里的内容行：表格数据行与列表项。"""
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set(":- ") for c in cells):
                continue  # 分隔行
            if cells and re.match(r"^(论断|claim|编号|id)$", cells[0], re.IGNORECASE):
                continue  # 表头
            out.append(s)
        elif re.match(r"^[-*+]\s+", s) or re.match(r"^\d+[.、)]\s+", s):
            out.append(s)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="结构化笔记字段完整性与证据锚点检查（阅读10 专用）")
    ap.add_argument("--notes", required=True, help="笔记 Markdown 绝对路径")
    ap.add_argument("--register", default=None,
                    help="materials_register.md 绝对路径（提供则校验锚点编号已登记）")
    ap.add_argument("--section-map", default=None,
                    help="section_map.md 绝对路径（v2：提供则做章节完整性 WARN 检查）")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.notes):
        print("错误：笔记文件不存在：%s" % args.notes)
        return 2
    text = read_text(args.notes)
    sections = split_sections(text)
    registered = None
    if args.register:
        if not os.path.isfile(args.register):
            print("错误：登记表不存在：%s" % args.register)
            return 2
        registered = load_registered_ids(args.register)

    fails, warns = [], []

    # 检查 1：必备章节
    missing = []
    for name, pattern in REQUIRED_SECTIONS:
        title, _ = find_section(sections, pattern)
        if title is None:
            missing.append(name)
    if missing:
        fails.append("必备章节缺失 %d 项：%s" % (len(missing), "、".join(missing)))
    else:
        print("[PASS] 必备章节齐全（%d 组）" % len(REQUIRED_SECTIONS))

    # 检查 2：锚点合法性与登记一致性
    anchors = list(ANCHOR_RE.finditer(text))
    bad_locator, unknown_id = [], []
    for m in anchors:
        sid, loc = int(m.group(1)), m.group(2).strip()
        if not LOCATOR_RE.search(loc):
            bad_locator.append(m.group(0))
        if registered is not None and sid not in registered:
            unknown_id.append(m.group(0))
    if bad_locator:
        fails.append("锚点缺定位信息（页/节/段/图表）%d 处，示例：%s"
                     % (len(bad_locator), "、".join(sorted(set(bad_locator))[:3])))
    else:
        print("[PASS] 全部 %d 个锚点均含定位信息" % len(anchors))
    if unknown_id:
        fails.append("锚点引用未登记的来源编号 %d 处：%s"
                     % (len(unknown_id), "、".join(sorted(set(unknown_id))[:5])))
    elif registered is not None:
        print("[PASS] 全部锚点编号均已在登记表登记（S%s）"
              % ("..S".join([str(min(registered)), str(max(registered))])
                 if registered else "无"))

    # 检查 3：论断→证据映射每行带锚点
    t, body = find_section(sections, REQUIRED_SECTIONS[-1][1])
    if body is not None:
        rows = claim_lines(body)
        no_anchor = [r for r in rows if not ANCHOR_RE.search(r)]
        if not rows:
            fails.append("论断→证据映射区为空（未发现任何论断行）")
        elif no_anchor:
            fails.append("论断→证据映射中 %d/%d 条论断无锚点，首条：%s"
                         % (len(no_anchor), len(rows), no_anchor[0][:60]))
        else:
            print("[PASS] 论断→证据映射 %d 条论断全部带锚点" % len(rows))

    # 检查 4：未报告与不确定项显式填写
    t, body = find_section(sections, REQUIRED_SECTIONS[8][1])
    if body is not None:
        content = [l.strip() for l in body.splitlines()
                   if l.strip() and not l.strip().startswith("#")]
        filled = any(re.match(r"^[-*+]\s*\S", l) or re.search(r"无|没有", l)
                     for l in content)
        if not filled:
            fails.append("“未报告与不确定项”一节为空（必须显式列出或写明“无”）")
        else:
            print("[PASS] 未报告与不确定项已显式填写")

    # 检查 5：主要结果中的数值论断建议带锚点
    t, body = find_section(sections, REQUIRED_SECTIONS[6][1])
    if body is not None:
        numeric_no_anchor = []
        for line in body.splitlines():
            s = line.strip()
            if NUMERIC_CLAIM_RE.search(s) and not ANCHOR_RE.search(s):
                if s.startswith(("-", "*", "+", "|")):
                    numeric_no_anchor.append(s[:60])
        if numeric_no_anchor:
            warns.append("主要结果中 %d 条数值论断未带锚点（建议补齐），首条：%s"
                         % (len(numeric_no_anchor), numeric_no_anchor[0]))
        else:
            print("[PASS] 主要结果中的数值论断均带锚点")

    # 检查 6（v2，仅 WARN）：章节完整性——笔记不得只覆盖论文部分章节。
    # 提供 --section-map 时逐节比对；未提供时仅检查章节摘要区有小节结构。
    t, body = find_section_span(text, r"章节摘要|分节摘要|按章节")
    if body is None:
        warns.append("未发现“章节摘要”区（chapter-complete 要求逐章覆盖；"
                     "若论文确为单节短文请在 result.json 说明）")
    else:
        sub_heads = re.findall(r"^#{2,6}\s*\S", body, re.MULTILINE)
        if not sub_heads:
            warns.append("章节摘要区没有任何小节标题（应按论文实际章节逐节列出）")
        elif args.section_map:
            if not os.path.isfile(args.section_map):
                print("错误：section_map 不存在：%s" % args.section_map)
                return 2
            sm_text = read_text(args.section_map)
            sm_secs = sorted({m.group(1)
                              for m in SECTION_MAP_RE.finditer(sm_text)
                              if "." not in m.group(1)})
            body_secs = {m.group(1)
                         for m in SECTION_MAP_RE.finditer(body)}
            missing_secs = [s for s in sm_secs
                            if s not in body_secs and
                            not any(b.startswith(s + ".") for b in body_secs)]
            if missing_secs:
                warns.append("章节摘要疑似漏覆盖 section_map 中的章节：%s"
                             "（chapter-complete：每章都应有小节或显式说明从略）"
                             % "、".join("§" + s for s in missing_secs))
            else:
                print("[PASS] 章节摘要覆盖 section_map 全部一级章节（%d 节）"
                      % len(sm_secs))
        else:
            print("[PASS] 章节摘要区含 %d 个小节（未提供 --section-map，"
                  "跳过逐节比对）" % len(sub_heads))

    # 检查 7（v2，仅 WARN）：证据锚点定位精度——建议“页+章节+行区间”复合定位。
    if anchors:
        composite = 0
        for m in anchors:
            loc = m.group(2)
            kinds = sum(1 for rx in LOCATOR_KINDS.values() if rx.search(loc))
            if kinds >= 2:
                composite += 1
        if composite == 0:
            warns.append("全部锚点均为单一定位：建议升级为“页+章节+行区间”复合定位"
                         "（如 [S1 p.3 §3.1 L12-15]），提高原文可回溯性")
        else:
            print("[PASS] %d/%d 个锚点为复合定位（页/章节/行区间等≥2 类）"
                  % (composite, len(anchors)))

    for w in warns:
        print("[WARN] " + w)
    for f_ in fails:
        print("[FAIL] " + f_)
    print("----")
    print("检查结果：FAIL=%d WARN=%d" % (len(fails), len(warns)))
    if fails or (args.strict and warns):
        print("结论：未通过")
        return 1
    print("结论：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
