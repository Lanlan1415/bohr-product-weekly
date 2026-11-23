#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付固化（finalize，文献文档解析技能）：交付韧性兜底——
无论主流程走到哪一步、是否中断，都把当前的**诚实状态**固化为 /app/output 下的
可交付物：已完成的保留，未完成的显式登记 skipped_reason，绝不整案失败、
绝不编造内容。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/finalize.py \
        --work /app/work --output /app/output --case /input/case.json \
        [--status partial] [--skipped "步骤3: OCR 排队超时，p.5-6 未识别"] ...

行为：
  1. 必备交付物盘点：parsed_document.md / evidence_map.md / survey.json / result.json。
     - 主产物或证据映射缺失 → 写一个**显式标注 NOT_COMPLETED 的诚实占位文件**
       （说明中断位置与已完成中间产物的去向），不编造解析内容；
     - survey.json 缺失但 /app/work 中能找得到 → 复制过来（复用，不重复解析）。
  2. result.json：不存在则新建；补齐 case_id 与 output_contract 声明的全部字段
     （缺失字段按声明类型填空值，并在 uncertainty 逐条说明）；status 缺省 partial；
     --skipped 与自动发现的缺失产物逐条写入顶层 skipped_reason 数组，
     并同步摘要进 uncertainty。
  3. 收尾时按 contract_check.py 同口径复核契约字段并打印结果。

退出码：0 固化完成（哪怕 status 是 partial/failed——诚实交付即成功）；
1 仅在输出目录不可写等致命 IO 错误。
仅使用 Python 标准库；utf-8-sig 读取；不修改 /input；不访问网络。
"""
import argparse
import json
import os
import shutil
import sys

ALLOWED_STATUS = ("success", "partial", "failed")

# 必备交付物：(文件名, 缺失时是否写诚实占位)
EXPECTED = [
    ("parsed_document.md", True),
    ("evidence_map.md", True),
    ("survey.json", False),   # 优先从 work 目录复制；找不到才登记缺失
    ("result.json", False),   # 由本脚本直接生成/补齐
]

PLACEHOLDER = """# {title}（未完成占位 / NOT_COMPLETED）

