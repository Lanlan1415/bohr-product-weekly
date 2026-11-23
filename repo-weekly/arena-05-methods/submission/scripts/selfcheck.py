#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 交付自查脚本（写作09｜方法与实验章节写作）。

对照运行契约逐项检查交付目录（如 /app/output）：
1. result.json 存在且为合法 JSON；含 case_id、status（success/partial/failed）、
   sources、uncertainty、change_log；
2. 若提供 --case：case_id 一致，且 output_contract 声明的全部原始字段出现在
   result.json 顶层（字段名一字不差）；
3. 主产物齐全：方法章节成稿（.md/.tex/.txt）、参数表（*param*）、
   来源映射（*evidence*）、result.json；
4. 六类要素齐全：成稿中按关键词组检出 步骤/实验设置/参数/数据集/对照/复现与限制；
5. 来源标记：成稿中存在 [S#] 标记，且引用的编号不大于材料登记数（若输出目录
   或工作目录可提供登记表则核对，否则仅检查标记存在）；
6. 待确认一致性：status=partial 时 result.json 的 uncertainty 非空。

v2 新增 WARN 级检查（只提醒、绝不把原本能通过的交付判 FAIL）：
7. 交付韧性：status 为 partial/failed 时建议附 skipped_reason 说明跳过阶段的原因；
8. 篇幅与覆盖：成稿全文过短（<300 字符）或某要素仅零星提及一次时提示补写或标注；
9. 参数表 v2 列：参数表缺少"被覆盖值"/"所属阶段"列时提示升级（不强制）。

用法：
    python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output [--case /input/case.json] [--register /app/work/materials_register.md]

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

# 六类要素关键词组（中英双语，命中任一即算该类出现）
ELEMENTS = {
    "步骤": r"步骤|流程|procedure|protocol|steps",
    "实验设置": r"实验设置|设置|硬件|软件版本|环境|setup|implementation|environment",
    "参数": r"参数|超参数|parameter|hyperparameter",
    "数据集与划分": r"数据集|划分|预处理|dataset|split|preprocess",
    "对照": r"对照|基线|baseline|对比|ablation|消融",
    "复现与限制": r"复现|reproducib|replicat|限制|局限|limitation",
}


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


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="方法与实验章节交付结构自查")
    parser.add_argument("--output", required=True, help="交付目录（如 /app/output）")
    parser.add_argument("--case", default=None, help="case.json 路径（可选）")
    parser.add_argument("--register", default=None,
                        help="材料登记表路径（可选，用于核对 [S#] 编号上界）")
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
        check(str(result.get("status") or "") in STATUS_OK,
              "status 属于 success/partial/failed（实际：%r）" % result.get("status"))
        for key in ("sources", "uncertainty", "change_log"):
            check(key in result, "result.json 含字段 '%s'" % key)
        if result.get("status") == "partial":
            unc = result.get("uncertainty")
            check(bool(unc), "status=partial 时 uncertainty 非空（说明哪里不完整）")
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
        results.append(("PASS", "未提供 --case，跳过契约对齐检查（正式交付前必须补做）"))

    # ---- 主产物 ----
    drafts = [p for p in glob.glob(os.path.join(out_dir, "*.md"))
              + glob.glob(os.path.join(out_dir, "*.tex"))
              + glob.glob(os.path.join(out_dir, "*.txt"))
              if not re.search(r"(evidence|param|result|readme)", os.path.basename(p), re.I)]
    check(bool(drafts), "方法章节成稿存在（.md/.tex/.txt）")
    check(bool(glob.glob(os.path.join(out_dir, "*param*"))),
          "参数表存在（*param*）")
    check(bool(glob.glob(os.path.join(out_dir, "*evidence*"))),
          "来源映射存在（*evidence*）")

    # ---- 六类要素 ----
    draft_text = ""
    for p in drafts:
        try:
            draft_text += read_text(p) + "\n"
        except OSError:
            pass
    if draft_text:
        for name, pat in ELEMENTS.items():
            check(bool(re.search(pat, draft_text, re.IGNORECASE)),
                  "六类要素之「%s」在成稿中可检出" % name)
        # v2 WARN：篇幅与覆盖核对（只提醒，不判 FAIL）
        warn(len(draft_text.strip()) >= 300,
             "成稿全文篇幅 %d 字符 ≥ 300（过短可能要素单薄，人工复核）"
             % len(draft_text.strip()))
        for name, pat in ELEMENTS.items():
            hits = len(re.findall(pat, draft_text, re.IGNORECASE))
            if 0 < hits <= 1:
                warn(False,
                     "要素「%s」仅零星提及 %d 次，可能只是一句话带过（WARN，不阻断）"
                     % (name, hits))
    else:
        check(False, "成稿可读以做要素检查")

    # ---- 来源标记 ----
    marks = re.findall(r"\[S(\d+)\]", draft_text)
    check(bool(marks), "成稿中存在来源标记 [S#]")
    if marks and args.register:
        try:
            reg = read_text(os.path.abspath(args.register))
            n_reg = len(re.findall(r"\|\s*S\d+\s*\|", reg))
            if n_reg:
                over = sorted({int(m) for m in marks if int(m) > n_reg})
                check(not over,
                      "[S#] 编号不超过登记表材料数 %d（越界：%s）"
                      % (n_reg, over if over else "无"))
        except OSError as exc:
            check(False, "登记表可读（%s）" % exc)

    # ---- v2 WARN 级：交付韧性与参数表列 ----
    if isinstance(result, dict):
        status = str(result.get("status") or "")
        if status in ("partial", "failed"):
            warn(bool(result.get("skipped_reason")),
                 "status=%s 时附 skipped_reason 说明跳过/未完成阶段的原因（交付韧性，WARN）"
                 % status)
    for p in glob.glob(os.path.join(out_dir, "*param*")):
        try:
            ptext = read_text(p)
        except OSError:
            continue
        if os.path.basename(p).lower().endswith((".md", ".txt")):
            warn("被覆盖值" in ptext,
                 "参数表 %s 含「被覆盖值」列（v2 模板，WARN 不强制）"
                 % os.path.basename(p))
            warn("阶段" in ptext or "运行" in ptext,
                 "参数表 %s 含「所属阶段/运行」列（阶段级出处，WARN 不强制）"
                 % os.path.basename(p))
            break

    # ---- 汇总 ----
    print("=" * 60)
    print("交付自查（方法与实验章节写作）")
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
