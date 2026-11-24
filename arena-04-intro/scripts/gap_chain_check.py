#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gap_chain_check.py — 研究空白推导链（gap-chain）完整性核验。

链条定义
    gap_chain = [{step, kind?, basis, evidence_or_author_judgment, evidence?}, ...]
    kind ∈ literature_gap（文献局限）| cross_gap（交汇缺口）| this_work（本文切入）
    evidence_or_author_judgment ∈ evidence | author_judgment
    evidence 环必须带 evidence: {ref, quote（原文逐字 ≤50 字）}；
    author_judgment 环是作者判断，必须登记进 human_review_items；
    最后一环必须指向本文工作（kind=this_work 或 basis 含“本文/this work”等标志）。

核验项
    CHAIN_EMPTY / CHAIN_TOO_SHORT(<3 环, warning) / STEP_BASIS_MISSING(error)
    FIELD_MISSING(error：evidence_or_author_judgment 缺失或取值非法)
    STEP_ORDER(warning：step 编号不从 1 开始或不连续)
    LITERATURE_STEP_NO_EVIDENCE(error：evidence 环缺 evidence.ref/quote)
    EVIDENCE_QUOTE_NOT_FOUND(error：quote 与 --entries 原文不符，需 --entries)
    AUTHOR_JUDGMENT_NOT_IN_REVIEW(error：作者判断环未登记进 human_review_items)
    REVIEW_ITEMS_NOT_PROVIDED(warning：存在作者判断环但未提供 --review)
    LAST_STEP_NOT_THIS_WORK(error：链尾没有指向本文工作)

用法
    python gap_chain_check.py --chain gap_chain.json [--review review_items.json]
                              [--entries entries.json] [--report report.json]

输入格式
    gap_chain.json     列表，或含 gap_chain 键的对象。
    review_items.json  字符串列表，或含 human_review_items 键的对象。
    entries.json       parse_library.py 输出（用于 quote 逐字回查，可选）。

报告
    {"script","ok","summary":{steps,errors,warnings},"findings":[{code,severity,step,detail}],
     "author_judgment_steps":[...], "review_items_count":N}

