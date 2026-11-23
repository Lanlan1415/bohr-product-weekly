#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 交付自查脚本（写作13｜LaTeX 写作与编译）。

对照运行契约逐项检查交付目录（如 /app/output）：
1. result.json 存在且为合法 JSON；含 case_id、status（success/partial/failed）、
   sources、uncertainty、change_log；
2. 若提供 --case：case_id 一致，且 output_contract 声明的全部原始字段出现在
   result.json 顶层（字段名一字不差）；
3. 主产物齐全：.tex 源码存在；编译记录（*build*record*）存在；
4. 编译诚实性：若存在 PDF → 通过；若不存在 PDF → 必须 status ∈ {partial, failed}
   且保留 .log 或 PDF_FAILED 说明（防止"谎称编译成功"）；
5. 来源映射（*evidence*）存在且含材料登记；
6. status=partial 时 uncertainty 非空。

v2 新增 WARN 级检查（只提醒、绝不把原本能通过的交付判 FAIL）：
7. 交付韧性：status 为 partial/failed 时建议附 skipped_reason 说明跳过阶段的原因；
8. 编译记录含引擎/编译器信息（pdflatex/xelatex/lualatex/latexmk 之一），
   便于复核"编译器选择顺序：题目/模板指定 > 工程现有配置 > 启发式默认"。

用法：
    python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output [--case /input/case.json]

退出码：0 = 全部通过；1 = 存在 FAIL 项。stdlib-only，utf-8-sig 读文件，
只读输入与输出目录，不依赖 CWD。
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
                for k in ("name", "field", "key", "id"):
                    if k in item:
                        out.append(str(item[k]))
                        break
        return out
    return []


def rglob(base, pattern):
    return glob.glob(os.path.join(base, "**", pattern), recursive=True)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="LaTeX 交付结构自查")
    parser.add_argument("--output", required=True, help="交付目录（如 /app/output）")
    parser.add_argument("--case", default=None, help="case.json 路径（可选）")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.output)
    results = []  # (level, msg)，level ∈ {PASS, WARN, FAIL}

    def check(ok, msg):
        """FAIL 级检查：不通过影响退出码。"""
        results.append(("PASS" if ok else "FAIL", msg))

    def warn(ok, msg):
        """WARN 级检查：只提醒，不影响退出码（v2 新增项一律走这里）。"""
        results.append(("PASS" if ok else "WARN", msg))

    check(os.path.isdir(out_dir), "输出目录存在：%s" % out_dir.replace(os.sep, "/"))

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
        status = str(result.get("status") or "")
        check(status in STATUS_OK,
              "status 属于 success/partial/failed（实际：%r）" % result.get("status"))
        for key in ("sources", "uncertainty", "change_log"):
            check(key in result, "result.json 含字段 '%s'" % key)
        if status == "partial":
            check(bool(result.get("uncertainty")),
                  "status=partial 时 uncertainty 非空（说明哪里不完整）")
    else:
        status = ""
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
        results.append(("PASS", "未提供 --case，跳过契约对齐检查（正式交付前必须补做）"))

    # ---- 主产物 ----
    tex_files = rglob(out_dir, "*.tex")
    check(bool(tex_files), "LaTeX 源码存在（*.tex）")
    main_tex = None
    for p in tex_files:
        try:
            with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                if re.search(r"\\documentclass", f.read()):
                    main_tex = p
                    break
        except OSError:
            continue
    check(main_tex is not None, "存在含 \\documentclass 的主文件：%s"
          % (os.path.relpath(main_tex, out_dir).replace(os.sep, "/") if main_tex else "未找到"))

    check(bool(rglob(out_dir, "*build*record*")) or bool(rglob(out_dir, "*build_record*")),
          "编译记录存在（build_record.md）")
    check(bool(rglob(out_dir, "*evidence*")), "来源映射存在（*evidence*）")

    # ---- 编译诚实性 ----
    pdfs = rglob(out_dir, "*.pdf")
    logs = rglob(out_dir, "*.log")
    failed_notes = [p for p in rglob(out_dir, "*PDF*FAILED*")] + \
                   [p for p in rglob(out_dir, "*fail*") if p.lower().endswith(".md")]
    if pdfs:
        check(True, "PDF 产物存在（%d 个）" % len(pdfs))
    else:
        check(bool(logs) or bool(failed_notes),
              "无 PDF 时必须保留编译日志(.log)或 PDF_FAILED 说明")
        check(status in ("partial", "failed"),
              "无 PDF 时 status 必须为 partial/failed（实际：%r）——禁止谎称编译成功"
              % (status or None))

    # ---- v2 WARN 级：交付韧性与编译器留痕 ----
    if isinstance(result, dict):
        if status in ("partial", "failed"):
            warn(bool(result.get("skipped_reason")),
                 "status=%s 时附 skipped_reason 说明跳过/未完成阶段的原因（交付韧性，WARN）"
                 % status)
    for p in rglob(out_dir, "*build*record*") + rglob(out_dir, "*build_record*"):
        if not p.lower().endswith((".md", ".txt")):
            continue
        try:
            with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                btext = f.read()
        except OSError:
            continue
        warn(bool(re.search(r"pdflatex|xelatex|lualatex|latexmk|bibtex|biber",
                            btext, re.IGNORECASE)),
             "编译记录 %s 写明所用引擎/编译链（便于复核编译器选择顺序，WARN）"
             % os.path.basename(p))
        break

    return _summarize(results)


def _summarize(results):
    print("=" * 60)
    print("交付自查（LaTeX 写作与编译）")
    print("=" * 60)
    fails = 0
    warns = 0
    for level, msg in results:
        print("[%s] %s" % (level, msg))
        if level == "FAIL":
            fails += 1
        elif level == "WARN":
            warns += 1
    print("-" * 60)
    print("结果：%s（FAIL %d / WARN %d / 共 %d 项）—— WARN 只提醒，不影响退出码"
          % ("未通过" if fails else "通过", fails, warns, len(results)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
