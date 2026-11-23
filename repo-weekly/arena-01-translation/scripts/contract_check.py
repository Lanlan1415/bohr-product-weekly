#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""契约前置校验（文献翻译技能）：在写入/交付 result.json **之前**，
先用本脚本核对 output_contract 声明的字段齐全，避免"契约缺字段导致整案无效"。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/contract_check.py \
        --case /input/case.json --result /app/output/result.json

校验项（任一 FAIL → 退出码 1）：
  1. case.json 存在、可解析、含 case_id；
  2. result 文件存在且是合法 JSON 对象；
  3. result.case_id 与 case.json 的 case_id 逐字一致；
  4. output_contract 声明的全部字段都在 result 顶层（兼容 dict/list/str 声明形式）；
  5. result.status 属于 success/partial/failed。

校准纪律（v2 新增）：字段值与 output_contract 的类型提示（"string"/"array"/"object"）
不一致时只报 WARN，不判 FAIL——新检查项一律 WARN 起步，观察稳定后才允许升级 FAIL。

退出码：0 全部 PASS（允许 WARN）；1 存在 FAIL 或参数/IO 错误。
（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读取一律 utf-8-sig；只读，不修改任何文件；不访问网络。
"""
import argparse
import json
import os
import sys

ALLOWED_STATUS = ("success", "partial", "failed")
TYPE_HINTS = {"string": str, "str": str, "array": list, "list": list,
              "object": dict, "dict": dict, "number": (int, float),
              "integer": int, "boolean": bool, "bool": bool}


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def contract_fields(case_obj):
    """从 case.json 提取 output_contract 声明的 [(字段名, 类型提示)] 列表。"""
    if not isinstance(case_obj, dict):
        return []
    oc = case_obj.get("output_contract")
    if isinstance(oc, dict):
        return [(str(k), v if isinstance(v, str) else "") for k, v in oc.items()]
    if isinstance(oc, list):
        return [(str(x), "") for x in oc]
    if isinstance(oc, str):
        return [(oc, "")]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="契约前置校验：写入 result.json 前核对 output_contract 字段齐全")
    parser.add_argument("--case", required=True, help="case.json 绝对路径，例如 /input/case.json")
    parser.add_argument("--result", required=True,
                        help="待校验的 result.json 绝对路径（可以是尚未交付的草稿）")
    args = parser.parse_args(argv)

    results = []  # (级别 PASS/FAIL/WARN, 名称, 细节)

    def check(level, name, detail=""):
        if isinstance(level, bool):
            level = "PASS" if level else "FAIL"
        results.append((level, name, detail))

    case_text = read_text(os.path.abspath(args.case))
    if case_text is None:
        print("[FAIL] case.json 不可读：%s" % os.path.abspath(args.case))
        return 1
    try:
        case_obj = json.loads(case_text)
        check("PASS", "case.json 是合法 JSON", "")
    except json.JSONDecodeError as exc:
        print("[FAIL] case.json 不是合法 JSON：%s" % exc)
        return 1

    case_id = case_obj.get("case_id") if isinstance(case_obj, dict) else None
    check(bool(case_id), "case.json 含 case_id", str(case_id))

    res_text = read_text(os.path.abspath(args.result))
    if res_text is None:
        print("[FAIL] result 文件不可读：%s" % os.path.abspath(args.result))
        return 1
    try:
        res = json.loads(res_text)
        check(isinstance(res, dict), "result 是 JSON 对象", "")
        if not isinstance(res, dict):
            res = {}
    except json.JSONDecodeError as exc:
        check("FAIL", "result 是合法 JSON", str(exc))
        res = {}

    if res:
        check(res.get("case_id") == case_id, "case_id 与 case.json 逐字一致",
              "result=%s case=%s" % (res.get("case_id"), case_id))
        check(res.get("status") in ALLOWED_STATUS,
              "status 合法（success/partial/failed）", str(res.get("status")))
        fields = contract_fields(case_obj)
        if fields:
            missing = [name for name, _ in fields if name not in res]
            check("PASS" if not missing else "FAIL", "output_contract 字段齐全",
                  ("缺失：%s" % ", ".join(missing)) if missing
                  else "%d 个字段齐全" % len(fields))
            for name, hint in fields:
                if name in res and hint:
                    ptype = TYPE_HINTS.get(hint.strip().lower())
                    if ptype is not None and res[name] is not None \
                            and not isinstance(res[name], ptype):
                        check("WARN", "字段类型提示不一致：%s" % name,
                              "声明 %s，实际 %s" % (hint, type(res[name]).__name__))
        else:
            check("WARN", "case.json 未声明 output_contract，跳过逐字段比对", "")
    else:
        check("FAIL", "result 是合法 JSON", "空对象或解析失败")

    n_fail = sum(1 for lv, _, _ in results if lv == "FAIL")
    n_warn = sum(1 for lv, _, _ in results if lv == "WARN")
    for lv, name, detail in results:
        print("[%s] %s%s" % (lv, name, (" —— " + detail) if detail else ""))
    print("[contract_check] PASS %d，WARN %d，FAIL %d"
          % (len(results) - n_fail - n_warn, n_warn, n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
