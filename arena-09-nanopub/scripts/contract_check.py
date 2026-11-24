# -*- coding: utf-8 -*-
"""contract_check.py — 契约前置校验（verify-then-write，v2 新增）

在**写入最终 /app/output/result.json 之前**，先对草稿 JSON 做确定性核对：
先验证、后落契约。避免"写完才发现缺契约字段"的返工。

检查项：
  1. case.json 与草稿 JSON 均可解析，草稿为 JSON 对象。
  2. 草稿含 case_id，且与 case.json 的 case_id 一致（若 case.json 提供）。
  3. output_contract 声明的全部原始字段在草稿顶层齐全（字段名逐字一致，
     不臆造、不改名）；缺失为 FAIL，多出的字段仅 WARN 提示。
  4. status ∈ {success, partial, failed}；诚实性字段
     sources / uncertainty / change_log 齐全。
  5. status 为 partial/failed 时建议提供 skipped_reason（WARN，v2 交付韧性）。
  6. 契约字段值为 null 时建议在 uncertainty 中有对应说明（WARN）。

用法：
    python contract_check.py --case /input/case.json --draft /app/work/result_draft.json

退出码：0 通过（允许 WARN）；1 未通过；2 参数错误。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
（缺字段补 null）并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
仅使用 Python 标准库；读文件一律 utf-8-sig；只读输入；不依赖 CWD 与网络。
"""
import argparse
import json
import os
import sys

ALLOWED_STATUS = {"success", "partial", "failed"}
HONESTY_FIELDS = ("sources", "uncertainty", "change_log")


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def contract_fields(case):
    """从 case.json 提取 output_contract 声明的字段名列表。"""
    oc = case.get("output_contract")
    if oc is None:
        return []
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        names = []
        for item in oc:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and "name" in item:
                names.append(item["name"])
        return names
    if isinstance(oc, str):
        return [oc]
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="契约前置校验：写入 result.json 之前核对 output_contract 字段齐全")
    ap.add_argument("--case", required=True, help="/input/case.json 绝对路径")
    ap.add_argument("--draft", required=True,
                    help="待核对的 result.json 草稿绝对路径（尚未交付）")
    args = ap.parse_args(argv)

    for label, path in (("case.json", args.case), ("草稿", args.draft)):
        if not os.path.isfile(path):
            print("错误：%s不存在：%s" % (label, path))
            return 2

    fails, warns = [], []

    try:
        case = json.loads(read_text(args.case))
        print("[PASS] case.json 是合法 JSON")
    except (ValueError, OSError) as exc:
        print("[FAIL] case.json 解析失败：%s" % exc)
        print("结论：未通过")
        return 1
    try:
        draft = json.loads(read_text(args.draft))
    except (ValueError, OSError) as exc:
        print("[FAIL] 草稿 JSON 解析失败：%s" % exc)
        print("结论：未通过")
        return 1
    if not isinstance(draft, dict):
        print("[FAIL] 草稿顶层必须是 JSON 对象")
        print("结论：未通过")
        return 1
    print("[PASS] 草稿是合法 JSON 对象")

    # case_id
    cid_case = case.get("case_id")
    cid_draft = draft.get("case_id")
    if not cid_draft:
        fails.append("草稿缺少 case_id")
    elif cid_case and cid_case != cid_draft:
        fails.append("case_id 不一致：case.json=%r 草稿=%r" % (cid_case, cid_draft))
    else:
        print("[PASS] case_id 一致：%s" % cid_draft)

    # output_contract 字段齐全性（先验证后落契约的核心检查）
    fields = contract_fields(case)
    missing = [f for f in fields if f not in draft]
    if missing:
        fails.append("草稿缺少 output_contract 声明的字段 %d 个：%s"
                     % (len(missing), "、".join(missing)))
    else:
        print("[PASS] output_contract 全部 %d 个字段已在草稿中就位" % len(fields))
    extra = sorted(k for k in draft
                   if k not in fields
                   and k not in (("case_id", "status") + HONESTY_FIELDS
                                 + ("skipped_reason",)))
    if extra:
        warns.append("草稿含契约外字段（允许，但确认非笔误）：%s" % "、".join(extra))
    null_fields = [f for f in fields if f in draft and draft[f] is None]
    if null_fields:
        warns.append("契约字段为 null（须已在 uncertainty 说明原因）：%s"
                     % "、".join(null_fields))

    # status 与诚实性字段
    status = draft.get("status")
    if status not in ALLOWED_STATUS:
        fails.append("status 非法：%r（应为 success/partial/failed）" % (status,))
    else:
        print("[PASS] status=%s" % status)
    for key in HONESTY_FIELDS:
        if key not in draft:
            fails.append("草稿缺少诚实性字段：%s" % key)
        else:
            print("[PASS] 草稿含字段 %s" % key)
    if status in ("partial", "failed") and "skipped_reason" not in draft:
        warns.append("status=%s 但未提供 skipped_reason：建议逐条列出被跳过阶段"
                     "与原因（v2 交付韧性约定）" % status)

    for w in warns:
        print("[WARN] " + w)
    for f in fails:
        print("[FAIL] " + f)
    print("----")
    print("契约前置校验：FAIL=%d WARN=%d" % (len(fails), len(warns)))
    if fails:
        print("结论：未通过（修复后再写入 /app/output/result.json）")
        return 1
    print("结论：通过（可以写入 /app/output/result.json）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
