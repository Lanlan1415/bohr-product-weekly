#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付自查脚本（阅读15｜文献知识图谱构建）。

对照运行契约逐项检查 /app/output：
1. result.json 存在且为合法 JSON；
2. result.json 含 case_id、status（success/partial/failed）、sources、
   uncertainty、change_log 字段；
3. 若提供 --case /input/case.json：case_id 与之一致，且 output_contract
   声明的全部原始字段都出现在 result.json 顶层；
4. 主产物齐全：图摘要（graph_summary.md）、三元组边表（*.csv）、result.json；
5. 证据标记：输出文件中存在来源标记（[S#] 或 source_id 列）；
6. 查询展示：图摘要中至少出现 3 个查询（"查询1/Q1/Query 1"等计数）。

v2 新增（只 WARN、不判 FAIL——原本能通过的草稿不会被新检查打回）：
- 存在 GraphML 导出（graph.graphml，可回导格式，由 graphml_roundtrip.py 验证）；
- 比较类边已带 condition（摘要或边表中出现 condition 列/比较条件说明）；
- result.json 含 skipped_reason 或 quality_gate 字段（finalize 习惯）；
- 输出含对齐名册痕迹（evidence_map.md 或 alignment_roster 文件）。

用法：
    python selfcheck.py --output /app/output [--case /input/case.json]

退出码：0 = 通过（可有 WARN）；1 = 存在 FAIL 项。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
stdlib-only，utf-8-sig 读文件，只读输入与输出目录，不依赖 CWD。
"""

import argparse
import glob
import json
import os
import re
import sys

STATUS_OK = {"success", "partial", "failed"}


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def contract_fields(contract):
    """从 output_contract 中提取字段名清单，兼容 dict / list 两种形态。"""
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


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="图谱交付物结构自查")
    parser.add_argument("--output", required=True, help="交付目录（如 /app/output）")
    parser.add_argument("--case", default=None, help="case.json 路径（可选）")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.output)
    results = []  # (ok, 说明)

    def check(ok, msg):
        results.append((bool(ok), msg))

    check(os.path.isdir(out_dir), "输出目录存在：%s" % out_dir)

    # ---- result.json ----
    rj_path = os.path.join(out_dir, "result.json")
    result = None
    if not os.path.isfile(rj_path):
        check(False, "result.json 存在")
    else:
        try:
            result = read_json(rj_path)
            check(True, "result.json 为合法 JSON")
        except (json.JSONDecodeError, OSError) as exc:
            check(False, "result.json 可解析（%s）" % exc)

    if isinstance(result, dict):
        check(bool(str(result.get("case_id") or "").strip()),
              "result.json 含非空 case_id")
        check(str(result.get("status") or "") in STATUS_OK,
              "status 属于 success/partial/failed（实际：%r）"
              % result.get("status"))
        for key in ("sources", "uncertainty", "change_log"):
            check(key in result, "result.json 含字段 '%s'" % key)
    else:
        check(False, "result.json 顶层为对象")

    # ---- 与 case.json 对齐 ----
    if args.case:
        case_path = os.path.abspath(args.case)
        try:
            case = read_json(case_path)
            cid = case.get("case_id")
            if isinstance(result, dict):
                check(result.get("case_id") == cid,
                      "case_id 与 case.json 一致（%r）" % cid)
            fields = contract_fields(case.get("output_contract"))
            if fields:
                missing = [f for f in fields
                           if not isinstance(result, dict) or f not in result]
                check(not missing,
                      "output_contract 全部字段透传（缺失：%s）"
                      % (", ".join(missing) if missing else "无"))
            else:
                check(True, "case.json 未声明 output_contract 字段，跳过透传检查")
        except (json.JSONDecodeError, OSError) as exc:
            check(False, "case.json 可解析（%s）" % exc)
    else:
        results.append((True, "未提供 --case，跳过契约对齐检查（正式交付前必须补做）"))

    # ---- 主产物 ----
    def has_glob(pat):
        return bool(glob.glob(os.path.join(out_dir, pat)))

    check(has_glob("graph_summary.md") or has_glob("*summary*.md"),
          "图摘要存在（graph_summary.md）")
    check(bool(glob.glob(os.path.join(out_dir, "*.csv"))),
          "三元组 CSV 存在（*.csv）")
    check(has_glob("result.json"), "result.json 文件存在")

    # ---- 证据标记 ----
    marker = re.compile(r"\[S\d+\]|source_id", re.IGNORECASE)
    hit = False
    for path in glob.glob(os.path.join(out_dir, "*.*")):
        if os.path.splitext(path)[1].lower() not in (".md", ".csv", ".txt", ".json"):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                if marker.search(f.read()):
                    hit = True
                    break
        except OSError:
            continue
    check(hit, "输出中存在来源标记（[S#] 或 source_id 列）")

    # ---- 查询数 ----
    q_ok = False
    for cand in glob.glob(os.path.join(out_dir, "*summary*.md")):
        try:
            with open(cand, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except OSError:
            continue
        found = re.findall(r"(?:查询|query|Q)\s*[:#]?\s*\d", text, re.IGNORECASE)
        if len(set(found)) >= 3 or len(found) >= 3:
            q_ok = True
            break
    check(q_ok, "图摘要展示至少 3 个实际执行的查询")

    # ---- v2 新增检查（只 WARN，不判 FAIL：不影响原本能通过的草稿）----
    warns = []
    if not has_glob("*.graphml"):
        warns.append("无 GraphML 导出（graph.graphml）：建议用 "
                     "graphml_roundtrip.py 导出并做回导一致性验证")
    csv_has_condition = False
    for p in glob.glob(os.path.join(out_dir, "*.csv")):
        try:
            with open(p, "r", encoding="utf-8-sig", newline="") as f:
                if "condition" in (f.readline() or ""):
                    csv_has_condition = True
                    break
        except OSError:
            continue
    if not csv_has_condition:
        warns.append("边表无 condition 列：比较类论断的比较条件无处安放"
                     "（比较-条件门要求比较边带 condition）")
    if isinstance(result, dict):
        if "skipped_reason" not in result and "quality_gate" not in result:
            warns.append("result.json 无 skipped_reason/quality_gate 字段"
                         "（降级原因与质量门结果建议显式记录）")
    has_roster = has_glob("evidence_map.md") or has_glob("*roster*")
    if not has_roster:
        warns.append("未见对齐名册/evidence_map（合并决策与对齐依据应留痕）")

    # ---- 汇总 ----
    print("=" * 60)
    print("交付自查（文献知识图谱构建）")
    print("=" * 60)
    fails = 0
    for ok, msg in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", msg))
        if not ok:
            fails += 1
    for w in warns:
        print("[WARN] %s" % w)
    print("-" * 60)
    print("结果：%s（FAIL %d / 共 %d 项；WARN %d 条不阻塞）"
          % ("未通过" if fails else "通过", fails, len(results), len(warns)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
