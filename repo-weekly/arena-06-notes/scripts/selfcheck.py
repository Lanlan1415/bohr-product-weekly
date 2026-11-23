# -*- coding: utf-8 -*-
"""selfcheck.py — 交付自查（阅读10：文献总结与结构化笔记）

对 /app/output（或参数指定目录）做交付前确定性检查：
  1. 主产物 notes.md 存在且非空；证据映射 evidence_map.md 存在。
  2. result.json 存在、是合法 JSON、含 case_id、status ∈ {success, partial, failed}，
     且含 sources / uncertainty / change_log 三个诚实性字段。
  3. 若提供 case.json：result.json 必须包含 output_contract 声明的全部原始字段
     （字段名以 case.json 为准，不臆造）。
  4. notes.md 中的 [S#] 来源标记存在；若提供登记表，编号必须已登记。
  5. result.json 中 status=success 时不应出现未填占位符（TODO/待补）。
  6. （v2，仅 WARN）status=partial/failed 时建议提供 skipped_reason 字段
     （交付韧性；不误判 v1 草稿）。

用法：
    python selfcheck.py --out <output_dir> [--case <case.json>]
                        [--register <materials_register.md>] [--main notes.md]

退出码：0 通过；1 未通过；2 参数错误。
（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读文件一律 utf-8-sig；只读被检查目录；
不依赖当前工作目录（CWD）。
"""
import argparse
import json
import os
import re
import sys

S_MARK_RE = re.compile(r"\[S(\d+)[\s:：\]p]")
REG_ROW_RE = re.compile(r"^\|\s*S(\d+)\s*\|", re.MULTILINE)
ALLOWED_STATUS = {"success", "partial", "failed"}


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
    ap = argparse.ArgumentParser(description="交付自查（阅读10）")
    ap.add_argument("--out", required=True, help="输出目录绝对路径（如 /app/output）")
    ap.add_argument("--case", default=None, help="/input/case.json 绝对路径")
    ap.add_argument("--register", default=None, help="materials_register.md 绝对路径")
    ap.add_argument("--main", default="notes.md", help="主产物文件名（默认 notes.md）")
    args = ap.parse_args(argv)

    fails, warns = [], []
    if not os.path.isdir(args.out):
        print("[FAIL] 输出目录不存在：%s" % args.out)
        print("结论：未通过")
        return 1

    # 1. 主产物与证据映射
    notes_path = os.path.join(args.out, args.main)
    if not os.path.isfile(notes_path) or os.path.getsize(notes_path) == 0:
        fails.append("主产物缺失或为空：%s" % notes_path)
    else:
        print("[PASS] 主产物存在：%s（%d 字节）"
              % (args.main, os.path.getsize(notes_path)))
    ev_path = os.path.join(args.out, "evidence_map.md")
    if not os.path.isfile(ev_path):
        fails.append("证据映射文件缺失：evidence_map.md")
    else:
        print("[PASS] 证据映射文件存在：evidence_map.md")
    cmp_path = os.path.join(args.out, "comparison_matrix.md")
    if not os.path.isfile(cmp_path):
        warns.append("未发现 comparison_matrix.md（多篇文献案例应提供横向对比矩阵）")

    # 2. result.json
    rj_path = os.path.join(args.out, "result.json")
    result = None
    if not os.path.isfile(rj_path):
        fails.append("result.json 缺失")
    else:
        try:
            result = json.loads(read_text(rj_path))
            print("[PASS] result.json 是合法 JSON")
        except (ValueError, OSError) as exc:
            fails.append("result.json 解析失败：%s" % exc)
    if isinstance(result, dict):
        if not result.get("case_id"):
            fails.append("result.json 缺少 case_id")
        else:
            print("[PASS] result.json 含 case_id：%s" % result["case_id"])
        status = result.get("status")
        if status not in ALLOWED_STATUS:
            fails.append("result.json status 非法：%r（应为 success/partial/failed）"
                         % (status,))
        else:
            print("[PASS] result.json status=%s" % status)
        for key in ("sources", "uncertainty", "change_log"):
            if key not in result:
                fails.append("result.json 缺少诚实性字段：%s" % key)
            else:
                print("[PASS] result.json 含字段 %s" % key)
        # v2（仅 WARN，不误判 v1 草稿）：partial/failed 建议带 skipped_reason
        if result.get("status") in ("partial", "failed") \
                and "skipped_reason" not in result:
            warns.append("status=%s 但无 skipped_reason 字段：建议逐条列出被跳过"
                         "阶段与原因（v2 交付韧性约定，校验器校准：仅提示不判 FAIL）"
                         % result.get("status"))

    # 3. 契约字段透传
    if args.case and isinstance(result, dict):
        if not os.path.isfile(args.case):
            fails.append("case.json 不存在：%s" % args.case)
        else:
            try:
                case = json.loads(read_text(args.case))
                fields = contract_fields(case)
                missing = [f for f in fields if f not in result]
                if missing:
                    fails.append("result.json 缺少 output_contract 声明的字段：%s"
                                 % "、".join(missing))
                else:
                    print("[PASS] output_contract 全部 %d 个字段已透传" % len(fields))
                cid = case.get("case_id")
                if cid and result.get("case_id") and cid != result.get("case_id"):
                    fails.append("case_id 不一致：case.json=%r result.json=%r"
                                 % (cid, result.get("case_id")))
            except (ValueError, OSError) as exc:
                fails.append("case.json 解析失败：%s" % exc)

    # 4. [S#] 标记存在且已登记
    if os.path.isfile(notes_path):
        text = read_text(notes_path)
        marks = set(int(x) for x in S_MARK_RE.findall(text))
        if not marks:
            fails.append("notes.md 中未发现任何 [S#] 来源标记")
        else:
            print("[PASS] notes.md 含 %d 个不同来源标记：%s"
                  % (len(marks), "、".join("S%d" % i for i in sorted(marks))))
        if args.register and os.path.isfile(args.register):
            reg = set(int(x) for x in REG_ROW_RE.findall(read_text(args.register)))
            unknown = sorted(marks - reg)
            if unknown:
                fails.append("notes.md 引用了未登记来源：%s"
                             % "、".join("S%d" % i for i in unknown))
            else:
                print("[PASS] 全部来源标记已登记")

    # 5. 占位符与 status 一致性
    if isinstance(result, dict) and result.get("status") == "success":
        for path in (notes_path, ev_path):
            if os.path.isfile(path):
                body = read_text(path)
                if re.search(r"TODO|待补|占位|PLACEHOLDER|XXX", body, re.IGNORECASE):
                    warns.append("%s 含占位符痕迹，但 status=success（应改为 partial）"
                                 % os.path.basename(path))

    for w in warns:
        print("[WARN] " + w)
    for f in fails:
        print("[FAIL] " + f)
    print("----")
    print("自查结果：FAIL=%d WARN=%d" % (len(fails), len(warns)))
    if fails:
        print("结论：未通过")
        return 1
    print("结论：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
