#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付自查脚本（写作02｜学术语言润色）。

对照运行契约逐项检查 /app/output：
1. result.json 存在且为合法 JSON；
2. result.json 含 case_id、status（success/partial/failed）、sources、
   uncertainty、change_log 字段；
3. 若提供 --case：case_id 一致，且 output_contract 全部原始字段透传；
4. 主产物齐全：润色稿（*.md/*.txt，result.json 之外）、修改记录
   （change_log.md 或含逐条修改记录的文件）、result.json；
5. 修改记录可回溯：修改记录中至少存在 3 条带编号条目（如 C001/E01/#1），
   且同时含"原文/原句"与"改后/润色"对照字样；
6. 来源映射存在：输出文件中存在 [S#] 标记或 evidence_map 文件。

v2 新增（只 WARN、不判 FAIL——原本能通过的草稿不会被新检查打回）：
- result.json 含 before_after_digest（finalize.py 的评审友好摘要）；
- status 非 success 时有 skipped_reason/uncertainty 说明；
- 存在 _manifest.json（finalize.py 的审计与篡改检测基线）。

用法：
    python selfcheck.py --output /app/output [--case /input/case.json]

退出码：0 = 通过（可有 WARN）；1 = 存在 FAIL 项。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
stdlib-only，utf-8-sig 读文件，只读目录，不依赖 CWD。
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


def read_all(paths):
    buf = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                buf.append(f.read())
        except OSError:
            pass
    return "\n".join(buf)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="润色交付物结构自查")
    parser.add_argument("--output", required=True, help="交付目录（如 /app/output）")
    parser.add_argument("--case", default=None, help="case.json 路径（可选）")
    args = parser.parse_args()

    out_dir = os.path.abspath(args.output)
    results = []

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

    # ---- 契约对齐 ----
    if args.case:
        try:
            case = read_json(os.path.abspath(args.case))
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
    md_files = [p for p in glob.glob(os.path.join(out_dir, "*.md"))]
    txt_files = [p for p in glob.glob(os.path.join(out_dir, "*.txt"))]
    polished = [p for p in md_files + txt_files
                if os.path.basename(p) not in ("evidence_map.md", "change_log.md")]
    check(bool(polished), "润色稿存在（.md/.txt）")

    cl_candidates = [p for p in md_files
                     if "change" in os.path.basename(p).lower()
                     or "log" in os.path.basename(p).lower()]
    cl_text = read_all(cl_candidates) if cl_candidates else ""
    if not cl_text:
        cl_text = read_all(md_files)  # 退而在全部 md 里找修改记录
    check(bool(cl_candidates) or "修改" in cl_text,
          "修改记录文件存在（change_log.md 或同等文件）")

    # ---- 修改条目可回溯 ----
    entries = re.findall(r"(?m)^\s*(?:[-*]\s*)?(?:C\d{3}|E\d{2,3}|#\d+|修改\s*\d+)",
                         cl_text)
    check(len(entries) >= 3,
          "修改记录含 ≥3 条带编号条目（实际 %d 条）" % len(entries))
    has_pair = (re.search(r"原[文句]|修改前|before", cl_text, re.IGNORECASE)
                and re.search(r"改[后文]|润色后|after", cl_text, re.IGNORECASE))
    check(bool(has_pair), "修改记录含改前/改后对照")

    # ---- 来源映射 ----
    all_text = read_all(md_files + txt_files + [rj_path])
    check(bool(re.search(r"\[S\d+\]", all_text))
          or any("evidence" in os.path.basename(p).lower() for p in md_files),
          "存在来源映射（[S#] 标记或 evidence_map 文件）")

    # ---- v2 新增检查（只 WARN，不判 FAIL：不影响原本能通过的草稿）----
    warns = []
    if isinstance(result, dict):
        if "before_after_digest" not in result:
            warns.append("result.json 缺少 before_after_digest"
                         "（finalize.py 生成的评审友好摘要；v1 流程可忽略）")
        if result.get("status") != "success" and not (
                result.get("skipped_reason") or result.get("uncertainty")):
            warns.append("status 非 success 但无 skipped_reason/uncertainty 说明原因")
    if not os.path.isfile(os.path.join(out_dir, "_manifest.json")):
        warns.append("无 _manifest.json（finalize.py 的审计基线）："
                     "无法用 audit.py 做事后篡改检测")

    # ---- 汇总 ----
    print("=" * 60)
    print("交付自查（学术语言润色）")
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
