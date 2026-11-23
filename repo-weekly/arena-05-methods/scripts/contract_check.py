#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_check.py — result.json 落盘前的契约前置校验（玻尔周赛 Skill 通用）。

在把 result 草稿落盘为 /app/output/result.json **之前**运行，核对：
1. 草稿为合法 JSON、顶层为对象；
2. case_id 非空，且与 case.json 的 case_id 逐字一致（提供 --case 时）；
3. case.json 的 output_contract 声明的全部原始字段出现在草稿顶层
   （字段名一字不差，不臆造、不改名、不漏项；值可为 null 但字段必须在）；
4. status 属于 success/partial/failed；sources、uncertainty、change_log 字段存在。

WARN 级（不阻断落盘，只提醒）：
- status 为 partial/failed 时 uncertainty 应为非空；
- 存在 skipped_reason 字段时其内容应非空（交付韧性：跳过阶段须写明原因）。

用法：
    python3 /skills/weekly-skill/scripts/contract_check.py \
        --case /input/case.json --result /app/work/result_draft.json \
        [--report /app/work/contract_check.md]

退出码：0 = 无 FAIL 项；1 = 存在建议修复项。本检查是建议性的自查，不作为
交付门禁：无论退出码如何，都应照常把草稿落盘为 /app/output/result.json 交付，
未修复的 FAIL 项逐项写入 result.json 的 uncertainty 与 skipped_reason。
脚本退出码仅供定位问题，绝不阻止交付。
stdlib-only，utf-8-sig 读文件，只读输入，不依赖网络与 CWD，路径输出用正斜杠。
"""

import argparse
import json
import os
import sys

STATUS_OK = {"success", "partial", "failed"}


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def contract_fields(contract):
    """从 output_contract（dict 或 list）提取字段名清单。"""
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    if isinstance(contract, list):
        out = []
        for item in contract:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for k in ("name", "field", "key", "id"):
                    if k in item:
                        out.append(str(item[k]))
                        break
        return out
    return []


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="result.json 落盘前的契约前置校验（建议性）：核对 case_id 与 output_contract 字段齐全；退出码 1 表示存在建议修复项，无论退出码如何都应照常交付并在 uncertainty 中记录未修复项。")
    parser.add_argument("--case", required=True, help="/input/case.json 路径")
    parser.add_argument("--result", required=True,
                        help="待校验的 result 草稿路径（如 /app/work/result_draft.json）")
    parser.add_argument("--report", default=None,
                        help="可选：把校验结果同时写入该 .md 路径留痕")
    args = parser.parse_args(argv)

    results = []  # (level, msg)，level ∈ {PASS, WARN, FAIL}

    def check(level, ok, msg):
        results.append((level if ok else "FAIL", msg))

    # ---- case.json ----
    case = None
    case_path = os.path.abspath(args.case)
    try:
        case = read_json(case_path)
        results.append(("PASS", "case.json 可解析：%s" % case_path.replace(os.sep, "/")))
    except (json.JSONDecodeError, OSError) as exc:
        results.append(("FAIL", "case.json 可解析（%s）" % exc))

    # ---- result 草稿 ----
    draft = None
    draft_path = os.path.abspath(args.result)
    if not os.path.isfile(draft_path):
        results.append(("FAIL", "result 草稿存在：%s" % draft_path.replace(os.sep, "/")))
    else:
        try:
            draft = read_json(draft_path)
            results.append(("PASS", "result 草稿为合法 JSON"))
        except (json.JSONDecodeError, OSError) as exc:
            results.append(("FAIL", "result 草稿可解析（%s）" % exc))

    if draft is not None and not isinstance(draft, dict):
        results.append(("FAIL", "result 草稿顶层为对象"))
        draft = None

    if isinstance(draft, dict):
        check("PASS", bool(str(draft.get("case_id") or "").strip()),
              "草稿含非空 case_id")
        status = str(draft.get("status") or "")
        check("PASS", status in STATUS_OK,
              "status 属于 success/partial/failed（实际：%r）" % draft.get("status"))
        for key in ("sources", "uncertainty", "change_log"):
            check("PASS", key in draft, "草稿含字段 '%s'" % key)
        if status in ("partial", "failed") and not draft.get("uncertainty"):
            results.append(("WARN",
                            "status=%s 但 uncertainty 为空：落盘前建议写明哪里不完整" % status))
        if "skipped_reason" in draft and not draft.get("skipped_reason"):
            results.append(("WARN",
                            "存在 skipped_reason 字段但内容为空：跳过的阶段须写明原因"))

    # ---- 契约字段对齐 ----
    if isinstance(case, dict) and isinstance(draft, dict):
        cid = case.get("case_id")
        check("PASS", draft.get("case_id") == cid,
              "case_id 与 case.json 逐字一致（%r）" % cid)
        fields = contract_fields(case.get("output_contract"))
        if fields:
            missing = [f for f in fields if f not in draft]
            check("PASS", not missing,
                  "output_contract 全部字段透传（缺失：%s）"
                  % (", ".join(missing) if missing else "无"))
            null_fields = [f for f in fields
                           if f in draft and draft.get(f) is None]
            if null_fields:
                results.append(("WARN",
                                "契约字段值为 null：%s（允许，但须在 uncertainty 说明原因）"
                                % ", ".join(null_fields)))
        else:
            results.append(("PASS", "case.json 未声明 output_contract 字段，跳过透传检查"))

    # ---- 汇总 ----
    lines = []
    lines.append("# 契约前置校验报告（result.json 落盘前）")
    lines.append("")
    lines.append("case：`%s`" % case_path.replace(os.sep, "/"))
    lines.append("草稿：`%s`" % draft_path.replace(os.sep, "/"))
    lines.append("")
    n_fail = sum(1 for lv, _ in results if lv == "FAIL")
    n_warn = sum(1 for lv, _ in results if lv == "WARN")
    for lv, msg in results:
        lines.append("- [%s] %s" % (lv, msg))
    lines.append("")
    lines.append("结果：%s（FAIL %d / WARN %d / 共 %d 项）—— %s"
                 % ("无 FAIL 项" if not n_fail else "存在建议修复项",
                    n_fail, n_warn, len(results),
                    "退出码 0" if not n_fail else "建议补齐缺失字段后复查一次；退出码 1 不阻止交付，未修复项记入 uncertainty/skipped_reason 后照常落盘"))
    text = "\n".join(lines) + "\n"

    print("=" * 60)
    print("契约前置校验（result.json 落盘前）")
    print("=" * 60)
    for lv, msg in results:
        print("[%s] %s" % (lv, msg))
    print("-" * 60)
    print("结果：%s（FAIL %d / WARN %d / 共 %d 项）退出码 %d（退出码仅供定位问题，不作为交付门禁）"
          % ("无 FAIL 项" if not n_fail else "存在建议修复项",
             n_fail, n_warn, len(results), 1 if n_fail else 0))

    if args.report:
        rep = os.path.abspath(args.report)
        rep_dir = os.path.dirname(rep)
        if rep_dir:
            os.makedirs(rep_dir, exist_ok=True)
        try:
            with open(rep, "w", encoding="utf-8") as f:
                f.write(text)
            print("报告已写入：%s" % rep.replace(os.sep, "/"))
        except OSError as exc:
            print("警告：无法写出报告（%s）" % exc, file=sys.stderr)

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
