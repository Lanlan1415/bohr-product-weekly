#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""负路径自测（文献翻译技能）：用**全合成** fixture 验证本技能脚本的
正向可用性与负向拦截力——尤其是"必须被拒绝"的译稿确实被拒绝。

用法（绝对路径调用，不依赖 CWD）：

    python3 /skills/weekly-skill/scripts/selftest.py [--keep-dir]

覆盖的自测用例（全部合成数据）：
  正向：inventory / term_consistency / align_check / sentence_anchor /
        selfcheck 全 PASS / contract_check PASS / finalize 固化。
  负路径（必须被拒绝，期望退出码 1）：
  N1. 译文使用术语表禁用变体 → term_consistency FAIL；
  N2. 译文漏段（P002 未译）→ align_check FAIL（漏段却报 complete 的段级形态）；
  N3. 锚定记录零锚句段 + 空译文 → sentence_anchor FAIL（漏段却报 complete 的句级形态）；
  N4. 交付主产物缺"术语表"必备章节 → selfcheck FAIL；
  N5. result.json 缺 output_contract 字段 → contract_check FAIL。
  校准纪律用例：
  C1. 内容齐全但 status=partial 且 uncertainty 为空 → selfcheck 只 WARN、退出码 0
     （新增检查项不得把原本能通过的草稿判 FAIL）。

打印逐条结果；全部符合预期退出码 0，任一不符退出码 1。
（v3 注：本脚本验证的是校验器拦截力，属开发期自测；真实评测交付时，
任何校验脚本的退出码都不作为交付门禁——FAIL 项记入 uncertainty/skipped_reason 后照常交付。）
仅使用 Python 标准库；fixture 写在系统临时目录；不访问网络；不修改 /input。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS = os.path.dirname(os.path.abspath(__file__))

CASE_JSON = """{
  "case_id": "SYNTH-TRANS-SELFTEST",
  "output_contract": {
    "bilingual_path": "string",
    "glossary_path": "string",
    "evidence_map_path": "string",
    "status": "string",
    "sources": "array",
    "uncertainty": "array",
    "change_log": "array"
  }
}
"""

SOURCE_PARAS = """[P001] Band-Gap Tuning of Synthetic ZnO Nanorods
[P002] The band gap of sample Z1 was determined to be 3.37 eV.
[P003] The nanorods were grown by hydrothermal synthesis at 90 C for 6 h.
"""

GLOSSARY = """# 全合成 selftest 术语表
band gap = 带隙 ; 能隙, 禁带宽度
hydrothermal synthesis = 水热合成 ; 水热法合成
"""

DRAFT_OK = """[P001] Band-Gap Tuning of Synthetic ZnO Nanorods
译文：合成 ZnO 纳米棒的带隙调控

[P002] The band gap of sample Z1 was determined to be 3.37 eV.
译文：样品 Z1 的带隙测定为 3.37 eV。

[P003] The nanorods were grown by hydrothermal synthesis at 90 C for 6 h.
译文：纳米棒通过水热合成在 90 °C 下反应 6 h 制得。
"""

DRAFT_BAD_TERM = DRAFT_OK.replace("带隙", "能隙").replace("水热合成在", "水热法合成在")

DRAFT_BAD_ALIGN = """[P001] Band-Gap Tuning of Synthetic ZnO Nanorods
译文：合成 ZnO 纳米棒的带隙调控

[P003] The nanorods were grown by hydrothermal synthesis at 90 C for 6 h.
译文：纳米棒通过水热合成在 90 °C 下反应 6 h 制得。
"""

ANCHORS_OK = """# 全合成句级锚定记录（sentence_id + 原文 + 译文 + 页码）
[P001-S01] [p.1] Band-Gap Tuning of Synthetic ZnO Nanorods || 合成 ZnO 纳米棒的带隙调控
[P002-S01] [p.1] The band gap of sample Z1 was determined to be 3.37 eV. || 样品 Z1 的带隙测定为 3.37 eV。
[P003-S01] [p.1] The nanorods were grown by hydrothermal synthesis at 90 C for 6 h. || 纳米棒通过水热合成在 90 °C 下反应 6 h 制得。
"""

# 负路径：P002 整段零锚句（漏段却报 complete 的句级形态）+ P003 译文为空
ANCHORS_BAD = """# 全合成负路径锚定记录
[P001-S01] [p.1] Band-Gap Tuning of Synthetic ZnO Nanorods || 合成 ZnO 纳米棒的带隙调控
[P003-S01] [p.1] The nanorods were grown by hydrothermal synthesis at 90 C for 6 h. || 
"""

