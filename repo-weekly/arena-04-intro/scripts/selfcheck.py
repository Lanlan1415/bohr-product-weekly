#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 交付自查（引言与相关工作写作题，stdlib-only）。

逐条打印 PASS/FAIL，任一项 FAIL 退出码为 1：
  1. 输出目录存在且非空；
  2. result.json 合法、status 诚实、含 sources/uncertainty/change_log；
  3. case_id 与 case.json 一致，output_contract 声明的全部原始字段透传齐全；
  4. 主产物（引言/相关工作成稿）存在；
  5. 漏斗四段（背景/相关工作/空白/贡献）齐全；
  6. 相关工作对比表存在且维度 ≥3（方法/数据/结论/局限）；
  7. 正文 [S#] 全部在证据表中登记；
  8. 贡献条目数 == 缺口条目数。
（5–8 的完整版与 slogan 检测由 structure_check.py 提供，本脚本复用其逻辑。）

用法（绝对路径，不依赖 CWD，只读输入目录）：
  python3 /skills/weekly-skill/scripts/selfcheck.py \
      --output-dir /app/output --case-json /input/case.json
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import structure_check as sc  # noqa: E402  复用正则与判据，避免两处漂移

results = []


def record(ok, name, detail="", warn=False):
    level = "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL")
    results.append((level, name, detail))


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for it in oc:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict):
                for k in ("name", "field", "key"):
                    if k in it:
                        fields.append(it[k])
                        break
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付自查：契约透传 + 本题结构要素 + 来源登记。")
    ap.add_argument("--output-dir", default="/app/output", help="交付目录（默认 /app/output）")
    ap.add_argument("--case-json", default="/input/case.json", help="case.json 路径")
    args = ap.parse_args(argv)

    outdir = args.output_dir
    if not os.path.isdir(outdir):
        record(False, "输出目录存在", "目录不存在: %s" % outdir)
        return report()
    files = []
    for dp, _dn, fns in os.walk(outdir):
        for fn in fns:
            files.append(os.path.join(dp, fn))
    record(bool(files), "输出目录非空", "%d 个文件" % len(files))

    # result.json / 契约
    rj_path = os.path.join(outdir, "result.json")
    rj = None
    if not os.path.isfile(rj_path):
        record(False, "result.json 存在", rj_path)
    else:
        try:
            rj = json.loads(read_text(rj_path))
            record(True, "result.json 合法 JSON")
        except (ValueError, OSError) as e:
            record(False, "result.json 合法 JSON", str(e))
    if rj is not None:
        record(rj.get("status") in ("success", "partial", "failed"),
               "status 诚实取值", "status=%r" % (rj.get("status"),))
        for key in ("sources", "uncertainty"):
            record(key in rj, "result.json 含 %s" % key)
        record(("change_log" in rj) or ("change_records" in rj),
               "result.json 含 change_log/change_records")
        if os.path.isfile(args.case_json):
            try:
                case = json.loads(read_text(args.case_json))
                cid = case.get("case_id") or case.get("id")
                record(rj.get("case_id") == cid, "case_id 透传一致",
                       "case.json=%r result.json=%r" % (cid, rj.get("case_id")))
                missing = [f for f in contract_fields(case) if f not in rj]
                record(not missing, "output_contract 字段透传齐全",
                       "缺失: %s" % ", ".join(missing) if missing else "全部透传")
            except (ValueError, OSError) as e:
                record(False, "case.json 可解析", str(e))
        else:
            record(False, "case.json 可解析", "不存在: %s（无法核对契约字段）" % args.case_json,
                   warn=True)

    # 主产物与证据表定位
    text_files = [p for p in files if os.path.splitext(p)[1].lower() in (".md", ".txt")]
    draft, evidence = None, None
    for p in text_files:
        base = os.path.basename(p).lower()
        if ("evidence" in base or "证据" in base or "来源" in base) and p.endswith(".md"):
            evidence = evidence or p
            continue
        if any(k in base for k in ("report", "报告", "register", "登记")):
            continue
        if draft is None:
            try:
                t = read_text(p)
            except OSError:
                continue
            if sc.SECTION_PATTERNS["related"].search(t) or sc.SECTION_PATTERNS["background"].search(t):
                draft = p
    record(draft is not None, "主产物（成稿）存在", draft or "未找到含引言/相关工作标题的稿件")
    record(evidence is not None, "证据表（来源映射）存在", evidence or "未找到")

    if draft:
        try:
            d = read_text(draft)
        except OSError:
            d = ""
        # 漏斗四段
        for key, label in (("background", "研究背景/引言"), ("related", "相关工作"),
                           ("gap", "研究空白/缺口"), ("contrib", "贡献")):
            record(bool(sc.SECTION_PATTERNS[key].search(d)), "漏斗段落：%s" % label)
        # 对比表维度
        tables = re.findall(r"((?:^\|.*\|\s*$\n?){2,})", d, re.M)
        dim_hit = False
        for tb in tables:
            header = tb.splitlines()[0]
            if sum(1 for pat in sc.TABLE_DIMS.values() if pat.search(header)) >= 3:
                dim_hit = True
                break
        record(bool(tables), "相关工作对比表存在",
               "" if tables else "未找到 markdown 表格")
        if tables:
            record(dim_hit, "对比表维度 ≥3（方法/数据/结论/局限）")
        # [S#] 登记
        used = {int(m.group(1)) for m in sc.SMARK.finditer(d)}
        registered = set()
        if evidence:
            try:
                registered = {int(m.group(1)) for m in sc.SREG.finditer(read_text(evidence))}
            except OSError:
                pass
        record(bool(used), "正文使用 [S#] 来源标记", "共 %d 个" % len(used) if used else "未使用")
        if evidence and used:
            ghosts = sorted(used - registered)
            record(not ghosts, "无幽灵来源标记",
                   "未登记: %s" % ", ".join("S%d" % g for g in ghosts) if ghosts else "均已登记")
        # 贡献-缺口对应
        gs, cs = sc.section_span(d, "gap"), sc.section_span(d, "contrib")
        if gs and cs:
            n_g, n_c = sc.count_list_items(d[gs[0]:gs[1]]), sc.count_list_items(d[cs[0]:cs[1]])
            record(n_g > 0 and n_g == n_c, "贡献-缺口一一对应",
                   "缺口 %d 条 vs 贡献 %d 条" % (n_g, n_c))
        # --- v2 新增检查项（只 WARN，不把原本能通过的草稿判 FAIL） ---
        record(not sc.INCOMPLETE.search(d), "行文完成度：无 TODO/占位标记（v2，WARN）",
               "检出未完成标记——交付前须替换为成稿文字", warn=True)
        cmp_bad = None
        for sec_key in ("gap", "contrib"):
            sp = sc.section_span(d, sec_key)
            if not sp:
                continue
            for line in d[sp[0]:sp[1]].splitlines():
                if sc.CMP_CLAIM.search(line) and not sc.NUM_VAL.search(line):
                    cmp_bad = line.strip()[:40]
                    break
            if cmp_bad:
                break
        record(cmp_bad is None, "相邻结果边界：比较断言含数值（v2，WARN）",
               ("「%s」缺数值区间——按 method_rules §5.1 补最相近工作结果对比" % cmp_bad)
               if cmp_bad else "", warn=True)
    return report()


def report():
    n_fail = 0
    for level, name, detail in results:
        if level == "FAIL":
            n_fail += 1
        print("[%s] %s%s" % (level, name, (" — " + detail) if detail else ""))
    print("自查结论: %s（FAIL %d 项）" % ("FAIL" if n_fail else "PASS", n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
