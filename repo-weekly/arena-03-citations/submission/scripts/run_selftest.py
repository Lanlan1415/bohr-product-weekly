#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_selftest.py — 本技能脚本的负路径自测（stdlib-only，全合成 fixture）。

在临时目录生成合成 fixture（正例 + 必须被拒绝的负例），逐个调用本技能脚本，
断言退出码符合预期：
  正例（期望退出码 0）：合规稿件、合规映射表、合规文献表、合规 result 草稿；
  负例（期望退出码 1，**必须被拒绝**）：
    N1 引而无目（正文引用 [9] 但文献表无此条目）；
    N2 条目缺年份（GB/T lint ERROR）；
    N3 幽灵来源（正文 [S9] 未在来源映射登记）；
    N4 契约字段缺失（result.json 少 output_contract 字段）；
    N5 同 DOI 重复条目（去重必须报候选）；
    N6 编号映射碰撞（两个保留条目共用新编号）；
    N7 源头缺字段 + --strict（往返检查必须判 LOSS）。

用法（绝对路径，不依赖 CWD，不碰 /input 与 /app）：
  python3 /skills/weekly-skill/scripts/run_selftest.py
退出码：0 = 全部断言成立；1 = 任一断言不成立。
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def w(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(HERE, script)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode


GOOD_MS = """低资源命名实体识别旨在标注稀缺语料中的实体 [1]。迁移方法依赖同源语对 [2]。

## 参考文献
[1] 张三, 李四. 图神经网络综述[J]. 软件学报, 2021, 32(5): 1301-1320.
[2] Smith J, Doe A. Synthetic attention study[J]. Journal of Synthetic Studies, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.
"""

GOOD_MAP = """# 编号映射表（合成）
| 原编号 | 新编号 | 去向 | 备注 |
| --- | --- | --- | --- |
| 1 | 1 | 保留 | - |
| 2 | 2 | 保留 | - |
"""

GOOD_REFS = """[1] 张三, 李四. 图神经网络综述[J]. 软件学报, 2021, 32(5): 1301-1320.
[2] Smith J, Doe A. Synthetic attention study[J]. Journal of Synthetic Studies, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.
"""

EVIDENCE = """# 来源映射（合成）
| 编号 | 来源 |
| S1 | 张三 2021 |
| S2 | Smith 2022 |
"""

CASE = {"case_id": "selftest-syn",
        "output_contract": {"revised_manuscript": "str", "citation_report": "str"}}

GOOD_RJ = {"case_id": "selftest-syn", "status": "success",
           "revised_manuscript": "manuscript_revised.md",
           "citation_report": "citation_check_report.md",
           "sources": ["S1", "S2"], "uncertainty": "无",
           "change_log": ["合成自测"]}

GHOST_MS = GOOD_MS + "\n另见相关工作 [S9] 的讨论。\n"

checks = []  # (名称, 期望退出码, 实际退出码)


def expect(name, want, got):
    checks.append((name, want, got))
    print("[%s] %s：期望退出码 %d，实际 %d"
          % ("OK" if want == got else "BAD", name, want, got))


def main():
    tmp = tempfile.mkdtemp(prefix="skill_selftest_")
    print("[selftest] 合成 fixture 目录（临时）: %s" % tmp)

    # ---- 公共 fixture ----
    case_p = os.path.join(tmp, "case.json")
    w(case_p, json.dumps(CASE, ensure_ascii=False))
    good_ms = os.path.join(tmp, "good_ms.md")
    w(good_ms, GOOD_MS)
    rep = os.path.join(tmp, "report.md")

    # ---- 正例 ----
    expect("P1 citation_check 合规稿件", 0,
           run("citation_check.py", "--manuscript", good_ms, "--output", rep))
    good_map = os.path.join(tmp, "good_map.md")
    w(good_map, GOOD_MAP)
    expect("P2 mapping_check 合规映射表", 0,
           run("mapping_check.py", "--map", good_map, "--manuscript", good_ms,
               "--output", rep))
    good_refs = os.path.join(tmp, "good_refs.md")
    w(good_refs, GOOD_REFS)
    expect("P3 dedupe_refs 无重复文献表", 0,
           run("dedupe_refs.py", "--refs", good_refs, "--output", rep))
    expect("P4 roundtrip_check 字段齐全文献表", 0,
           run("roundtrip_check.py", "--refs", good_refs, "--output", rep))
    good_rj = os.path.join(tmp, "good_result.json")
    w(good_rj, json.dumps(GOOD_RJ, ensure_ascii=False))
    expect("P5 contract_check 合规 result 草稿", 0,
           run("contract_check.py", "--case-json", case_p, "--result-json", good_rj))
    outdir = os.path.join(tmp, "out_good")
    os.makedirs(outdir)
    w(os.path.join(outdir, "manuscript_revised.md"), GOOD_MS)
    w(os.path.join(outdir, "evidence_map.md"), EVIDENCE)
    w(os.path.join(outdir, "citation_check_report.md"), "# 报告（合成）\n")
    w(os.path.join(outdir, "numbering_map.md"), GOOD_MAP)
    w(os.path.join(outdir, "roundtrip_report.md"), "# 往返（合成）\n")
    w(os.path.join(outdir, "result.json"), json.dumps(GOOD_RJ, ensure_ascii=False))
    expect("P6 selfcheck 合规交付目录", 0,
           run("selfcheck.py", "--output-dir", outdir, "--case-json", case_p))

    # ---- 负例（必须被拒绝，退出码 1） ----
    n1 = os.path.join(tmp, "neg_ghost_num.md")
    w(n1, GOOD_MS.replace("实体 [1]", "实体 [1][9]"))
    expect("N1 citation_check 引而无目[9]", 1,
           run("citation_check.py", "--manuscript", n1, "--output", rep))
    n2 = os.path.join(tmp, "neg_no_year.md")
    w(n2, GOOD_MS.replace(", 2021, 32(5): 1301-1320.", "."))
    expect("N2 citation_check 条目缺年份", 1,
           run("citation_check.py", "--manuscript", n2, "--output", rep))
    out3 = os.path.join(tmp, "out_ghost_s")
    os.makedirs(out3)
    w(os.path.join(out3, "manuscript_revised.md"), GHOST_MS)
    w(os.path.join(out3, "evidence_map.md"), EVIDENCE)
    w(os.path.join(out3, "citation_check_report.md"), "# 报告（合成）\n")
    w(os.path.join(out3, "numbering_map.md"), GOOD_MAP)
    w(os.path.join(out3, "roundtrip_report.md"), "# 往返（合成）\n")
    w(os.path.join(out3, "result.json"), json.dumps(GOOD_RJ, ensure_ascii=False))
    expect("N3 selfcheck 幽灵来源[S9]", 1,
           run("selfcheck.py", "--output-dir", out3, "--case-json", case_p))
    bad_rj = dict(GOOD_RJ)
    del bad_rj["citation_report"]
    bad_rj_p = os.path.join(tmp, "bad_result.json")
    w(bad_rj_p, json.dumps(bad_rj, ensure_ascii=False))
    expect("N4 contract_check 契约字段缺失", 1,
           run("contract_check.py", "--case-json", case_p, "--result-json", bad_rj_p))
    dup_refs = os.path.join(tmp, "dup_refs.md")
    w(dup_refs, GOOD_REFS +
      "[3] Smith J, Doe A. Synthetic attention study[J]. J Synth Stud, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.\n")
    expect("N5 dedupe_refs 同DOI重复", 1,
           run("dedupe_refs.py", "--refs", dup_refs, "--output", rep))
    bad_map = os.path.join(tmp, "bad_map.md")
    w(bad_map, GOOD_MAP.replace("| 2 | 2 | 保留 | - |", "| 2 | 1 | 保留 | - |"))
    expect("N6 mapping_check 新编号碰撞", 1,
           run("mapping_check.py", "--map", bad_map, "--output", rep))
    poor_refs = os.path.join(tmp, "poor_refs.md")
    w(poor_refs, "[1] 张三, 李四. 图神经网络综述[J]. 软件学报.\n"
                 "[2] Smith J, Doe A. Synthetic attention study[J]. JSS, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.\n")
    expect("N7 roundtrip_check --strict 源头缺年份", 1,
           run("roundtrip_check.py", "--refs", poor_refs, "--strict", "--output", rep))

    bad = [c for c in checks if c[1] != c[2]]
    print("[selftest] 断言 %d 项：成立 %d，不成立 %d -> %s"
          % (len(checks), len(checks) - len(bad), len(bad),
             "FAIL" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
