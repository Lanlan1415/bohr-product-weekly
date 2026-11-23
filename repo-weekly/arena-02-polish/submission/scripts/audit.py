#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py —— 五脚本流水线的第 4 环：交付后审计（事后篡改检测 + 复核）。

对 /app/output 做独立复核，不信任任何中间环节的"自称完成"：

1. 篡改检测：重算全部交付物 sha256，与 _manifest.json 比对——任何
   不一致即 FAIL（finalize 之后有人动过交付物）；manifest 缺失记 WARN；
2. 守恒复核：用同目录的 conservation_check.py 对 original_snapshot.md
   与导出的润色稿做整文档复检（脚本或快照缺失记 WARN 跳过，不算失败）；
3. 契约复核：result.json 的 case_id 与 output_contract 字段对齐 case.json；
4. 回退留痕：verify_result.json 中每条被回退的 edit_id 应能在
   change_log 文本中找到（找不到记 WARN：留痕是评审可读性要求）；
5. 状态诚实：status=success 但存在 skipped_reason / 回退记录 → FAIL。

用法：
    python3 /skills/weekly-skill/scripts/audit.py \
        --output /app/output [--case /input/case.json] [--workdir /app/work]

退出码：0 = 通过（可有 WARN）；1 = 存在 FAIL。
退出码 1 仅表示存在建议修复项；无论退出码如何，交付物均已落盘，应照常交付
并在 result.json 的 uncertainty 中记录未修复项——本脚本不充当交付门禁。
stdlib-only；utf-8-sig；
只读输入目录；写 audit_report.md 到 --workdir（若给）否则只打印；不依赖 CWD。
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="交付后审计：篡改检测 + 守恒/契约复核")
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", default=None)
    parser.add_argument("--workdir", default=None)
    args = parser.parse_args(argv)

    outdir = os.path.abspath(args.output)
    workdir = os.path.abspath(args.workdir) if args.workdir else None
    errors, warnings, notes = [], [], []

    # ---- 1. 篡改检测 ----
    man_path = os.path.join(outdir, "_manifest.json")
    if os.path.isfile(man_path):
        try:
            manifest = json.loads(read_text(man_path))
            for rel, want in manifest.items():
                p = os.path.join(outdir, rel)
                if not os.path.isfile(p):
                    errors.append("交付物丢失：%s（manifest 有记录）" % rel)
                elif sha256(p) != want:
                    errors.append("事后篡改：%s 的 sha256 与 manifest 不符——"
                                  "finalize 之后交付物被改动，须重跑 finalize 复核" % rel)
            notes.append("manifest 核对文件 %d 个" % len(manifest))
        except json.JSONDecodeError as exc:
            warnings.append("_manifest.json 损坏：%s" % exc)
    else:
        warnings.append("无 _manifest.json（未走 finalize.py？）：无法做事后篡改检测")

    # ---- 2. 守恒复核（进程内加载同目录 conservation_check.py，避免子进程依赖）----
    snapshot = os.path.join(workdir, "original_snapshot.md") if workdir else None
    polished = None
    for name in ("polished_text.md", "polished.md", "polished_text.txt"):
        p = os.path.join(outdir, name)
        if os.path.isfile(p):
            polished = p
            break
    gate = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "conservation_check.py")
    if snapshot and os.path.isfile(snapshot) and polished and os.path.isfile(gate):
        argv = ["--original", snapshot, "--polished", polished]
        terms = os.path.join(workdir, "terms.txt")
        if os.path.isfile(terms):
            argv += ["--terms", terms]
        try:
            spec = importlib.util.spec_from_file_location("conservation_check", gate)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            print("---- conservation_check 复核输出 ----")
            rc = mod.main(argv)
            print("---- 复核结束 ----")
            if rc != 0:
                errors.append("守恒复核 FAIL：导出稿与原文快照存在硬不一致"
                              "（见上方 conservation_check 输出）")
            else:
                notes.append("守恒复核通过（conservation_check 退出码 0）")
        except Exception as exc:  # 加载/运行异常不应中断审计
            warnings.append("守恒复核脚本运行失败：%s（请手工复跑 conservation_check）" % exc)
    else:
        warnings.append("守恒复核跳过（缺快照/润色稿/conservation_check.py）")

    # ---- 3. 契约复核 ----
    rj_path = os.path.join(outdir, "result.json")
    result = None
    if not os.path.isfile(rj_path):
        errors.append("result.json 缺失")
    else:
        try:
            result = json.loads(read_text(rj_path))
        except json.JSONDecodeError as exc:
            errors.append("result.json 不可解析：%s" % exc)
    if isinstance(result, dict) and args.case:
        try:
            case = json.loads(read_text(os.path.abspath(args.case)))
            if result.get("case_id") != case.get("case_id"):
                errors.append("case_id 与 case.json 不一致：%r ≠ %r"
                              % (result.get("case_id"), case.get("case_id")))
            missing = [f for f in contract_fields(case.get("output_contract"))
                       if f not in result]
            if missing:
                errors.append("output_contract 字段未透传：%s" % ", ".join(missing))
            else:
                notes.append("契约字段全部透传")
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append("case.json 不可读，契约复核跳过：%s" % exc)
    elif not args.case:
        warnings.append("未提供 --case，契约复核跳过")

    # ---- 4. 回退留痕 ----
    if workdir:
        vr_path = os.path.join(workdir, "verify_result.json")
        cl_path = os.path.join(outdir, "change_log.md")
        if os.path.isfile(vr_path):
            try:
                vr = json.loads(read_text(vr_path))
                rejected = vr.get("rejected") or []
                cl_text = read_text(cl_path) if os.path.isfile(cl_path) else ""
                not_logged = [r.get("edit_id") for r in rejected
                              if str(r.get("edit_id")) not in cl_text]
                if not_logged:
                    warnings.append("被回退编辑未在 change_log 留痕：%s"
                                    "（评审需要看到'拒绝了什么、为什么')"
                                    % ", ".join(map(str, not_logged)))
            except json.JSONDecodeError:
                warnings.append("verify_result.json 损坏，回退留痕核对跳过")

    # ---- 5. 状态诚实 ----
    if isinstance(result, dict):
        if result.get("status") == "success" and \
                (result.get("skipped_reason") or
                 (result.get("before_after_digest") or {}).get("rejected")):
            errors.append("status=success 但存在 skipped_reason/回退记录，"
                          "状态不诚实，应降为 partial")

    # ---- 汇总 ----
    print("=" * 60)
    print("audit：交付后审计")
    print("=" * 60)
    for n in notes:
        print("[INFO] %s" % n)
    for w in warnings:
        print("[WARN] %s" % w)
    for e in errors:
        print("[FAIL] %s" % e)
    print("结果：%s（FAIL %d，WARN %d）"
          % ("未通过" if errors else "通过", len(errors), len(warnings)))

    if workdir:
        rep = os.path.join(workdir, "audit_report.md")
        with open(rep, "w", encoding="utf-8") as f:
            f.write("# audit 审计报告\n\n## FAIL（%d）\n\n" % len(errors))
            for e in errors:
                f.write("- %s\n" % e)
            f.write("\n## WARN（%d）\n\n" % len(warnings))
            for w in warnings:
                f.write("- %s\n" % w)
            f.write("\n## INFO\n\n")
            for n in notes:
                f.write("- %s\n" % n)
        print("[OK] 报告已写入 %s" % rep)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
