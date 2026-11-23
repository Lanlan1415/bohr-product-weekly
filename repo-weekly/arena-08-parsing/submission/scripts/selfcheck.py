#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付自查脚本（文献文档解析技能）：对 /app/output 做逐项机器校验。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/selfcheck.py \
        --output /app/output --case /input/case.json

校验项：
  1. 输出目录存在且非空；
  2. 主产物（parsed_document.md）存在且非空；
  3. result.json 是合法 JSON，含 case_id 且与 case.json 一致；
  4. result.json 顶层包含 case.json 的 output_contract 声明的全部字段；
  5. result.json 的 status 属于 success/partial/failed；
  6. 主产物包含本题必备章节（元数据/章节/图表/公式/参考文献/置信度）；
  7. 主产物中引用的每个 [S#] 来源标记都已在证据映射表中登记；
  8. 证据映射表 evidence_map.md 存在。

v2 新增 WARN 级检查（校验器校准纪律：新检查项一律 WARN 起步，
不把原本能通过的草稿判 FAIL；观察稳定后才允许升级为 FAIL）：
  W1. status 为 partial/failed 但 uncertainty 为空 → WARN；
  W2. result.json 缺 change_log 或 sources（契约未声明时）→ WARN；
  W3. status 为 partial 但无 skipped_reason 字段且 uncertainty 无跳过/未完成说明 → WARN；
  W4. survey.json 的 ocr_pages 非空，但主产物缺"OCR 页覆盖声明" → WARN
     （对应负路径红线：跳过 OCR 页却声称覆盖）；
  W5. 主产物缺"未决事项/待确认"小节 → WARN。

打印逐条 [PASS]/[FAIL]/[WARN]，任一 FAIL 则退出码为 1，WARN 不影响退出码。
（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读取一律 utf-8-sig；不访问网络；不修改任何输入。
"""
import argparse
import json
import os
import re
import sys

MAIN_ARTIFACT = "parsed_document.md"
EVIDENCE_MAP = "evidence_map.md"
RESULT_JSON = "result.json"

# 主产物必备章节（正则），缺任一条即 FAIL
REQUIRED_SECTIONS = [
    ("元数据（标题/作者）", r"标题"),
    ("作者与单位", r"作者"),
    ("摘要", r"摘要"),
    ("章节树/章节结构", r"章节"),
    ("图表与题注", r"图|表"),
    ("公式", r"公式"),
    ("参考文献", r"参考文献"),
    ("置信度标注", r"conf:(high|medium|low)|置信度"),
]

RE_SOURCE_MARK = re.compile(r"\[S(\d+)\]")
ALLOWED_STATUS = ("success", "partial", "failed")


def read_text(path):
    """utf-8-sig 读取文本文件；失败返回 None。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def contract_fields(case_obj):
    """从 case.json 提取 output_contract 声明的字段名列表（兼容 dict/list/str）。"""
    if not isinstance(case_obj, dict):
        return []
    oc = case_obj.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(x) for x in oc]
    if isinstance(oc, str):
        return [oc]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description="交付自查（文献文档解析技能）")
    parser.add_argument("--output", required=True, help="交付目录绝对路径，例如 /app/output")
    parser.add_argument("--case", default=None,
                        help="case.json 绝对路径，例如 /input/case.json（可选但强烈建议）")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.output)
    results = []  # (级别 PASS/FAIL/WARN, 名称, 细节)

    def check(ok, name, detail=""):
        results.append(("PASS" if ok else "FAIL", name, detail))

    def warn(name, detail=""):
        results.append(("WARN", name, detail))

    # 1. 输出目录
    if not os.path.isdir(out_dir):
        print("[FAIL] 输出目录不存在：%s" % out_dir)
        return 1
    names = os.listdir(out_dir)
    check(len(names) > 0, "输出目录非空", "%d 个条目" % len(names))

    # 2. 主产物
    main_path = os.path.join(out_dir, MAIN_ARTIFACT)
    main_text = read_text(main_path)
    check(main_text is not None and main_text.strip(), "主产物存在且非空", MAIN_ARTIFACT)

    # 3-5. result.json
    rj_path = os.path.join(out_dir, RESULT_JSON)
    rj_text = read_text(rj_path)
    rj = None
    if rj_text is None:
        check(False, "result.json 存在且可读", rj_path)
    else:
        try:
            rj = json.loads(rj_text)
            check(True, "result.json 是合法 JSON", "")
        except json.JSONDecodeError as exc:
            check(False, "result.json 是合法 JSON", str(exc))

    case_obj = None
    if args.case:
        case_text = read_text(os.path.abspath(args.case))
        if case_text is not None:
            try:
                case_obj = json.loads(case_text)
            except json.JSONDecodeError:
                case_obj = None

    if isinstance(rj, dict):
        check(bool(rj.get("case_id")), "result.json 含 case_id", str(rj.get("case_id")))
        if isinstance(case_obj, dict) and case_obj.get("case_id"):
            check(rj.get("case_id") == case_obj.get("case_id"),
                  "case_id 与 case.json 一致",
                  "result=%s case=%s" % (rj.get("case_id"), case_obj.get("case_id")))
        check(rj.get("status") in ALLOWED_STATUS,
              "status 合法（success/partial/failed）", str(rj.get("status")))
        fields = contract_fields(case_obj) if case_obj else []
        if fields:
            missing = [f for f in fields if f not in rj]
            check(not missing, "output_contract 字段齐全",
                  "缺失：%s" % ", ".join(missing) if missing else "%d 个字段齐全" % len(fields))
        else:
            check(True, "output_contract 字段齐全（case.json 未声明，跳过逐字段比对）", "")
    # 6. 必备章节
    if main_text:
        for label, pattern in REQUIRED_SECTIONS:
            check(re.search(pattern, main_text) is not None,
                  "主产物含必备章节：%s" % label, "")
    # 7-8. 来源标记与证据映射
    ev_path = os.path.join(out_dir, EVIDENCE_MAP)
    ev_text = read_text(ev_path)
    check(ev_text is not None and ev_text.strip(), "证据映射表存在", EVIDENCE_MAP)
    if main_text:
        cited = sorted(set(RE_SOURCE_MARK.findall(main_text)), key=int)
        check(len(cited) > 0, "主产物含 [S#] 来源标记", "共 %d 个" % len(cited))
        if ev_text:
            registered = set(RE_SOURCE_MARK.findall(ev_text)) | set(
                re.findall(r"\bS(\d+)\b", ev_text))
            missing = [s for s in cited if s not in registered]
            check(not missing, "引用的 [S#] 均已登记",
                  "未登记：%s" % ", ".join("S" + s for s in missing) if missing else "全部已登记")

    # ---- v2 WARN 级检查（校准纪律：只 WARN，不判 FAIL）----
    if isinstance(rj, dict):
        status = rj.get("status")
        unc = rj.get("uncertainty")
        if status in ("partial", "failed") and not unc:
            warn("W1 status 为 %s 但 uncertainty 为空" % status,
                 "partial/failed 必须逐条说明限制与未完成项")
        if "change_log" not in rj or "sources" not in rj:
            warn("W2 result.json 缺 change_log 或 sources",
                 "契约未声明时也建议保留：来源与修改记录是可核验性的基础")
        if status == "partial":
            has_skip_field = isinstance(rj.get("skipped_reason"), list) \
                and bool(rj.get("skipped_reason"))
            unc_text = " ".join(str(u) for u in unc) if isinstance(unc, list) else ""
            if not has_skip_field and not re.search(
                    r"skip|跳过|未完成|未译|中断|耗尽", unc_text):
                warn("W3 partial 但未说明跳过原因",
                     "建议用 finalize.py 固化交付并写 skipped_reason")
    survey_text = read_text(os.path.join(out_dir, "survey.json"))
    if survey_text and main_text:
        try:
            survey = json.loads(survey_text)
        except json.JSONDecodeError:
            survey = None
        if isinstance(survey, dict) and survey.get("ocr_pages"):
            ocr_pages = survey["ocr_pages"]
            if not re.search(r"OCR\s*页覆盖|OCR\s*覆盖声明|OCR\s*页清单|OCR pages",
                             main_text, re.IGNORECASE):
                warn("W4 有 OCR 页但主产物缺 OCR 页覆盖声明",
                     "survey.json 标记需 OCR 的页：p.%s；"
                     "禁止跳过 OCR 页却声称覆盖——照抄 ocr_coverage.md 的清单"
                     % ", p.".join(str(p) for p in ocr_pages[:20]))
    if main_text and not re.search(r"未决|待确认", main_text):
        warn("W5 主产物缺“未决事项/待确认”小节",
             "诚实声明未完成与存疑项是可核验性的评分点")

    n_fail = n_warn = 0
    for lv, name, detail in results:
        if lv == "FAIL":
            n_fail += 1
        elif lv == "WARN":
            n_warn += 1
        print("[%s] %s%s" % (lv, name, (" —— " + detail) if detail else ""))
    print("[selfcheck] PASS %d，WARN %d，FAIL %d（WARN 不影响退出码）"
          % (len(results) - n_fail - n_warn, n_warn, n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