> **本文件由 scripts/finalize.py 生成的诚实占位，不是正式产物。**
> 主流程在产出该文件前中断或对应步骤失败。
> 已完成的中间产物保留在 /app/work/ 下，可人工接管续做。
> 中断/跳过原因见同目录 result.json 的 skipped_reason 与 uncertainty。
"""


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def contract_fields(case_obj):
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


def empty_value(hint):
    h = (hint or "").strip().lower()
    if h in ("array", "list"):
        return []
    if h in ("object", "dict"):
        return {}
    if h in ("number", "integer"):
        return 0
    if h in ("boolean", "bool"):
        return False
    return ""


def find_in_work(work_dir, filename):
    """在 work 目录（含一级子目录）中寻找同名文件，返回路径或 None。"""
    if not os.path.isdir(work_dir):
        return None
    for root, _dirs, files in os.walk(work_dir):
        if filename in files:
            return os.path.join(root, filename)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="交付固化：中断/失败时也能交付诚实部分 + skipped_reason")
    parser.add_argument("--work", required=True, help="工作目录绝对路径，例如 /app/work")
    parser.add_argument("--output", required=True, help="交付目录绝对路径，例如 /app/output")
    parser.add_argument("--case", default=None, help="case.json 绝对路径（可选但强烈建议）")
    parser.add_argument("--status", default="partial",
                        choices=ALLOWED_STATUS, help="交付状态，缺省 partial")
    parser.add_argument("--skipped", action="append", default=[],
                        help="跳过/未完成事项说明，可重复；逐条写入 skipped_reason")
    args = parser.parse_args(argv)

    work_dir = os.path.abspath(args.work)
    out_dir = os.path.abspath(args.output)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        sys.stderr.write("[finalize] 错误：输出目录不可创建：%s（%s）\n" % (out_dir, exc))
        return 1

    skipped = list(args.skipped)
    print("[finalize] 固化交付 -> %s" % out_dir)

    # ---- 1. 必备交付物盘点 ----
    for fname, make_placeholder in EXPECTED:
        if fname == "result.json":
            continue
        target = os.path.join(out_dir, fname)
        if os.path.isfile(target):
            print("  [OK] %s 已存在" % fname)
            continue
        src = find_in_work(work_dir, fname)
        if src:
            try:
                shutil.copyfile(src, target)
                print("  [OK] %s 从 work 复制：%s" % (fname, src.replace(os.sep, "/")))
                continue
            except OSError:
                pass
        if make_placeholder:
            title = "文献解析结果" if fname == "parsed_document.md" else "证据映射表"
            reason = "产物 %s 未生成（主流程中断或对应步骤失败）" % fname
            try:
                write_text(target, PLACEHOLDER.format(title=title))
            except OSError as exc:
                sys.stderr.write("[finalize] 错误：占位文件不可写：%s（%s）\n" % (target, exc))
                return 1
            skipped.append(reason)
            print("  [占位] %s —— %s" % (fname, reason))
        else:
            skipped.append("产物 %s 未生成且 work 中无副本" % fname)
            print("  [缺失] %s —— 已登记 skipped_reason" % fname)

    # ---- 2. result.json 生成/补齐 ----
    case_obj = None
    if args.case:
        case_text = read_text(os.path.abspath(args.case))
        if case_text is not None:
            try:
                case_obj = json.loads(case_text)
            except json.JSONDecodeError:
                case_obj = None

    rj_path = os.path.join(out_dir, "result.json")
    rj = {}
    old_text = read_text(rj_path)
    if old_text is not None:
        try:
            parsed = json.loads(old_text)
            if isinstance(parsed, dict):
                rj = parsed
        except json.JSONDecodeError:
            skipped.append("原 result.json 不是合法 JSON，已按诚实状态重建")

    if case_obj and case_obj.get("case_id"):
        if rj.get("case_id") not in (None, case_obj.get("case_id")):
            skipped.append("原 result.json 的 case_id 与 case.json 不一致，已按 case.json 纠正")
        rj["case_id"] = case_obj.get("case_id")

    fields = contract_fields(case_obj)
    filled = []
    for name, hint in fields:
        if name not in rj:
            rj[name] = empty_value(hint)
            filled.append(name)
    if filled:
        unc = rj.setdefault("uncertainty", [])
        if isinstance(unc, list):
            unc.append("finalize 补齐了缺失的契约字段（空值占位）：%s" % ", ".join(filled))

    if rj.get("status") not in ALLOWED_STATUS:
        rj["status"] = args.status
    elif args.status != "partial":
        rj["status"] = args.status

    if skipped:
        existing = rj.get("skipped_reason")
        merged = list(existing) if isinstance(existing, list) else []
        for s in skipped:
            if s not in merged:
                merged.append(s)
        rj["skipped_reason"] = merged
        unc = rj.setdefault("uncertainty", [])
        if isinstance(unc, list):
            for s in skipped:
                entry = "skipped: %s" % s
                if entry not in unc:
                    unc.append(entry)
        if rj.get("status") == "success":
            rj["status"] = "partial"
            unc2 = rj.get("uncertainty")
            if isinstance(unc2, list):
                unc2.append("存在 skipped 事项，status 由 success 下调为 partial")

    cl = rj.setdefault("change_log", [])
    if isinstance(cl, list):
        cl.append({"step": "finalize",
                   "action": "固化交付：skipped %d 项，status=%s" % (len(skipped), rj.get("status"))})

    try:
        write_text(rj_path, json.dumps(rj, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        sys.stderr.write("[finalize] 错误：result.json 不可写：%s（%s）\n" % (rj_path, exc))
        return 1
    print("  [OK] result.json 已固化：status=%s，skipped %d 项" % (rj.get("status"), len(skipped)))

    # ---- 3. 契约复核（contract_check 同口径）----
    n_fail = 0
    if case_obj and fields:
        missing = [name for name, _ in fields if name not in rj]
        if missing:
            n_fail += 1
            print("  [FAIL] 契约字段仍缺失：%s" % ", ".join(missing))
        else:
            print("  [PASS] output_contract 全部 %d 个字段齐全" % len(fields))
        if case_obj.get("case_id") and rj.get("case_id") != case_obj.get("case_id"):
            n_fail += 1
            print("  [FAIL] case_id 不一致")
    else:
        print("  [WARN] 未提供可用 case.json，跳过契约逐字段复核")

    print("[finalize] 完成：诚实交付已固化（skipped 不等于失败；缺失均已显式登记）")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