BILINGUAL_OK = """# 双语对照译文：Band-Gap Tuning of Synthetic ZnO Nanorods（全合成 selftest fixture）

## 0. 元数据与翻译说明
- 来源：[S1] paper_en.md（文字层直取）

## 1. 术语表
| 原文术语 | 首选译名 | 禁用变体 |
|---|---|---|
| band gap | 带隙 | 能隙, 禁带宽度 |
| hydrothermal synthesis | 水热合成 | 水热法合成 |

## 2. 双语对照正文

[P001] Band-Gap Tuning of Synthetic ZnO Nanorods
译文：合成 ZnO 纳米棒的带隙调控

[P002] The band gap of sample Z1 was determined to be 3.37 eV.
译文：样品 Z1 的带隙测定为 3.37 eV。

[P003] The nanorods were grown by hydrothermal synthesis at 90 C for 6 h.
译文：纳米棒通过水热合成在 90 °C 下反应 6 h 制得。

## 4. 译文核验清单
| 核验项 | 抽查处数 | 结果 |
|---|---|---|
| 数字 | 3 | 通过 |

## 5. 未决项
- 无 [UNSURE]；无 [NOT_TRANSLATED]。
"""


def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def run(script, *script_args):
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)] + list(script_args),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description="负路径自测（全合成 fixture）")
    parser.add_argument("--keep-dir", action="store_true", help="保留临时 fixture 目录以便人工查看")
    args = parser.parse_args(argv)

    root = tempfile.mkdtemp(prefix="trans_selftest_")
    print("[selftest] fixture 目录（全合成）：%s" % root)
    inp = os.path.join(root, "input")
    work = os.path.join(root, "work")
    os.makedirs(inp, exist_ok=True)
    case = os.path.join(inp, "case.json")
    w(case, CASE_JSON)
    w(os.path.join(inp, "task.md"), "# 合成 selftest 任务：全文翻译为中文\n")
    w(os.path.join(inp, "paper_en.md"), "Synthetic demo source. (全合成 fixture)\n")
    w(os.path.join(work, "source_paras.md"), SOURCE_PARAS)
    w(os.path.join(work, "glossary.tsv"), GLOSSARY)
    w(os.path.join(work, "draft_ok.md"), DRAFT_OK)
    w(os.path.join(work, "draft_bad_term.md"), DRAFT_BAD_TERM)
    w(os.path.join(work, "draft_bad_align.md"), DRAFT_BAD_ALIGN)
    w(os.path.join(work, "anchors_ok.md"), ANCHORS_OK)
    w(os.path.join(work, "anchors_bad.md"), ANCHORS_BAD)

    good_rj = {"case_id": "SYNTH-TRANS-SELFTEST", "status": "success",
               "bilingual_path": "x", "glossary_path": "x", "evidence_map_path": "x",
               "sources": [{"id": "S1", "file": "paper_en.md"}],
               "uncertainty": ["合成 fixture"], "change_log": [{"step": 0, "action": "落盘"}]}

    good = os.path.join(root, "output-good")
    w(os.path.join(good, "bilingual_translation.md"), BILINGUAL_OK)
    w(os.path.join(good, "glossary.tsv"), GLOSSARY)
    w(os.path.join(good, "evidence_map.md"),
      "# 证据映射表（合成）\n\n| 编号 | 文件 |\n|---|---|\n| S1 | paper_en.md |\n\n"
      "| 段号 | 来源 |\n|---|---|\n| P001 | S1 |\n")
    w(os.path.join(good, "result.json"), json.dumps(good_rj, ensure_ascii=False, indent=2))

    bad = os.path.join(root, "output-bad")  # N4：缺"术语表"章节
    w(os.path.join(bad, "bilingual_translation.md"),
      BILINGUAL_OK.replace("## 1. 术语表", "## 1. 词汇对照（改名导致缺章节）"))
    w(os.path.join(bad, "evidence_map.md"), "# 证据映射表\n\n| S1 | paper_en.md |\n")
    w(os.path.join(bad, "result.json"), json.dumps(good_rj, ensure_ascii=False, indent=2))

    warn_only = os.path.join(root, "output-warn")  # C1：只应 WARN
    w(os.path.join(warn_only, "bilingual_translation.md"), BILINGUAL_OK)
    w(os.path.join(warn_only, "evidence_map.md"),
      "# 证据映射表（合成）\n\n| S1 | paper_en.md |\n| P001 | S1 |\n")
    warn_rj = dict(good_rj)
    warn_rj["status"] = "partial"
    warn_rj["uncertainty"] = []
    w(os.path.join(warn_only, "result.json"), json.dumps(warn_rj, ensure_ascii=False))

    broken_rj = os.path.join(root, "broken_result.json")  # N5：缺契约字段
    tmp = dict(good_rj)
    del tmp["glossary_path"]
    w(broken_rj, json.dumps(tmp, ensure_ascii=False))

    tests = []

    def expect(name, rc, out, expect_fail=False, must_contain=()):
        ok = (rc != 0) if expect_fail else (rc == 0)
        for needle in must_contain:
            if needle not in out:
                ok = False
        tests.append((ok, name, rc, out))

    rc, out = run("inventory.py", "--input", inp, "--output",
                  os.path.join(work, "materials_register.md"))
    expect("正向：inventory 清点", rc, out)

    rc, out = run("term_consistency.py", "--glossary", os.path.join(work, "glossary.tsv"),
                  "--translation", os.path.join(work, "draft_ok.md"),
                  "--source", os.path.join(work, "source_paras.md"),
                  "--report", os.path.join(work, "term_report_ok.md"))
    expect("正向：term_consistency 合格译稿", rc, out)

    rc, out = run("term_consistency.py", "--glossary", os.path.join(work, "glossary.tsv"),
                  "--translation", os.path.join(work, "draft_bad_term.md"),
                  "--source", os.path.join(work, "source_paras.md"),
                  "--report", os.path.join(work, "term_report_bad.md"))
    expect("负路径 N1：禁用变体必须被拒绝", rc, out, expect_fail=True)

    rc, out = run("align_check.py", "--source", os.path.join(work, "source_paras.md"),
                  "--translation", os.path.join(work, "draft_ok.md"),
                  "--report", os.path.join(work, "align_report_ok.md"))
    expect("正向：align_check 段号一一对应", rc, out)

    rc, out = run("align_check.py", "--source", os.path.join(work, "source_paras.md"),
                  "--translation", os.path.join(work, "draft_bad_align.md"),
                  "--report", os.path.join(work, "align_report_bad.md"))
    expect("负路径 N2：漏段（P002）必须被拒绝", rc, out, expect_fail=True,
           must_contain=("漏译",))

    rc, out = run("sentence_anchor.py", "--anchors", os.path.join(work, "anchors_ok.md"),
                  "--source", os.path.join(work, "source_paras.md"),
                  "--report", os.path.join(work, "anchor_report_ok.md"))
    expect("正向：sentence_anchor 逐句回链齐全", rc, out)

    rc, out = run("sentence_anchor.py", "--anchors", os.path.join(work, "anchors_bad.md"),
                  "--source", os.path.join(work, "source_paras.md"),
                  "--report", os.path.join(work, "anchor_report_bad.md"))
    expect("负路径 N3：零锚句段+空译文必须被拒绝", rc, out, expect_fail=True,
           must_contain=("零锚句",))

    rc, out = run("selfcheck.py", "--output", good, "--case", case)
    expect("正向：selfcheck 合格交付全 PASS", rc, out)

    rc, out = run("selfcheck.py", "--output", bad, "--case", case)
    expect("负路径 N4：缺术语表章节必须被拒绝", rc, out, expect_fail=True)

    rc, out = run("selfcheck.py", "--output", warn_only, "--case", case)
    expect("校准 C1：partial 无 uncertainty 只 WARN 不 FAIL（退出码 0）",
           rc, out, must_contain=("[WARN]",))

    rc, out = run("contract_check.py", "--case", case,
                  "--result", os.path.join(good, "result.json"))
    expect("正向：contract_check 字段齐全", rc, out)

    rc, out = run("contract_check.py", "--case", case, "--result", broken_rj)
    expect("负路径 N5：缺契约字段必须被拒绝", rc, out, expect_fail=True)

    # finalize：work 里只有 translation_draft.md（中断现场）
    fin_work = os.path.join(root, "work-interrupted")
    w(os.path.join(fin_work, "translation_draft.md"), DRAFT_OK)
    fin_out = os.path.join(root, "output-finalize")
    rc, out = run("finalize.py", "--work", fin_work, "--output", fin_out, "--case", case,
                  "--skipped", "步骤4: 预算耗尽，合成演示")
    extra = ()
    fin_rj = os.path.join(fin_out, "result.json")
    if rc == 0 and os.path.isfile(fin_rj):
        with open(fin_rj, "r", encoding="utf-8-sig") as fh:
            rj = json.load(fh)
        if not rj.get("skipped_reason"):
            extra = ("result.json 缺 skipped_reason",)
        missing = [f for f in ("bilingual_path", "glossary_path", "evidence_map_path",
                               "status", "sources", "uncertainty", "change_log")
                   if f not in rj]
        if missing:
            extra += ("契约字段缺失：%s" % missing,)
        fin_main = os.path.join(fin_out, "bilingual_translation.md")
        if os.path.isfile(fin_main):
            with open(fin_main, "r", encoding="utf-8-sig") as fh:
                if "带隙测定为 3.37 eV" not in fh.read():
                    extra += ("固化稿未保留已译段落",)
        else:
            extra += ("缺固化双语稿",)
    else:
        extra = ("finalize 未产出 result.json",)
    expect("正向：finalize 中断兜底（已译段落保留 + skipped_reason）",
           rc, out, must_contain=extra)

    for script in ("inventory.py", "term_consistency.py", "align_check.py",
                   "sentence_anchor.py", "selfcheck.py", "contract_check.py",
                   "finalize.py"):
        rc, out = run(script, "--help")
        expect("正向：%s --help 可用" % script, rc, out)

    n_bad = 0
    print("")
    for ok, name, rc, out in tests:
        if not ok:
            n_bad += 1
        print("[%s] %s（退出码 %d）" % ("PASS" if ok else "FAIL", name, rc))
    print("[selftest] %d/%d 用例符合预期%s"
          % (len(tests) - n_bad, len(tests),
             "；fixture 保留于 %s" % root if args.keep_dir else ""))
    if not args.keep_dir:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
