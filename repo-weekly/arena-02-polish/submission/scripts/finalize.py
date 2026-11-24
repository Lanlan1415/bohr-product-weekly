#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py —— 五脚本流水线的第 3 环：无条件导出可交付物。

铁律：**finalize 永远导出可交付物**。任一上游阶段失败/缺失时，交付已完成
的诚实部分（最差情况 = 原文快照 + skipped_reason），绝不空手而归。

阶段与宽容路径：
1. 读 contract_fields.json（prepare 产出）或退回直接读 case.json；
2. 润色稿来源：polished_verified.md 存在 → 用之；
   否则 original_snapshot.md 存在 → 交付原文并记 skipped_reason
   （"verify 未运行或无产出"）；两者皆无 → 只交付 result.json，
   status=failed + skipped_reason；
3. change_log.md / evidence_map.md：/app/work 有则复制；没有则按
   verify_result.json 生成最小 change_log 并标注"自动生成"；
4. **契约前置校验**：组装 result.json 后、写盘前，逐字段核对 case_id 与
   output_contract 全部字段；缺失字段补 null 并写入 uncertainty（不删字段）；
5. 评审友好的 before_after_digest：接受/回退计数 + 前 8 条改前→改后样例；
6. 改后回读通道：写完 polished_text.md 后重新读回，校验哈希一致 +
   数字 token 计数与源文件一致，结果记入 quality_gate.readback；
7. 写 _manifest.json（全部交付物 sha256），供 audit.py 做事后篡改检测。

用法：
    python3 /skills/weekly-skill/scripts/finalize.py \
        --workdir /app/work --output /app/output [--case /input/case.json]

退出码：0 = 已导出（含 partial/failed 的诚实交付）；1 = 连 result.json
都无法写盘。stdlib-only；utf-8-sig；不依赖 CWD；不联网。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter

RE_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?:\s*[eE][+-]?\d+)?%?")
DIGEST_SAMPLES = 8


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


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


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="无条件导出交付物（含诚实 partial + skipped_reason）")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", default=None)
    parser.add_argument("--polished-name", default="polished_text.md")
    args = parser.parse_args(argv)

    workdir, outdir = os.path.abspath(args.workdir), os.path.abspath(args.output)
    os.makedirs(outdir, exist_ok=True)
    change_log, uncertainty, skipped = [], [], []
    case_values = {}

    # ---- 1. 契约 ----
    case_id, fields = "", []
    cf_path = os.path.join(workdir, "contract_fields.json")
    if os.path.isfile(cf_path):
        try:
            cf = json.loads(read_text(cf_path))
            case_id, fields = str(cf.get("case_id") or ""), list(cf.get("fields") or [])
        except json.JSONDecodeError:
            skipped.append("contract_fields.json 损坏，改从 case.json 直读")
    if not fields and args.case and os.path.isfile(os.path.abspath(args.case)):
        try:
            case = json.loads(read_text(os.path.abspath(args.case)))
            case_id = case_id or str(case.get("case_id") or "")
            fields = contract_fields(case.get("output_contract"))
        except (json.JSONDecodeError, OSError) as exc:
            skipped.append("case.json 直读失败：%s" % exc)
    if args.case and os.path.isfile(os.path.abspath(args.case)):
        try:
            loaded_case = json.loads(read_text(os.path.abspath(args.case)))
            if isinstance(loaded_case, dict):
                case_values = loaded_case
        except (json.JSONDecodeError, OSError):
            pass  # the earlier contract reader already recorded the degradation
    if not case_id:
        uncertainty.append("case_id 缺失 → 契约对齐无法确认 → 请人工核对 /input/case.json")
    change_log.append("[finalize] 契约字段 %d 个：%s"
                      % (len(fields), ", ".join(fields) if fields else "（未知）"))

    # ---- 2. 润色稿来源（宽容路径）----
    verified = os.path.join(workdir, "polished_verified.md")
    snapshot = os.path.join(workdir, "original_snapshot.md")
    polished_src, polished_text = None, None
    if os.path.isfile(verified):
        polished_src, polished_text = verified, read_text(verified)
    elif os.path.isfile(snapshot):
        polished_src, polished_text = snapshot, read_text(snapshot)
        skipped.append("verify 未运行或无产出 → 交付原文快照（未润色）")
    else:
        skipped.append("prepare/verify 均无产出 → 无润色稿可交付")

    # ---- verify 结果摘要 ----
    digest = {"accepted": 0, "unchanged": 0, "confirmations": 0,
              "rejected": 0, "rejected_reasons": {}, "samples": [],
              "unchanged_samples": [], "confirmation_items": []}
    vr_path = os.path.join(workdir, "verify_result.json")
    if os.path.isfile(vr_path):
        try:
            vr = json.loads(read_text(vr_path))
            digest["accepted"] = len(vr.get("accepted") or [])
            digest["unchanged"] = len(vr.get("unchanged") or [])
            digest["confirmations"] = len(vr.get("confirmations") or [])
            digest["rejected"] = len(vr.get("rejected") or [])
            for r in vr.get("rejected") or []:
                key = str(r.get("reason", "")).split("：")[0]
                digest["rejected_reasons"][key] = \
                    digest["rejected_reasons"].get(key, 0) + 1
            for a in (vr.get("accepted") or [])[:DIGEST_SAMPLES]:
                digest["samples"].append({"edit_id": a.get("edit_id"),
                                          "sentence_id": a.get("sentence_id"),
                                          "before": a.get("before"),
                                          "after": a.get("after"),
                                          "type": a.get("type"),
                                          "reason": a.get("reason"),
                                          "ambiguity": a.get("ambiguity"),
                                          "author_confirmation": a.get("author_confirmation"),
                                          "protected_elements": a.get("protected_elements")})
            digest["unchanged_samples"] = (vr.get("unchanged") or [])[:DIGEST_SAMPLES]
            digest["confirmation_items"] = vr.get("confirmations") or []
            if digest["confirmations"]:
                uncertainty.append(
                    "%d 条歧义/备选尚未由作者确认 → 对应原文未改 → 见 before_after_digest.confirmation_items"
                    % digest["confirmations"])
            if digest["rejected"]:
                uncertainty.append(
                    "%d 条编辑被守恒门回退（见 rejected_edits.jsonl）→ "
                    "对应句保持原文 → 可修正后重跑 verify+finalize"
                    % digest["rejected"])
        except json.JSONDecodeError:
            skipped.append("verify_result.json 损坏，摘要不可用")

    # ---- 3. 交付文件 ----
    delivered = []
    if polished_text is not None:
        p_out = os.path.join(outdir, args.polished_name)
        write_text(p_out, polished_text)
        delivered.append(p_out)

    for name in ("change_log.md", "evidence_map.md"):
        src = os.path.join(workdir, name)
        dst = os.path.join(outdir, name)
        if os.path.isfile(src):
            shutil.copyfile(src, dst)
            delivered.append(dst)
    if not os.path.isfile(os.path.join(outdir, "change_log.md")):
        lines = ["# 修改记录（change_log，finalize 自动生成的最小版）", "",
                 "- 说明：/app/work 未提供 Agent 维护的 change_log.md，"
                 "本文件由 finalize.py 依据 verify_result.json 生成，"
                 "逐条六要素记录请以正式 change_log 为准。", "",
                 "## 接受的编辑（前 %d 条示例）" % DIGEST_SAMPLES, ""]
        lines.append("- 接受编辑 %d 条；保持原文 %d 条；待作者确认 %d 条；回退 %d 条。"
                     % (digest["accepted"], digest["unchanged"],
                        digest["confirmations"], digest["rejected"]))
        for s in digest["samples"]:
            lines.append("- %s | 原文：%s | 改后：%s | 类型：%s | 理由：%s | 歧义：%s | 作者确认：%s"
                         % (s["edit_id"], s["before"], s["after"], s.get("type"),
                            s.get("reason"), s.get("ambiguity"), s.get("author_confirmation")))
        lines += ["", "## 保持原文（不计为润色修改）", ""]
        for s in digest["unchanged_samples"]:
            lines.append("- %s | 原文/改后：%s | 理由：%s"
                         % (s.get("edit_id"), s.get("before"), s.get("reason")))
        lines += ["", "## 待作者确认（候选未落稿）", ""]
        for s in digest["confirmation_items"]:
            lines.append("- %s | 歧义：%s | 候选：%s | 当前：保留原文"
                         % (s.get("edit_id"), s.get("ambiguity"), s.get("candidates")))
        lines += ["", "## 被回退的编辑（守恒门拦截，句子保持原文）", ""]
        vr_path2 = os.path.join(workdir, "verify_result.json")
        if os.path.isfile(vr_path2):
            try:
                vr2 = json.loads(read_text(vr_path2))
                for r in vr2.get("rejected") or []:
                    lines.append("- %s | 回退 | %s" % (r.get("edit_id"),
                                                       r.get("reason")))
            except json.JSONDecodeError:
                pass
        write_text(os.path.join(outdir, "change_log.md"), "\n".join(lines) + "\n")
        skipped.append("Agent 版 change_log.md 缺失 → 已生成最小版")
    if not os.path.isfile(os.path.join(outdir, "evidence_map.md")):
        em = ["# evidence_map.md（finalize 自动生成的最小版）", "",
              "- 说明：/app/work 未提供 Agent 维护的 evidence_map.md；"
              "本文件仅登记已知来源，事实守恒映射请补全。"
              "模板见 /skills/weekly-skill/templates/evidence_map_template.md。", "",
              "## 材料登记表", ""]
        reg = os.path.join(workdir, "materials_register.md")
        if os.path.isfile(reg):
            em.append(read_text(reg).strip())
        else:
            em.append("| 来源编号 | 文件 | 备注 |")
            em.append("|---|---|---|")
            em.append("| S1 | （待登记：待润色稿，见 original_snapshot.md）"
                      " | 未运行 inventory.py |")
        em += ["", "## 事实守恒映射", "",
               "- 守恒门结果：见 verify_report.md / audit_report.md；"
               "数字、引用、图表编号、公式以 conservation_check 复核为准。", ""]
        write_text(os.path.join(outdir, "evidence_map.md"), "\n".join(em) + "\n")
        skipped.append("Agent 版 evidence_map.md 缺失 → 已生成最小版")
    # 无论新生成还是沿用，change_log.md / evidence_map.md 都纳入 manifest
    for name in ("change_log.md", "evidence_map.md"):
        p = os.path.join(outdir, name)
        if os.path.isfile(p) and p not in delivered:
            delivered.append(p)

    # ---- 4. 组装 result.json + 契约前置校验 ----
    status = "success"
    if polished_text is None:
        status = "failed"
    elif skipped or digest["rejected"] or digest["confirmations"]:
        status = "partial"
    result = {
        "case_id": case_id,
        "status": status,
        "sources": [],
        "uncertainty": uncertainty,
        "change_log": change_log,
        "before_after_digest": digest,
        "quality_gate": {},
        "output_contract_fields": fields,
    }
    if skipped:
        result["skipped_reason"] = skipped
    # 常见契约字段的自动填充（仅在字段语义明确时）
    auto = {"polished_text": args.polished_name if polished_text is not None else None,
            "change_log": "change_log.md"}
    pre_check = []
    for f in fields:
        if f in result and result[f] not in (None, ""):
            pre_check.append((f, True, "已填"))
        elif f in case_values and f not in ("case_id", "output_contract") and \
                case_values[f] is not None and \
                (not isinstance(case_values[f], str) or case_values[f].strip()):
            result[f] = case_values[f]
            pre_check.append((f, True, "case 同名字段逐字直通"))
        elif f in auto:
            result[f] = auto[f]
            pre_check.append((f, True, "自动填充"))
        else:
            result[f] = None
            result["uncertainty"].append(
                "契约字段 %r 无法自动产出 → 置 null → 请人工补填或确认语义" % f)
            pre_check.append((f, False, "置 null + uncertainty"))
    print("[契约前置校验] case_id=%r；字段 %d 个：" % (case_id, len(fields)))
    for f, ok, how in pre_check:
        print("  [%s] %s（%s）" % ("OK" if ok else "NULL", f, how))

    # ---- 5/6. 写盘 + 改后回读 ----
    if polished_text is not None:
        p_out = os.path.join(outdir, args.polished_name)
        try:
            back = read_text(p_out)
            same_hash = hashlib.sha256(back.encode("utf-8")).hexdigest() == \
                hashlib.sha256(polished_text.encode("utf-8")).hexdigest()
            same_nums = Counter(RE_NUMBER.findall(back)) == \
                Counter(RE_NUMBER.findall(polished_text))
            ok = same_hash and same_nums
            result["quality_gate"]["readback"] = "pass" if ok else "fail"
            if not ok:
                result["uncertainty"].append(
                    "改后回读不一致 → 交付文件可能被外部改动 → 建议重跑 finalize")
        except OSError as exc:
            result["quality_gate"]["readback"] = "fail: %s" % exc

    rj = os.path.join(outdir, "result.json")
    try:
        write_text(rj, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        print("[FAIL] result.json 无法写盘：%s" % exc)
        return 1
    delivered.append(rj)

    # ---- 7. manifest（审计与篡改检测基线）----
    manifest = {os.path.relpath(p, outdir): sha256(p) for p in delivered
                if os.path.isfile(p)}
    write_text(os.path.join(outdir, "_manifest.json"),
               json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    print("[OK] finalize 导出完成：status=%s；交付 %d 个文件；skipped %d 项"
          % (status, len(delivered), len(skipped)))
    for s in skipped:
        print("[SKIP] %s" % s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