退出码：0 = 脚本运行成功（报告内 ok=false 表示存在 error 级问题）；2 = 输入错误。
"""

import argparse
import json
import re
import sys
import unicodedata

SCRIPT = "gap_chain_check"
VERSION = "1.0.0"
MIN_STEPS = 3
THIS_WORK_MARKERS = ("本文", "本工作", "本研究", "我们提出", "this work", "this paper",
                     "our approach", "our method", "our work")
KINDS = ("literature_gap", "cross_gap", "this_work")


def normalize(s):
    """NFC + 空白折叠 + CJK 相邻空白收紧（与 anchor_check 的 quote_bind 规则一致）。"""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\u00a0", " ").replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef])[ ](?=[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef])", "", s)
    return s.strip()


def normalize_grade(v):
    v = normalize(str(v)).lower()
    if not v:
        return ""
    if "判断" in v or "judgment" in v or "judgement" in v:
        return "author_judgment"
    if "证据" in v or "evidence" in v or "原文" in v:
        return "evidence"
    return v


def review_matches_step(items, step_no, basis):
    text = " ".join(normalize(str(x)) for x in items).casefold()
    tokens = ["gap_chain[%d]" % step_no, "gap_chain[% d]" % step_no,
              "第%d环" % step_no, "第 %d 环" % step_no,
              "步骤%d" % step_no, "步骤 %d" % step_no,
              "step %d" % step_no, "step%d" % step_no]
    if any(t in text for t in tokens):
        return True
    b = normalize(basis).casefold()
    return len(b) >= 10 and b[:24] in text


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="研究空白推导链完整性核验：每环有 basis、evidence 环有逐字证据、作者判断环进人工复核、链尾指向本文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python gap_chain_check.py --chain gap_chain.json --review review_items.json --entries entries.json")
    ap.add_argument("--chain", required=True, help="gap 链 JSON（列表或 {gap_chain:[...]}）")
    ap.add_argument("--review", help="human_review_items JSON（列表或 {human_review_items:[...]})")
    ap.add_argument("--entries", help="parse_library.py 输出（用于 evidence.quote 逐字回查，可选）")
    ap.add_argument("--report", help="报告 JSON 输出路径（默认仅打印）")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    def load_json(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    try:
        chain_doc = load_json(args.chain)
    except (OSError, ValueError) as e:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "READ_FAILED", "detail": str(e)},
                         ensure_ascii=False))
        return 2

    chain = chain_doc if isinstance(chain_doc, list) else None
    if chain is None and isinstance(chain_doc, dict):
        for k in ("gap_chain", "chain", "steps"):
            if isinstance(chain_doc.get(k), list):
                chain = chain_doc[k]
                break
    if chain is None:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "CHAIN_SHAPE_UNSUPPORTED",
                          "detail": "chain 需为列表或含 gap_chain 键的对象"}, ensure_ascii=False))
        return 2

    review_items = []
    if args.review:
        try:
            rv = load_json(args.review)
            if isinstance(rv, list):
                review_items = rv
            elif isinstance(rv, dict):
                for k in ("human_review_items", "items", "review"):
                    if isinstance(rv.get(k), list):
                        review_items = rv[k]
                        break
        except (OSError, ValueError) as e:
            review_items = []
            review_error = str(e)
        else:
            review_error = None
    else:
        review_error = None

    sources = {}
    if args.entries:
        try:
            edoc = load_json(args.entries)
            entries = edoc.get("entries", []) if isinstance(edoc, dict) else edoc
            for e in entries:
                parts = [str(e.get("title", "")), str(e.get("abstract", ""))]
                for v in (e.get("fields") or {}).values():
                    if isinstance(v, str) and len(v) > 40:
                        parts.append(v)
                text = "\n".join(p for p in parts if p)
                if text.strip():
                    sources[str(e.get("id", ""))] = text
        except (OSError, ValueError):
            pass

    findings = []

    def add(code, severity, step, detail):
        findings.append({"code": code, "severity": severity, "step": step, "detail": detail})

    if not chain:
        add("CHAIN_EMPTY", "error", None, "gap 链为空：无法说明空白如何由文献缺口推出")

    aj_steps = []
    for pos, s in enumerate(chain, 1):
        step_no = s.get("step", pos)
        basis = normalize(str(s.get("basis", "")))
        grade = normalize_grade(s.get("evidence_or_author_judgment", ""))
        kind = normalize(str(s.get("kind", ""))).lower()

        if not basis:
            add("STEP_BASIS_MISSING", "error", step_no,
                "第 %d 环缺少 basis：每一环都必须写明该步成立的理由（文献局限需落到具体条目）" % step_no)
        if not grade:
            add("FIELD_MISSING", "error", step_no,
                "第 %d 环缺少 evidence_or_author_judgment：每环必须显式标注 evidence 或 author_judgment" % step_no)
        elif grade not in ("evidence", "author_judgment"):
            add("FIELD_MISSING", "error", step_no,
                "第 %d 环 evidence_or_author_judgment=%r 非法（只允许 evidence / author_judgment）" % (step_no, grade))
        if kind and kind not in KINDS:
            add("KIND_UNKNOWN", "warning", step_no,
                "第 %d 环 kind=%r 不在 literature_gap/cross_gap/this_work 之列" % (step_no, kind))

        if grade == "evidence":
            ev = s.get("evidence") or {}
            ev_ref = normalize(str(ev.get("ref", ""))) if isinstance(ev, dict) else ""
            ev_quote = str(ev.get("quote", "")) if isinstance(ev, dict) else ""
            if not ev_ref or not ev_quote.strip():
                add("LITERATURE_STEP_NO_EVIDENCE", "error", step_no,
                    "第 %d 环标注 evidence 但缺少 evidence.ref/quote：文献缺口必须绑定具体条目与逐字原文" % step_no)
            elif len(normalize(ev_quote)) > 50:
                add("EVIDENCE_QUOTE_NOT_FOUND", "error", step_no,
                    "第 %d 环 evidence.quote 超过 50 字上限（%d 字），请截取更短逐字片段" % (step_no, len(normalize(ev_quote))))
            elif sources:
                src = sources.get(ev_ref)
                if src is None:
                    add("EVIDENCE_QUOTE_NOT_FOUND", "error", step_no,
                        "第 %d 环 evidence.ref=%r 在文献库中不存在" % (step_no, ev_ref))
                elif normalize(ev_quote) not in normalize(src):
                    add("EVIDENCE_QUOTE_NOT_FOUND", "error", step_no,
                        "第 %d 环 evidence.quote 未在 %r 原文中逐字命中" % (step_no, ev_ref))
            elif not sources and args.entries is None:
                add("EVIDENCE_NOT_VERIFIED", "note", step_no,
                    "未提供 --entries，第 %d 环 evidence.quote 未做逐字回查" % step_no)

        if grade == "author_judgment":
            aj_steps.append(step_no)
            if review_items:
                if not review_matches_step(review_items, step_no, basis):
                    add("AUTHOR_JUDGMENT_NOT_IN_REVIEW", "error", step_no,
                        "第 %d 环为作者判断，但 human_review_items 中找不到对应登记（需含 gap_chain[%d]/第%d环/步骤%d 等标志）"
                        % (step_no, step_no, step_no, step_no))
            elif args.review:
                if review_error:
                    add("REVIEW_ITEMS_NOT_PROVIDED", "warning", step_no,
                        "review 文件读取失败（%s），作者判断环无法核对是否已登记" % review_error)
            else:
                add("REVIEW_ITEMS_NOT_PROVIDED", "warning", step_no,
                    "存在作者判断环但未提供 --review，无法核对是否已登记进 human_review_items")

    if chain:
        numbers = [s.get("step", i + 1) for i, s in enumerate(chain)]
        if numbers != list(range(1, len(chain) + 1)):
            add("STEP_ORDER", "warning", None,
                "step 编号应从 1 开始连续递增，当前为 %r" % (numbers,))
        last = chain[-1]
        last_no = last.get("step", len(chain))
        last_basis = normalize(str(last.get("basis", "")))
        marked = last.get("kind") == "this_work" or last.get("points_to_this_work") is True
        contains = any(m in last_basis.casefold() for m in THIS_WORK_MARKERS)
        if not (marked or contains):
            add("LAST_STEP_NOT_THIS_WORK", "error", last_no,
                "链尾（第 %d 环）未指向本文工作：basis 需写明本文如何填补该空白（含“本文/本工作/this work”等，或 kind=this_work）"
                % last_no)
        if len(chain) < MIN_STEPS:
            add("CHAIN_TOO_SHORT", "warning", None,
                "链条仅 %d 环（建议 ≥%d：文献局限 → 交汇缺口 → 本文切入）" % (len(chain), MIN_STEPS))

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    report = {
        "script": SCRIPT,
        "version": VERSION,
        "ok": len(errors) == 0,
        "summary": {"steps": len(chain), "errors": len(errors), "warnings": len(warnings)},
        "findings": findings,
        "author_judgment_steps": aj_steps,
        "review_items_count": len(review_items),
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(payload)
    print(payload)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
