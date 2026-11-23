#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare.py —— 五脚本流水线的第 1 环：准备阶段。

职责：
1. 解析 case.json：提取 case_id 与 output_contract 全部字段名，
   写入 <workdir>/contract_fields.json 与 <workdir>/contract_note.md
   （供 finalize.py 做契约前置校验）；
2. 封存原文快照 <workdir>/original_snapshot.md（守恒基线，之后不再改动）；
3. 把原文切分为带 sentence_id 的句级清单 <workdir>/sentences.tsv
   （锚定协议的定位基准：编辑记录必须先抄原句、再写改文）；
4. 若 <workdir>/terms.txt 不存在，生成带注释头的空术语表骨架；
5. 写 <workdir>/prepare_report.md。

用法：
    python3 /skills/weekly-skill/scripts/prepare.py \
        --text /input/manuscript.md --workdir /app/work [--case /input/case.json]

约束：stdlib-only；utf-8-sig 读文件；只读输入；输出只写 --workdir；
不依赖 CWD，不联网。退出码：0 = 完成（含降级）；1 = 原文不可读。
"""

import argparse
import json
import os
import re
import sys

# 句末标点：英文 .!? 后接空白+大写/引号/数字才断句；中文 。！？ 直接断句；
# 分号不断句（避免把并列从句切碎）。LaTeX 公式段内不断句。
RE_SENT_END_ZH = re.compile(r"[。！？…]+[”’\"）)]*")
RE_SENT_END_EN = re.compile(r"[.!?]+[”’\"')\]]*(?=\s+(?:[A-Z0-9\"'(\[]|$)|\s*$)")


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def contract_fields(contract):
    """从 output_contract 提取字段名清单，兼容 dict / list 两种形态。"""
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    if isinstance(contract, list):
        out = []
        for item in contract:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for key in ("name", "field", "key", "id"):
                    if key in item:
                        out.append(str(item[key]))
                        break
        return out
    return []


def _in_inline_math(line, pos):
    """粗略判断 pos 处是否在行内 $...$ 内（统计 pos 前单个 $ 的奇偶）。"""
    prefix = line[:pos].replace("$$", "")
    return prefix.count("$") % 2 == 1


def split_line_sentences(line):
    """把一行（无换行符）切成句子，逐字返回（不改动任何字符）。"""
    spans = []
    i, n = 0, len(line)
    while i < n:
        m_zh = RE_SENT_END_ZH.search(line, i)
        m_en = RE_SENT_END_EN.search(line, i)
        if m_en and _in_inline_math(line, m_en.start()):
            # 公式内的句末点不断句：跳过该匹配，从其后继续找
            m_en = RE_SENT_END_EN.search(line, m_en.end())
            if m_en and _in_inline_math(line, m_en.start()):
                m_en = None
        cands = [m for m in (m_zh, m_en) if m]
        if not cands:
            break
        m = min(cands, key=lambda x: x.start())
        spans.append(line[i:m.end()])
        i = m.end()
    if i < n:
        spans.append(line[i:])
    return [s for s in spans if s.strip()]


def split_sentences(text):
    """逐行切句；标题/无标点短行整行作为一个单元。返回 [(sentence_id, text)]。"""
    out = []
    seq = 0
    for line in text.split("\n"):
        if not line.strip():
            continue
        stripped = line.strip()
        no_sent_end = (not RE_SENT_END_ZH.search(stripped)
                       and not RE_SENT_END_EN.search(stripped))
        if stripped.startswith("#") or no_sent_end:
            seq += 1
            out.append(("sent-%04d" % seq, line))
            continue
        for s in split_line_sentences(line):
            seq += 1
            out.append(("sent-%04d" % seq, s))
    return out


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="润色流水线 prepare：契约解析 + 原文快照 + 句级切分")
    parser.add_argument("--text", required=True, help="待润色原文路径")
    parser.add_argument("--workdir", required=True, help="工作目录（如 /app/work）")
    parser.add_argument("--case", default=None, help="case.json 路径（可选但强烈建议）")
    args = parser.parse_args(argv)

    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    warnings = []

    # ---- 1. 契约解析 ----
    case_id, fields = "", []
    if args.case:
        cpath = os.path.abspath(args.case)
        try:
            with open(cpath, "r", encoding="utf-8-sig") as f:
                case = json.load(f)
            case_id = str(case.get("case_id") or "")
            fields = contract_fields(case.get("output_contract"))
            if not case_id:
                warnings.append("case.json 缺少 case_id")
            if not fields:
                warnings.append("case.json 未声明 output_contract 字段")
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append("case.json 解析失败：%s（finalize 将以 skipped_reason 降级）" % exc)
    else:
        warnings.append("未提供 --case，契约前置校验将无依据（正式交付前必须补做）")

    write_text(os.path.join(workdir, "contract_fields.json"),
               json.dumps({"case_id": case_id, "fields": fields},
                          ensure_ascii=False, indent=2) + "\n")
    note = ["# 契约清单（prepare.py 生成）", "",
            "- case_id：%s" % (case_id or "（缺失）"),
            "- output_contract 字段（%d 个，result.json 必须逐字透传）：" % len(fields)]
    note += ["  - %s" % f for f in fields] or ["  - （无）"]
    note += ["", "后续所有产出对照本清单；result.json 写入前由 finalize.py 复核。"]
    write_text(os.path.join(workdir, "contract_note.md"), "\n".join(note) + "\n")

    # ---- 2. 原文快照 ----
    try:
        original = read_text(os.path.abspath(args.text))
    except OSError as exc:
        print("[FAIL] 原文不可读：%s" % exc)
        return 1
    write_text(os.path.join(workdir, "original_snapshot.md"), original)

    # ---- 3. 句级切分 ----
    sentences = split_sentences(original)
    tsv_lines = ["sentence_id\tsentence"]
    for sid, sent in sentences:
        tsv_lines.append("%s\t%s" % (sid, sent.replace("\t", " ")))
    write_text(os.path.join(workdir, "sentences.tsv"), "\n".join(tsv_lines) + "\n")

    # ---- 4. 术语表骨架 ----
    terms_path = os.path.join(workdir, "terms.txt")
    if not os.path.isfile(terms_path):
        write_text(terms_path,
                   "# 术语表：每行一个批准写法；# 开头为注释\n"
                   "# 缩写首次出现 = 全称（缩写）；未批准写法的替换记入 change_log\n")

    # ---- 5. 报告 ----
    rep = ["# prepare 报告", "",
           "- 原文：`%s`（%d 字符）" % (args.text, len(original)),
           "- 句子数：%d（sentences.tsv）" % len(sentences),
           "- case_id：%s；契约字段 %d 个" % (case_id or "（缺失）", len(fields)),
           "- 快照：original_snapshot.md（封存，不再改动）", ""]
    for w in warnings:
        rep.append("- [WARN] %s" % w)
    write_text(os.path.join(workdir, "prepare_report.md"), "\n".join(rep) + "\n")

    print("[OK] prepare 完成：%d 句；契约字段 %d 个；警告 %d 条"
          % (len(sentences), len(fields), len(warnings)))
    for w in warnings:
        print("[WARN] %s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
