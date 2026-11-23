#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_check.py — result.json 落盘前的契约前置校验（stdlib-only）。

用途：在把 result.json 写入 /app/output/ **之前**，先对草稿
（如 /app/work/result_draft.json）核对：
  1. case.json 可解析；
  2. 候选 result JSON 为合法 JSON；
  3. case_id 与 case.json 完全一致；
  4. output_contract 声明的全部原始字段逐项透传（字段名一字不差）；
  5. status ∈ {success, partial, failed}，且 sources / uncertainty /
     change_log（或 change_records）键齐全；
  6. status 为 partial/failed 时建议给出 skipped_reason（WARN，不阻断）。

本检查是建议性的自查，不作为交付门禁：退出码 1 表示存在建议修复项，
能修则修一轮后复查一次；无论退出码如何，都应照常把草稿落盘为
/app/output/result.json 交付，未修复项写入 result.json 的 uncertainty
与 skipped_reason。脚本退出码仅供定位问题，绝不阻止交付。

用法（绝对路径，不依赖 CWD，只读输入目录）：
  python3 /skills/weekly-skill/scripts/contract_check.py \
      --case-json /input/case.json --result-json /app/work/result_draft.json
"""
import argparse
import json
import os
import sys

results = []


def record(ok, name, detail="", warn=False):
    level = "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL")
    results.append((level, name, detail))


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def contract_fields(case):
    """从 case.json 提取 output_contract 声明的字段名，兼容 dict / list[str] / list[dict]。"""
    oc = case.get("output_contract") or case.get("outputContract") or {}
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for it in oc:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict):
                for k in ("name", "field", "key"):
                    if k in it:
                        fields.append(it[k])
                        break
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="result.json 落盘前的契约前置校验（建议性）：case_id 一致 + output_contract 字段齐全；退出码 1 表示存在建议修复项，无论退出码如何都应照常交付。")
    ap.add_argument("--case-json", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--result-json", required=True,
                    help="候选 result JSON（建议先写 /app/work/result_draft.json）")
    args = ap.parse_args(argv)

    case = None
    if not os.path.isfile(args.case_json):
        record(False, "case.json 存在", "不存在: %s" % args.case_json)
    else:
        try:
            case = json.loads(read_text(args.case_json))
            record(True, "case.json 合法 JSON")
        except (ValueError, OSError) as e:
            record(False, "case.json 合法 JSON", str(e))

    rj = None
    if not os.path.isfile(args.result_json):
        record(False, "候选 result JSON 存在", "不存在: %s" % args.result_json)
    else:
        try:
            rj = json.loads(read_text(args.result_json))
            record(True, "候选 result JSON 合法")
        except (ValueError, OSError) as e:
            record(False, "候选 result JSON 合法", str(e))

    if case is not None and rj is not None:
        cid = case.get("case_id") or case.get("id")
        record(rj.get("case_id") == cid, "case_id 透传一致",
               "case.json=%r result=%r" % (cid, rj.get("case_id")))
        fields = contract_fields(case)
        if fields:
            missing = [f for f in fields if f not in rj]
            record(not missing, "output_contract 字段透传齐全（%d 个）" % len(fields),
                   "缺失: %s" % ", ".join(missing) if missing else "全部透传")
        else:
            record(True, "output_contract 字段透传齐全",
                   "case.json 未声明 output_contract，跳过逐字段核对", warn=True)
        st = rj.get("status")
        record(st in ("success", "partial", "failed"),
               "status 诚实取值", "status=%r" % (st,))
        for key in ("sources", "uncertainty"):
            record(key in rj, "含 %s 键" % key)
        record(("change_log" in rj) or ("change_records" in rj),
               "含 change_log/change_records 键")
        if st in ("partial", "failed"):
            record("skipped_reason" in rj,
                   "partial/failed 时含 skipped_reason",
                   "建议列出未完成阶段及原因（交付韧性约定）", warn=True)

    n_fail = 0
    for level, name, detail in results:
        if level == "FAIL":
            n_fail += 1
        print("[%s] %s%s" % (level, name, (" — " + detail) if detail else ""))
    print("契约前置校验: %s（FAIL %d 项）" % ("FAIL" if n_fail else "PASS", n_fail))
    if n_fail:
        print("[提示] 建议修复候选 JSON 后复查一次；两轮后仍有 FAIL 时照常写入 "
              "/app/output/result.json 交付，未修复项记入 uncertainty/skipped_reason"
              "（退出码仅供定位问题，不作为交付门禁）")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
