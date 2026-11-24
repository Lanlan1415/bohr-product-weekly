#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchor_check.py — 证据锚点核验（quote_bind）。

逻辑（同 nanopublication 的 quote 绑定）
    每条三列转述（conclusion/conditions/limitation）可附一条原文逐字 quote（≤50 字）。
    本脚本把 quote 与该 ref 的原文来源做逐字回查：NFC 归一 + 空白折叠后必须是来源的子串；
    找不到即报 QUOTE_NOT_FOUND（说明转述可能脱离原文，或 quote 被改写）。
    不写 quote 是允许的（诚实降级：定位不到原文就不编 quote），但绝不允许编造 quote。

用法
    python anchor_check.py --anchors anchors.json --entries entries.json [--sources sources.json]
                           [--report report.json]

输入格式
    anchors.json  条目列表，或含 anchors / papers 键的对象。每条：
                  {"ref": "...", "quote": "...", "field": "conclusion|conditions|limitation|...",
                   "locator": {"section": "...", "page": ...}}
                  也兼容 {"ref":..., "anchor": {"quote":...}} 与 {"ref":..., "anchor": "quote"}。
    entries.json  parse_library.py 的输出（用条目的 title+abstract+fields 作回查来源）。
    sources.json  可选，显式来源映射 {"<ref_id>": "该条目的原文全文（如摘要页/PDF 抽取文本）"}；
                  与 --entries 同时提供时显式来源优先。

报告
    {"script","ok","summary":{ok,error,missing_source},
     "results":[{index,ref,field,quote,status,detail,hint}]}
    status: ok | quote_not_found | empty_quote | no_ref | missing_source | too_long(附随 warning)

退出码：0 = 脚本运行成功（报告内 ok=false 表示存在 error 级问题）；2 = 输入错误。
"""

import argparse
import difflib
import json
import re
import sys
import unicodedata

SCRIPT = "anchor_check"
VERSION = "1.0.0"
MAX_QUOTE_LEN = 50


def normalize(s):
    """quote_bind 归一：NFC + 空白折叠 + CJK 相邻空白收紧。
    CJK 文本在 PDF 换行处常被插入空格/换行（如“长
序列”），逐字判定时对
    两个 CJK 字符之间的空白不敏感；拉丁文本的空格仍保持敏感。"""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\u00a0", " ").replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef])[ ](?=[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef])", "", s)
    return s.strip()


def best_match_hint(source_norm, quote_norm):
    """在来源中找与 quote 最接近的句子，辅助定位被改写的词。"""
    sentences = re.split(r"(?<=[。！？.!?])\s*", source_norm)
    best, ratio = "", 0.0
    for sent in sentences:
        if not sent.strip():
            continue
        r = difflib.SequenceMatcher(None, sent, quote_norm).ratio()
        if r > ratio:
            best, ratio = sent, r
    return best[:120], round(ratio, 3)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="证据锚点核验：三列转述附带的原文 quote 逐字回查（quote_bind）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python anchor_check.py --anchors anchors.json --entries entries.json")
    ap.add_argument("--anchors", required=True, help="锚点 JSON（列表或 {anchors:[...]}）")
    ap.add_argument("--entries", help="parse_library.py 输出（以 title+abstract 作为回查来源）")
    ap.add_argument("--sources", help="显式来源映射 JSON：{ref_id: 原文全文}（优先于 --entries）")
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
        anchors_doc = load_json(args.anchors)
    except (OSError, ValueError) as e:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "READ_FAILED", "detail": str(e)},
                         ensure_ascii=False))
        return 2

    sources = {}
    if args.sources:
        try:
            sources = load_json(args.sources)
            if not isinstance(sources, dict):
                sources = {}
        except (OSError, ValueError) as e:
            print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "READ_FAILED",
                              "detail": "sources: %s" % e}, ensure_ascii=False))
            return 2

    if args.entries:
        try:
            entries_doc = load_json(args.entries)
            entries = entries_doc.get("entries", []) if isinstance(entries_doc, dict) else entries_doc
            for e in entries:
                eid = str(e.get("id", ""))
                parts = [str(e.get("title", "")), str(e.get("abstract", ""))]
                for v in (e.get("fields") or {}).values():
                    if isinstance(v, str) and len(v) > 40:
                        parts.append(v)
                text = "\n".join(p for p in parts if p)
                if text.strip():
                    sources.setdefault(eid, text)
        except (OSError, ValueError):
            pass

    anchors = anchors_doc if isinstance(anchors_doc, list) else None
    if anchors is None and isinstance(anchors_doc, dict):
        for k in ("anchors", "papers", "items", "results"):
            if isinstance(anchors_doc.get(k), list):
                anchors = anchors_doc[k]
                break
    if anchors is None:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "ANCHORS_SHAPE_UNSUPPORTED",
                          "detail": "anchors 需为列表或含 anchors/papers 键的对象"}, ensure_ascii=False))
        return 2

    results = []
    n_ok = n_err = n_missing = 0
    for idx, a in enumerate(anchors, 1):
        ref = str(a.get("ref", "")).strip()
        field = str(a.get("field", "")).strip()
        quote = a.get("quote")
        anchor = a.get("anchor")
        if quote is None and anchor is not None:
            quote = anchor.get("quote") if isinstance(anchor, dict) else anchor
        quote = str(quote) if quote is not None else ""

        row = {"index": idx, "ref": ref, "field": field, "quote": quote, "status": "ok", "detail": "", "hint": None}

        if not ref:
            row["status"] = "no_ref"
            row["detail"] = "锚点缺少 ref，无法绑定来源"
            n_err += 1
        elif not quote.strip():
            row["status"] = "empty_quote"
            row["detail"] = "quote 为空：允许（定位不到原文时不编造），但该转述的结论/局限应改标作者判断或进 uncertainty"
            n_missing += 1
        elif len(normalize(quote)) > MAX_QUOTE_LEN:
            row["status"] = "quote_not_found"
            row["detail"] = "quote 超过 %d 字上限（%d 字）：请截取更短逐字片段" % (MAX_QUOTE_LEN, len(normalize(quote)))
            n_err += 1
        else:
            src = sources.get(ref)
            if src is None:
                row["status"] = "missing_source"
                row["detail"] = "文献库中找不到 %r 的可回查原文（无 abstract/sources）：转述依据无法核验，进 uncertainty" % ref
                n_missing += 1
            elif normalize(quote) in normalize(src):
                row["status"] = "ok"
                row["detail"] = "quote 在来源中逐字命中"
                n_ok += 1
            else:
                row["status"] = "quote_not_found"
                row["detail"] = "quote 未在来源中逐字命中：转述可能改写了原文，必须修正 quote 或改标作者判断"
                text_n, quote_n = normalize(src), normalize(quote)
                hint_text, ratio = best_match_hint(text_n, quote_n)
                row["hint"] = {"text": hint_text, "similarity": ratio}
                n_err += 1

        results.append(row)

    report = {
        "script": SCRIPT,
        "version": VERSION,
        "ok": n_err == 0,
        "summary": {"total": len(results), "ok": n_ok, "error": n_err, "missing_or_empty": n_missing},
        "results": results,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(payload)
    print(payload)
    return 1 if n_err > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
