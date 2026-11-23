#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付固化（finalize，文献翻译技能）：交付韧性兜底——
无论主流程走到哪一步、是否中断，都把当前的**诚实状态**固化为 /app/output 下的
可交付物：已译完的段落保持双语对照交付，未完成的显式登记 skipped_reason，
绝不整案失败、绝不编造译文。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/finalize.py \
        --work /app/work --output /app/output --case /input/case.json \
        [--status partial] [--skipped "步骤4: 预算耗尽，P040-P042 未译"] ...

行为：
  1. 必备交付物盘点：bilingual_translation.md / glossary.tsv / evidence_map.md /
     result.json。
     - 主产物缺失但 work 中有 translation_draft.md → 以草稿为基础组装一份
       显式标注 NOT_COMPLETED 的对照稿（保留已译段落），不编造任何译文；
     - 其他必备物缺失 → 写显式 NOT_COMPLETED 占位或登记 skipped_reason；
     - glossary.tsv 缺失但 work 中有 → 复制过来（复用，不重复劳动）。
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

PLACEHOLDER = """# {title}（未完成占位 / NOT_COMPLETED）

> **本文件由 scripts/finalize.py 生成的诚实占位，不是正式产物。**
> 主流程在产出该文件前中断或对应步骤失败。
> 已完成的中间产物保留在 /app/work/ 下，可人工接管续做。
> 中断/跳过原因见同目录 result.json 的 skipped_reason 与 uncertainty。
"""

DRAFT_HEADER = """# 双语对照译文（未完成固化稿 / NOT_COMPLETED）

> **本稿由 scripts/finalize.py 基于 /app/work/translation_draft.md 固化：**
> 主流程中断，以下为中断前已译完的段落，原样保留双语对照；
> 未译段落以原文 + [NOT_TRANSLATED] 形式保留在 draft 中，绝不编造译文。
> 中断/跳过原因见同目录 result.json 的 skipped_reason 与 uncertainty。

---

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
    main_path = os.path.join(out_dir, "bilingual_translation.md")
    if os.path.isfile(main_path):
        print("  [OK] bilingual_translation.md 已存在")
    else:
        draft = find_in_work(work_dir, "translation_draft.md")
        draft_text = read_text(draft) if draft else None
        try:
            if draft_text and draft_text.strip():
                write_text(main_path, DRAFT_HEADER + draft_text)
                skipped.append("主产物未组装：以 translation_draft.md 固化（已译段落保留，"
                               "未译段落见 draft 中的 [NOT_TRANSLATED] 标注）")
                print("  [固化] bilingual_translation.md ← translation_draft.md（诚实部分）")
            else:
                write_text(main_path, PLACEHOLDER.format(title="双语对照译文"))
                skipped.append("产物 bilingual_translation.md 未生成（主流程中断或步骤失败）")
                print("  [占位] bilingual_translation.md —— 已写诚实占位")
        except OSError as exc:
            sys.stderr.write("[finalize] 错误：主产物不可写：%s（%s）\n" % (main_path, exc))
            return 1

    for fname, title in (("glossary.tsv", "术语表"), ("evidence_map.md", "证据映射表")):
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
        if fname == "evidence_map.md":
            try:
                write_text(target, PLACEHOLDER.format(title=title))
            except OSError as exc:
                sys.stderr.write("[finalize] 错误：占位文件不可写：%s（%s）\n" % (target, exc))
                return 1
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
