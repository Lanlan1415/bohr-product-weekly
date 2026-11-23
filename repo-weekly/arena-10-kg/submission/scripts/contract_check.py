#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_check.py —— 契约前置校验（阅读15｜文献知识图谱构建）。

在把 result.json 写入 /app/output **之前**，先用本脚本核对草稿：
1. 草稿是合法 JSON、顶层为对象；
2. case_id 与 case.json 逐字一致；
3. output_contract 声明的全部原始字段都出现在草稿顶层（字段名一字不差）；
4. 可选 --require-nonempty：契约字段的值不得为 null/空串/空数组
   （做不到的字段应先在草稿中显式填 null 并在 uncertainty 说明，
   本开关用于最终交付前的加严复核）。

用法：
    python3 /skills/weekly-skill/scripts/contract_check.py \
        --case /input/case.json --result /app/work/result_draft.json \
        [--require-nonempty]

退出码：0 = 通过；1 = 存在缺项/不一致。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
（缺字段补 null）并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
stdlib-only；utf-8-sig；只读输入；不依赖 CWD；不联网。
"""

import argparse
import json
import os
import sys


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


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="result.json 契约前置校验")
    parser.add_argument("--case", required=True, help="/input/case.json")
    parser.add_argument("--result", required=True, help="result.json 草稿路径")
    parser.add_argument("--require-nonempty", action="store_true",
                        help="加严：契约字段值不得为空（最终交付前用）")
    args = parser.parse_args(argv)

    errors, notes = [], []
    try:
        with open(os.path.abspath(args.case), "r", encoding="utf-8-sig") as f:
            case = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print("[FAIL] case.json 不可解析：%s" % exc)
        return 1
    try:
        with open(os.path.abspath(args.result), "r", encoding="utf-8-sig") as f:
            result = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print("[FAIL] result 草稿不可解析：%s" % exc)
        return 1
    if not isinstance(result, dict):
        print("[FAIL] result 草稿顶层不是对象")
        return 1

    cid = case.get("case_id")
    if result.get("case_id") != cid:
        errors.append("case_id 不一致：草稿 %r ≠ case.json %r"
                      % (result.get("case_id"), cid))
    else:
        notes.append("case_id 一致：%r" % cid)

    fields = contract_fields(case.get("output_contract"))
    if not fields:
        notes.append("case.json 未声明 output_contract 字段，仅核对 case_id")
    for f in fields:
        if f not in result:
            errors.append("契约字段缺失：%r（字段名以 case.json 为准，"
                          "不删不改名；做不到填 null 并在 uncertainty 说明）" % f)
        elif args.require_nonempty and result[f] in (None, "", [], {}):
            errors.append("契约字段 %r 为空（--require-nonempty 模式）" % f)
        else:
            notes.append("字段 %r 已透传" % f)

    print("=" * 60)
    print("契约前置校验（result.json 写盘前）")
    print("=" * 60)
    for n in notes:
        print("[PASS] %s" % n)
    for e in errors:
        print("[FAIL] %s" % e)
    print("结果：%s（字段 %d 个，缺/错 %d 个）"
          % ("未通过" if errors else "通过", len(fields), len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
