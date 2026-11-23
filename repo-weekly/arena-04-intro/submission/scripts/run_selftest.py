#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_selftest.py — 本技能脚本的负路径自测（stdlib-only，全合成 fixture）。

在临时目录生成合成 fixture（正例 + 必须被拒绝的负例），逐个调用本技能脚本，
断言退出码符合预期：
  正例（期望退出码 0）：合规漏斗成稿 + 合规证据表 + 合规 result 草稿；
  负例（期望退出码 1，**必须被拒绝**）：
    N1 幽灵来源（正文 [S9] 未在证据表登记）；
    N2 漏斗缺段（无「研究空白/缺口」节）；
    N3 贡献-缺口数量不一致（2 缺口 vs 3 贡献）；
    N4 契约前置校验失败（result 草稿少 output_contract 字段）；
    N5 交付自查失败（result.json 少契约字段）。

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


GOOD_DRAFT = """# 引言（合成）

## 研究背景
低资源命名实体识别旨在标注稀缺语料中的实体 [S1]。

## 相关工作
迁移学习方法依赖同源语对 [S2]。

| 工作 | 方法 | 数据 | 结论 | 局限 |
| --- | --- | --- | --- | --- |
| S1 | 规则 | 合成语料 | 基线水平 | 仅英文 |
| S2 | 迁移 | 合成语料 | 有所提升 | 依赖双语词典 |

## 研究空白
1. 现有方法均假设双语词典可得 [S1][S2]。
2. 已有工作均无无词典场景评测 [S2]。

## 贡献
1. 提出无词典迁移方法（图 1），对应缺口 1。
2. 构建无词典评测基准（表 2），对应缺口 2。
"""

GOOD_EVIDENCE = """# 证据表（合成）
| 编号 | 来源 |
| S1 | 张三 2021 |
| S2 | Smith 2022 |
"""

CASE = {"case_id": "selftest-syn",
        "output_contract": {"introduction_draft": "str", "evidence_map": "str"}}

GOOD_RJ = {"case_id": "selftest-syn", "status": "success",
           "introduction_draft": "manuscript.md", "evidence_map": "evidence_map.md",
           "sources": ["S1", "S2"], "uncertainty": "无",
           "change_log": ["合成自测"]}

checks = []


def expect(name, want, got):
    checks.append((name, want, got))
    print("[%s] %s：期望退出码 %d，实际 %d"
          % ("OK" if want == got else "BAD", name, want, got))


def main():
    tmp = tempfile.mkdtemp(prefix="skill_selftest_")
    print("[selftest] 合成 fixture 目录（临时）: %s" % tmp)

    case_p = os.path.join(tmp, "case.json")
    w(case_p, json.dumps(CASE, ensure_ascii=False))
    draft = os.path.join(tmp, "good_draft.md")
    w(draft, GOOD_DRAFT)
    evid = os.path.join(tmp, "evidence_map.md")
    w(evid, GOOD_EVIDENCE)
    rep = os.path.join(tmp, "report.md")

    # ---- 正例 ----
    expect("P1 structure_check 合规成稿", 0,
           run("structure_check.py", "--draft", draft, "--evidence", evid,
               "--output", rep))
    good_rj = os.path.join(tmp, "good_result.json")
    w(good_rj, json.dumps(GOOD_RJ, ensure_ascii=False))
    expect("P2 contract_check 合规 result 草稿", 0,
           run("contract_check.py", "--case-json", case_p, "--result-json", good_rj))
    outdir = os.path.join(tmp, "out_good")
    os.makedirs(outdir)
    w(os.path.join(outdir, "manuscript.md"), GOOD_DRAFT)
    w(os.path.join(outdir, "evidence_map.md"), GOOD_EVIDENCE)
    w(os.path.join(outdir, "result.json"), json.dumps(GOOD_RJ, ensure_ascii=False))
    expect("P3 selfcheck 合规交付目录", 0,
           run("selfcheck.py", "--output-dir", outdir, "--case-json", case_p))

    # ---- 负例（必须被拒绝，退出码 1） ----
    n1 = os.path.join(tmp, "neg_ghost.md")
    w(n1, GOOD_DRAFT.replace("实体 [S1]", "实体 [S1][S9]"))
    expect("N1 structure_check 幽灵来源[S9]", 1,
           run("structure_check.py", "--draft", n1, "--evidence", evid,
               "--output", rep))
    n2 = os.path.join(tmp, "neg_no_gap.md")
    w(n2, GOOD_DRAFT.replace("## 研究空白", "## 研究动机与设想"))
    expect("N2 structure_check 漏斗缺段", 1,
           run("structure_check.py", "--draft", n2, "--evidence", evid,
               "--output", rep))
    n3 = os.path.join(tmp, "neg_mismatch.md")
    w(n3, GOOD_DRAFT.replace(
        "2. 构建无词典评测基准（表 2），对应缺口 2。",
        "2. 构建无词典评测基准（表 2），对应缺口 2。\n3. 给出开源实现（附录），对应缺口 2。"))
    expect("N3 structure_check 贡献-缺口不对应", 1,
           run("structure_check.py", "--draft", n3, "--evidence", evid,
               "--output", rep))
    bad_rj = dict(GOOD_RJ)
    del bad_rj["evidence_map"]
    bad_rj_p = os.path.join(tmp, "bad_result.json")
    w(bad_rj_p, json.dumps(bad_rj, ensure_ascii=False))
    expect("N4 contract_check 契约字段缺失", 1,
           run("contract_check.py", "--case-json", case_p, "--result-json", bad_rj_p))
    out5 = os.path.join(tmp, "out_bad")
    os.makedirs(out5)
    w(os.path.join(out5, "manuscript.md"), GOOD_DRAFT)
    w(os.path.join(out5, "evidence_map.md"), GOOD_EVIDENCE)
    w(os.path.join(out5, "result.json"), json.dumps(bad_rj, ensure_ascii=False))
    expect("N5 selfcheck result.json 少契约字段", 1,
           run("selfcheck.py", "--output-dir", out5, "--case-json", case_p))

    bad = [c for c in checks if c[1] != c[2]]
    print("[selftest] 断言 %d 项：成立 %d，不成立 %d -> %s"
          % (len(checks), len(checks) - len(bad), len(bad),
             "FAIL" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
