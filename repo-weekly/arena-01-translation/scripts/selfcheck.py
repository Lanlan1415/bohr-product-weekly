#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付自查脚本（文献翻译技能）：对 /app/output 做逐项机器校验。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/selfcheck.py \
        --output /app/output --case /input/case.json

校验项：
  1. 输出目录存在且非空；
  2. 主产物（bilingual_translation.md）存在且非空；
  3. result.json 是合法 JSON，含 case_id 且与 case.json 一致；
  4. result.json 顶层包含 case.json 的 output_contract 声明的全部字段；
  5. result.json 的 status 属于 success/partial/failed；
  6. 主产物包含本题必备要素：术语表、[P###] 段号、双语对照、核验章节；
  7. 主产物中引用的每个 [S#] 来源标记都已在证据映射表中登记；
  8. 证据映射表 evidence_map.md 存在。

v2 新增 WARN 级检查（校验器校准纪律：新检查项一律 WARN 起步，
不把原本能通过的草稿判 FAIL；观察稳定后才允许升级为 FAIL）：
  W1. status 为 partial/failed 但 uncertainty 为空 → WARN；
  W2. result.json 缺 change_log 或 sources（契约未声明时）→ WARN；
  W3. status 为 partial 但无 skipped_reason 字段且 uncertainty 无跳过/未译说明 → WARN；
  W4. 主产物含 [UNSURE] 但未决项章节未列出对应条目 → WARN；
  W5. 主产物声称"翻译完成/全文完整"但含 [NOT_TRANSLATED] 标记 → WARN
     （对应负路径红线：漏段却报 complete——硬拦截由 align_check.py 与
     sentence_anchor.py 负责，此处只做交付层一致性提醒）。

打印逐条 [PASS]/[FAIL]/[WARN]，任一 FAIL 则退出码为 1，WARN 不影响退出码。
（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读取一律 utf-8-sig；不访问网络；不修改任何输入。

注意：本脚本不替代 term_consistency.py、align_check.py 与 sentence_anchor.py——
前三个脚本在步骤 5 对中间稿执行，本脚本在步骤 7 对最终交付执行结构校验。
"""
import argparse
import json
import os
import re
import sys

MAIN_ARTIFACT = "bilingual_translation.md"
EVIDENCE_MAP = "evidence_map.md"
RESULT_JSON = "result.json"

# 主产物必备要素（正则），缺任一条即 FAIL
REQUIRED_SECTIONS = [
    ("术语表章节", r"术语表"),
    ("段号标记 [P###]", r"\[P\d{3,}\]"),
    ("原文/译文对照结构", r"原文"),
    ("译文内容", r"译文"),
    ("核验清单章节", r"核验"),
]

RE_SOURCE_MARK = re.compile(r"\[S(\d+)\]")
ALLOWED_STATUS = ("success", "partial", "failed")


def read_text(path):
    """utf-8-sig 读取文本文件；失败返回 None。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def contract_fields(case_obj):
    """从 case.json 提取 output_contract 声明的字段名列表（兼容 dict/list/str）。"""
    if not isinstance(case_obj, dict):
        return []
    oc = case_obj.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(x) for x in oc]
    if isinstance(oc, str):
        return [oc]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description="交付自查（文献翻译技能）")
    parser.add_argument("--output", required=True, help="交付目录绝对路径，例如 /app/output")
    parser.add_argument("--case", default=None,
                        help="case.json 绝对路径，例如 /input/case.json（可选但强烈建议）")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.output)
    results = []

    def check(ok, name, detail=""):
        results.append(("PASS" if ok else "FAIL", name, detail))

    def warn(name, detail=""):
        results.append(("WARN", name, detail))

    if not os.path.isdir(out_dir):
        print("[FAIL] 输出目录不存在：%s" % out_dir)
        return 1
    names = os.listdir(out_dir)
    check(len(names) > 0, "输出目录非空", "%d 个条目" % len(names))

    main_path = os.path.join(out_dir, MAIN_ARTIFACT)
    main_text = read_text(main_path)
    check(main_text is not None and main_text.strip(), "主产物存在且非空", MAIN_ARTIFACT)

    rj_path = os.path.join(out_dir, RESULT_JSON)
    rj_text = read_text(rj_path)
    rj = None
    if rj_text is None:
        check(False, "result.json 存在且可读", rj_path)
    else:
        try:
            rj = json.loads(rj_text)
            check(True, "result.json 是合法 JSON", "")
        except json.JSONDecodeError as exc:
            check(False, "result.json 是合法 JSON", str(exc))

    case_obj = None
    if args.case:
        case_text = read_text(os.path.abspath(args.case))
        if case_text is not None:
            try:
                case_obj = json.loads(case_text)
            except json.JSONDecodeError:
                case_obj = None

    if isinstance(rj, dict):
        check(bool(rj.get("case_id")), "result.json 含 case_id", str(rj.get("case_id")))
        if isinstance(case_obj, dict) and case_obj.get("case_id"):
            check(rj.get("case_id") == case_obj.get("case_id"),
                  "case_id 与 case.json 一致",
                  "result=%s case=%s" % (rj.get("case_id"), case_obj.get("case_id")))
        check(rj.get("status") in ALLOWED_STATUS,
              "status 合法（success/partial/failed）", str(rj.get("status")))
        fields = contract_fields(case_obj) if case_obj else []
        if fields:
            missing = [f for f in fields if f not in rj]
            check(not missing, "output_contract 字段齐全",
                  "缺失：%s" % ", ".join(missing) if missing else "%d 个字段齐全" % len(fields))
        else:
            check(True, "output_contract 字段齐全（case.json 未声明，跳过逐字段比对）", "")

    if main_text:
        for label, pattern in REQUIRED_SECTIONS:
            check(re.search(pattern, main_text) is not None,
                  "主产物含必备要素：%s" % label, "")

    ev_path = os.path.join(out_dir, EVIDENCE_MAP)
    ev_text = read_text(ev_path)
    check(ev_text is not None and ev_text.strip(), "证据映射表存在", EVIDENCE_MAP)
    if main_text:
        cited = sorted(set(RE_SOURCE_MARK.findall(main_text)), key=int)
        check(len(cited) > 0, "主产物含 [S#] 来源标记", "共 %d 个" % len(cited))
        if ev_text:
            registered = set(RE_SOURCE_MARK.findall(ev_text)) | set(
                re.findall(r"\bS(\d+)\b", ev_text))
            missing = [s for s in cited if s not in registered]
            check(not missing, "引用的 [S#] 均已登记",
                  "未登记：%s" % ", ".join("S" + s for s in missing) if missing else "全部已登记")

    # ---- v2 WARN 级检查（校准纪律：只 WARN，不判 FAIL）----
    if isinstance(rj, dict):
        status = rj.get("status")
        unc = rj.get("uncertainty")
        if status in ("partial", "failed") and not unc:
            warn("W1 status 为 %s 但 uncertainty 为空" % status,
                 "partial/failed 必须逐条说明限制与未完成项")
        if "change_log" not in rj or "sources" not in rj:
            warn("W2 result.json 缺 change_log 或 sources",
                 "契约未声明时也建议保留：来源与修改记录是可核验性的基础")
        if status == "partial":
            has_skip_field = isinstance(rj.get("skipped_reason"), list) \
                and bool(rj.get("skipped_reason"))
            unc_text = " ".join(str(u) for u in unc) if isinstance(unc, list) else ""
            if not has_skip_field and not re.search(
                    r"skip|跳过|未完成|未译|中断|耗尽", unc_text):
                warn("W3 partial 但未说明跳过原因",
                     "建议用 finalize.py 固化交付并写 skipped_reason")
    if main_text:
        unsure_marks = re.findall(r"\[UNSURE[:：]", main_text)
        if unsure_marks and not re.search(r"未决[\s\S]{0,400}UNSURE", main_text):
            warn("W4 有 [UNSURE] 标注但未决项章节未汇总",
                 "每处 UNSURE 都要在未决项中列出原文、候选译法与需确认事项")
        if re.search(r"\[NOT_TRANSLATED", main_text) and re.search(
                r"翻译完成|全文完整|全部译完|complete", main_text, re.IGNORECASE):
            warn("W5 含 [NOT_TRANSLATED] 却声称翻译完成",
                 "漏段却报 complete 是负路径红线：未译段必须如实列入未决项")

    n_fail = n_warn = 0
    for lv, name, detail in results:
        if lv == "FAIL":
            n_fail += 1
        elif lv == "WARN":
            n_warn += 1
        print("[%s] %s%s" % (lv, name, (" —— " + detail) if detail else ""))
    print("[selfcheck] PASS %d，WARN %d，FAIL %d（WARN 不影响退出码）"
          % (len(results) - n_fail - n_warn, n_warn, n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
