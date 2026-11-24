# -*- coding: utf-8 -*-
"""写作08 回归测试集（学竞品方法论：每次改动 SKILL.md 前后跑全量回归，锁定行为）。

覆盖：SKILL.md 承诺的全部机器断言与产物结构。
运行：python -I -B tests/test_writing08_regression.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURES = os.path.join(SCRIPTS, "fixtures")


def run_py(script, args):
    return subprocess.run(
        [sys.executable, "-I", "-B", os.path.join(SCRIPTS, script)] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class RegressionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="w08_reg_")

    # ---- R1 parse_library：bib 解析与条目表结构 ----
    def test_r1_parse_library_bib(self):
        out = os.path.join(self.tmp, "entries.json")
        p = run_py("parse_library.py", ["--input", os.path.join(FIXTURES, "library.bib"), "--output", out])
        self.assertEqual(p.returncode, 0, p.stderr)
        entries = load_json(out)
        entries = entries.get("entries", entries)
        self.assertEqual(len(entries), 5, "夹具库应为 5 条")
        first = entries[0]
        for key in ("id", "title", "year", "abstract"):
            self.assertIn(key, first, "条目表缺字段 %s" % key)

    # ---- R2 coverage_check：编造引用必须被检出 ----
    def test_r2_fabricated_ref_detected(self):
        entries = os.path.join(self.tmp, "entries.json")
        run_py("parse_library.py", ["--input", os.path.join(FIXTURES, "library.bib"), "--output", entries])
        # 成稿引用一条库里不存在的文献
        bad_draft = os.path.join(self.tmp, "bad_draft.md")
        with open(bad_draft, "w", encoding="utf-8") as f:
            f.write("先前工作 (Zhao et al., 2099) 证明了不存在的事情。另一处 (Liu et al., 2021) 是真实引用。\n")
        rep = os.path.join(self.tmp, "report.json")
        p = run_py("coverage_check.py", ["--draft", bad_draft, "--entries", entries, "--report", rep])
        self.assertEqual(p.returncode, 1, "编造引用必须以退出码 1 报错")
        r = load_json(rep)
        blob = json.dumps(r, ensure_ascii=False)
        self.assertIn("Zhao", blob, "编造引用 Zhao 必须被点名")

    # ---- R3 anchor_check：坏 quote 必须被检出 ----
    def test_r3_bad_anchor_detected(self):
        entries = os.path.join(self.tmp, "entries.json")
        run_py("parse_library.py", ["--input", os.path.join(FIXTURES, "library.bib"), "--output", entries])
        # 锚点 quote 故意改一个字（原文是"误报率显著上升"）
        anchors = [{"ref": "liu2021arimad", "quote": "误报率显著下降（被篡改）", "locator": {"section": "abstract"}}]
        apath = os.path.join(self.tmp, "anchors.json")
        with open(apath, "w", encoding="utf-8") as f:
            json.dump({"anchors": anchors}, f, ensure_ascii=False)
        p = run_py("anchor_check.py", ["--anchors", apath, "--entries", entries])
        self.assertNotEqual(p.returncode, 0, "坏 quote 必须非零退出")
        self.assertIn("显著下降", p.stdout + p.stderr, "坏 quote 应在报告中点名")

    # ---- R4 gap_chain_check：缺 basis 与链尾不指向本文都必须被检出 ----
    def test_r4_gap_chain_defects_detected(self):
        entries = os.path.join(self.tmp, "entries.json")
        run_py("parse_library.py", ["--input", os.path.join(FIXTURES, "library.bib"), "--output", entries])
        chain = [
            {"step": 1, "kind": "literature_gap", "basis": "",  # 缺 basis
             "evidence_or_author_judgment": "evidence",
             "evidence": {"ref": "liu2021arimad", "quote": "依赖平稳性假设，在趋势漂移场景下误报率显著上升"}},
            {"step": 2, "kind": "cross_gap", "basis": "x",
             "evidence_or_author_judgment": "evidence",
             "evidence": {"ref": "chen2020mp", "quote": "无需训练即可检测点异常与片段异常"}},
            {"step": 3, "kind": "cross_gap", "basis": "y",
             "evidence_or_author_judgment": "author_judgment"},  # 末步不指向 this_work
        ]
        cpath = os.path.join(self.tmp, "chain.json")
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump({"gap_chain": chain}, f, ensure_ascii=False)
        p = run_py("gap_chain_check.py", ["--chain", cpath, "--report", os.path.join(self.tmp, "cr.json")])
        out = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, "缺陷链必须非零退出")
        self.assertIn("BASIS", out.upper(), "缺 basis 应被点名")

    # ---- R5 合法全链（夹具）必须全绿 ----
    def test_r5_valid_fixture_chain_passes(self):
        entries = os.path.join(self.tmp, "entries.json")
        run_py("parse_library.py", ["--input", os.path.join(FIXTURES, "library.bib"), "--output", entries])
        p = run_py("gap_chain_check.py",
                   ["--chain", os.path.join(FIXTURES, "gap_chain.json"),
                    "--review", os.path.join(FIXTURES, "review_items.json"),
                    "--entries", entries])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    # ---- R6 SKILL.md 产物契约锁定：三件套路径 + 契约镜像段 ----
    def test_r6_skill_contract_locked(self):
        t = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
        for must in ["intro_related_work.md", "comparison_matrix.csv", "output_contract",
                     "研究背景", "相关工作", "研究空白", "贡献", "problem_setting",
                     "method_route", "data_evaluation", "scope", "support_relation"]:
            self.assertIn(must, t, "SKILL.md 缺关键承诺: %s" % must)

    # ---- R7 selftest 不破 ----
    def test_r7_selftest_passes(self):
        p = subprocess.run([sys.executable, "-I", "-B", os.path.join(SCRIPTS, "selftest.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0, p.stdout[-400:] + p.stderr[-400:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
