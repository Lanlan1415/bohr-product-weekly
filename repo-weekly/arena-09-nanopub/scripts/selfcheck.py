# -*- coding: utf-8 -*-
"""selfcheck.py — 交付自查（阅读14：Nanopublication）

对 /app/output（或参数指定目录）做交付前确定性检查：
  1. 主产物存在：至少一个 .trig/.ttl 文件且非空（--main 可指定文件名）。
  2. result.json 存在、是合法 JSON、含 case_id、status ∈ {success, partial, failed}，
     且含 sources / uncertainty / change_log 三个诚实性字段。
  3. 若提供 case.json：result.json 必须包含 output_contract 声明的全部原始字段
     （字段名以 case.json 为准，不臆造）。
  4. nanopub 文件的最低结构痕迹：含 hasAssertion / hasProvenance /
     hasPublicationInfo 字样与 @prefix 声明（完整语法校验请用 nanopub_check.py）。
  5. result.json 中 status=success 时不应出现未填占位符（TODO/待补）。
  6. （v2，仅 WARN）status=partial/failed 时建议提供 skipped_reason 字段
     （交付韧性；不误判 v1 草稿）。

用法：
    python selfcheck.py --out <output_dir> [--case <case.json>] [--main xx.trig]

退出码：0 通过；1 未通过；2 参数错误。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
仅使用 Python 标准库；读文件一律 utf-8-sig；只读被检查目录；
不依赖当前工作目录（CWD）。
"""
import argparse
import json
import os
import re
import sys

ALLOWED_STATUS = {"success", "partial", "failed"}
NP_MARKERS = ["hasAssertion", "hasProvenance", "hasPublicationInfo"]


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


def find_rdf_files(out_dir, main_name=None):
    hits = []
    if main_name:
        p = os.path.join(out_dir, main_name)
        if os.path.isfile(p):
            hits.append(p)
        return hits
    for name in sorted(os.listdir(out_dir)):
        if name.lower().endswith((".trig", ".ttl")):
            hits.append(os.path.join(out_dir, name))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付自查（阅读14 Nanopublication）")
    ap.add_argument("--out", required=True, help="输出目录绝对路径（如 /app/output）")
    ap.add_argument("--case", default=None, help="/input/case.json 绝对路径")
    ap.add_argument("--main", default=None,
                    help="主产物文件名（默认自动查找 *.trig/*.ttl）")
    args = ap.parse_args(argv)

    fails, warns = [], []
    if not os.path.isdir(args.out):
        print("[FAIL] 输出目录不存在：%s" % args.out)
        print("结论：未通过")
        return 1

    # 1. 主产物（RDF 文件）
    rdf_files = find_rdf_files(args.out, args.main)
    if not rdf_files:
        fails.append("主产物缺失：%s 下没有任何 .trig/.ttl 文件" % args.out)
    for p in rdf_files:
        if os.path.getsize(p) == 0:
            fails.append("RDF 文件为空：%s" % os.path.basename(p))
        else:
            print("[PASS] 主产物存在：%s（%d 字节）"
                  % (os.path.basename(p), os.path.getsize(p)))

    # 1b. 辅助交付
    if not os.path.isfile(os.path.join(args.out, "assertion_table.md")):
        warns.append("未发现 assertion_table.md（断言登记表，建议随交付提供）")
    if not os.path.isfile(os.path.join(args.out, "evidence_map.md")):
        fails.append("证据映射文件缺失：evidence_map.md")
    else:
        print("[PASS] 证据映射文件存在：evidence_map.md")

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

    # 4. nanopub 结构痕迹（粗检；语法级校验交给 nanopub_check.py）
    for p in rdf_files:
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            continue
        body = read_text(p)
        if p.lower().endswith(".trig"):
            missing_m = [m for m in NP_MARKERS if m not in body]
            if missing_m:
                fails.append("%s 缺少三部结构字样：%s"
                             % (os.path.basename(p), "、".join(missing_m)))
            else:
                print("[PASS] %s 含三部结构字样" % os.path.basename(p))
        if "@prefix" not in body and "PREFIX" not in body:
            fails.append("%s 没有任何前缀声明" % os.path.basename(p))

    # 5. 占位符与 status 一致性
    if isinstance(result, dict) and result.get("status") == "success":
        for p in rdf_files + [os.path.join(args.out, "assertion_table.md")]:
            if os.path.isfile(p):
                body = read_text(p)
                if re.search(r"TODO|待补|占位|PLACEHOLDER|XXX", body, re.IGNORECASE):
                    warns.append("%s 含占位符痕迹，但 status=success（应改为 partial）"
                                 % os.path.basename(p))

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
