#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""负路径自测（文献文档解析技能）：用**全合成** fixture 验证本技能脚本的
正向可用性与负向拦截力——尤其是"必须被拒绝"的草稿确实被拒绝。

用法（绝对路径调用，不依赖 CWD）：

    python3 /skills/weekly-skill/scripts/selftest.py [--keep-dir]

覆盖的自测用例（全部合成数据）：
  正向：inventory / pdf_survey（文字层、混合页、扫描、加密、分块）/ selfcheck 全 PASS /
        contract_check PASS / finalize 固化。
  负路径（必须被拒绝，期望退出码 1）：
  N1. 交付缺 result.json → selfcheck FAIL；
  N2. 主产物声称"扫描页已全部 OCR 并完整覆盖"但缺必备章节、引用未登记 [S9]
      → selfcheck FAIL（跳过 OCR 页却声称覆盖的变体必须被拒绝）；
  N3. result.json 缺 output_contract 字段 → contract_check FAIL。
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
  "case_id": "SYNTH-PARSE-SELFTEST",
  "output_contract": {
    "parsed_document_path": "string",
    "evidence_map_path": "string",
    "survey_path": "string",
    "status": "string",
    "sources": "array",
    "uncertainty": "array",
    "change_log": "array"
  }
}
"""

GOOD_DOC = """# 文献解析结果：Synthetic Demo Paper（全合成 selftest fixture）

## 1. 解析概览
- 来源：S1 synth_text.pdf（1 页，有文字层）；提取视图：pdftotext -layout
- OCR 页覆盖声明：本页块无需 OCR 的页（ocr_coverage.md）

## 2. 元数据
- 标题：Synthetic Demo Paper
- 作者：A. Demo
- 摘要：原文未报告

## 3. 章节树
- 1 Introduction — p.1
- 3 Results — p.1

## 4. 正文（按区块）
[B001] [p.1] [col.full] [S1] [conf:high]
Zinc oxide is a wide band-gap semiconductor.

## 5. 图表与题注
表 1 [p.1] [S1] [conf:high] 候选区域 T001（table_registry.md）

## 6. 公式对照
式(1) [p.1] [conf:medium] Eg = 3.37 eV —— 置信度依据：上标线性化

## 7. 参考文献
[1] A. Demo, Synth. Mater. 1 (2020) 1.

## 8. 脚注与页眉页脚处置
- 无脚注；未检测到重复页眉页脚。

## 9. 置信度与未决事项
- conf 分布：high 2 / medium 1 / low 0；无 [NOT_READABLE]。
"""

DISHONEST_DOC = """# 文献解析结果：Synthetic Demo（全合成 selftest 负路径 fixture）

## 1. 解析概览
- 来源：S1 synth_mixed.pdf。全部页面（含扫描页）均已 OCR 并完整覆盖，无遗漏。

## 2. 元数据
- 标题：Synthetic Demo
- 作者：A. Demo
- 摘要：原文未报告

## 3. 章节树
- 1 Introduction — p.1

## 4. 正文（按区块）
[B001] [p.1] [col.full] [S1] [conf:high]
Zinc oxide is a wide band-gap semiconductor.
[B002] [p.2] [col.full] [S9] [conf:high]
This sentence was never OCR-verified but claims full coverage.

## 5. 图表与题注
原文未报告图或表。

## 7. 参考文献
[1] A. Demo, Synth. Mater. 1 (2020) 1.
"""


def build_pdf(objs, trailer_extra=b""):
    """objs: list[(num, body_bytes)]；生成带 xref 的合法 PDF（全合成）。"""
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num, body in objs:
        offsets[num] = len(out)
        out += ("%d 0 obj\n" % num).encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    maxnum = max(offsets)
    out += ("xref\n0 %d\n" % (maxnum + 1)).encode()
    out += b"0000000000 65535 f \n"
    for n in range(1, maxnum + 1):
        out += ("%010d 00000 n \n" % offsets[n]).encode()
    out += (b"trailer\n<< /Size " + str(maxnum + 1).encode() + b" /Root 1 0 R "
            + trailer_extra + b">>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF\n")
    return bytes(out)


def text_stream(lines):
    parts = ["BT /F1 12 Tf 72 720 Td 14 TL"]
    for i, ln in enumerate(lines):
        if i:
            parts.append("T*")
        parts.append("(%s) Tj" % ln.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)"))
    parts.append("ET")
    return " ".join(parts).encode()


def make_pdfs(root):
    """生成 4 个合成 PDF：文字层(含候选表格)、混合(第2页空白=需OCR)、扫描、加密。"""
    stream1 = text_stream([
        "Synthetic Demo Paper",
        "1 Introduction",
        "Zinc oxide is a wide band-gap semiconductor.",
        "3 Results",
        "The band gap was 3.37 eV. See Eq. (1).",
        "Table 1  Synthetic lattice parameters",
        "Sample    a (A)    c (A)",
        "Z1        3.250    5.207",
        "Z2        3.251    5.209",
        "References",
        "[1] A. Demo, Synth. Mater. 1 (2020) 1.",
    ])
    objs = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        (3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"),
        (4, b"<< /Length " + str(len(stream1)).encode() + b" >>\nstream\n" + stream1 + b"\nendstream"),
        (5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    with open(os.path.join(root, "synth_text.pdf"), "wb") as fh:
        fh.write(build_pdf(objs))

    # 混合页：p.1 有文字层，p.2 空白（无内容流）→ p.2 必须 OCR
    objs_mixed = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>"),
        (3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"),
        (4, b"<< /Length " + str(len(stream1)).encode() + b" >>\nstream\n" + stream1 + b"\nendstream"),
        (5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        (6, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"),
    ]
    with open(os.path.join(root, "synth_mixed.pdf"), "wb") as fh:
        fh.write(build_pdf(objs_mixed))

    objs_scan = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        (3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"),
    ]
    with open(os.path.join(root, "synth_scanned.pdf"), "wb") as fh:
        fh.write(build_pdf(objs_scan))

    stream_e = text_stream(["Encrypted demo."])
    objs_enc = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        (3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"),
        (4, b"<< /Length " + str(len(stream_e)).encode() + b" >>\nstream\n" + stream_e + b"\nendstream"),
        (5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        (6, b"<< /Filter /Standard /V 1 /R 2 /Length 40 /P -4 "
            b"/O (01234567890123456789012345678901) /U (01234567890123456789012345678901) >>"),
    ]
    with open(os.path.join(root, "synth_encrypted.pdf"), "wb") as fh:
        fh.write(build_pdf(objs_enc, trailer_extra=b"/Encrypt 6 0 R "))


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

    root = tempfile.mkdtemp(prefix="parse_selftest_")
    print("[selftest] fixture 目录（全合成）：%s" % root)
    inp = os.path.join(root, "input")
    os.makedirs(inp, exist_ok=True)
    w(os.path.join(inp, "case.json"), CASE_JSON)
    w(os.path.join(inp, "task.md"), "# 合成 selftest 任务\n")
    make_pdfs(inp)
    case = os.path.join(inp, "case.json")

    # 交付 fixture
    good = os.path.join(root, "output-good")
    w(os.path.join(good, "parsed_document.md"), GOOD_DOC)
    w(os.path.join(good, "evidence_map.md"),
      "# 证据映射表（合成）\n\n| 编号 | 文件 |\n|---|---|\n| S1 | synth_text.pdf |\n\n"
      "| 区块 | 来源 |\n|---|---|\n| B001 | S1 |\n\n## 待确认项\n- 无\n")
    good_rj = {"case_id": "SYNTH-PARSE-SELFTEST", "status": "success",
               "parsed_document_path": "x", "evidence_map_path": "x", "survey_path": "x",
               "sources": [{"id": "S1", "file": "synth_text.pdf"}],
               "uncertainty": ["合成 fixture"], "change_log": [{"step": 0, "action": "落盘"}]}
    w(os.path.join(good, "result.json"), json.dumps(good_rj, ensure_ascii=False, indent=2))
    w(os.path.join(good, "survey.json"),
      json.dumps({"ocr_pages": [], "text_layer_present": True}, ensure_ascii=False))

    bad = os.path.join(root, "output-bad")   # N1：缺 result.json
    w(os.path.join(bad, "parsed_document.md"), GOOD_DOC)
    w(os.path.join(bad, "evidence_map.md"), "# 证据映射表\n\n| S1 | synth_text.pdf |\n")

    dishonest = os.path.join(root, "output-dishonest")  # N2：声称覆盖但缺章节+未登记来源
    w(os.path.join(dishonest, "parsed_document.md"), DISHONEST_DOC)
    w(os.path.join(dishonest, "evidence_map.md"),
      "# 证据映射表\n\n| 编号 | 文件 |\n|---|---|\n| S1 | synth_mixed.pdf |\n")
    w(os.path.join(dishonest, "result.json"),
      json.dumps(good_rj, ensure_ascii=False, indent=2))
    w(os.path.join(dishonest, "survey.json"),
      json.dumps({"ocr_pages": [2], "text_layer_present": True}, ensure_ascii=False))

    warn_only = os.path.join(root, "output-warn")  # C1：只应 WARN
    w(os.path.join(warn_only, "parsed_document.md"), GOOD_DOC)
    w(os.path.join(warn_only, "evidence_map.md"),
      "# 证据映射表（合成）\n\n| S1 | synth_text.pdf |\n| B001 | S1 |\n\n## 待确认项\n- 无\n")
    warn_rj = dict(good_rj)
    warn_rj["status"] = "partial"
    warn_rj["uncertainty"] = []
    w(os.path.join(warn_only, "result.json"), json.dumps(warn_rj, ensure_ascii=False))

    broken_rj = os.path.join(root, "broken_result.json")  # N3：缺契约字段
    tmp = dict(good_rj)
    del tmp["survey_path"]
    w(broken_rj, json.dumps(tmp, ensure_ascii=False))

    tests = []  # (名称, 期望退出码非零?, 实际退出码, 补充判定, 输出)

    def expect(name, rc, out, expect_fail=False, must_contain=()):
        ok = (rc != 0) if expect_fail else (rc == 0)
        for needle in must_contain:
            if needle not in out:
                ok = False
        tests.append((ok, name, rc, out))

    work = os.path.join(root, "work")
    rc, out = run("inventory.py", "--input", inp, "--output",
                  os.path.join(work, "materials_register.md"))
    expect("正向：inventory 清点", rc, out)

    sv_text = os.path.join(work, "survey-text")
    rc, out = run("pdf_survey.py", "--pdf", os.path.join(inp, "synth_text.pdf"),
                  "--output", sv_text)
    extra = ()
    survey_file = os.path.join(sv_text, "survey.json")
    if rc == 0 and os.path.isfile(survey_file):
        with open(survey_file, "r", encoding="utf-8-sig") as fh:
            sv = json.load(fh)
        if sv.get("ocr_pages") != [] or "table_regions" not in sv:
            extra = ("survey.json 缺 ocr_pages/table_regions 字段",)
        if not os.path.isfile(os.path.join(sv_text, "ocr_coverage.md")):
            extra += ("缺 ocr_coverage.md",)
        if not os.path.isfile(os.path.join(sv_text, "table_registry.md")):
            extra += ("缺 table_registry.md",)
    expect("正向：pdf_survey 文字层 PDF（含 ocr_pages/table_registry 产物）",
           rc, out, must_contain=extra)

    sv_mixed = os.path.join(work, "survey-mixed")
    rc, out = run("pdf_survey.py", "--pdf", os.path.join(inp, "synth_mixed.pdf"),
                  "--output", sv_mixed)
    if rc == 0 and os.path.isfile(os.path.join(sv_mixed, "survey.json")):
        with open(os.path.join(sv_mixed, "survey.json"), "r", encoding="utf-8-sig") as fh:
            sv = json.load(fh)
        if sv.get("ocr_pages") != [2]:
            extra = ("ocr_pages 应为 [2]，实际 %s" % sv.get("ocr_pages"),)
        else:
            extra = ()
    else:
        extra = ("survey.json 未生成",)
    expect("正向：pdf_survey 混合页 PDF → p.2 列入 OCR 页覆盖清单",
           rc, out, must_contain=extra)

    rc, out = run("pdf_survey.py", "--pdf", os.path.join(inp, "synth_scanned.pdf"),
                  "--output", os.path.join(work, "survey-scan"))
    expect("正向：pdf_survey 扫描件（异常分级不中断）", rc, out)

    rc, out = run("pdf_survey.py", "--pdf", os.path.join(inp, "synth_encrypted.pdf"),
                  "--output", os.path.join(work, "survey-enc"))
    expect("正向：pdf_survey 加密件（blocker 登记不中断）", rc, out)

    rc, out = run("pdf_survey.py", "--pdf", os.path.join(inp, "synth_text.pdf"),
                  "--output", os.path.join(work, "survey-chunk"),
                  "--first-page", "1", "--last-page", "1")
    expect("正向：pdf_survey 分块参数 -f/-l", rc, out)

    rc, out = run("selfcheck.py", "--output", good, "--case", case)
    expect("正向：selfcheck 合格交付全 PASS", rc, out)

    rc, out = run("selfcheck.py", "--output", bad, "--case", case)
    expect("负路径 N1：缺 result.json 必须被拒绝", rc, out, expect_fail=True)

    rc, out = run("selfcheck.py", "--output", dishonest, "--case", case)
    expect("负路径 N2：声称 OCR 全覆盖但缺章节/来源未登记必须被拒绝",
           rc, out, expect_fail=True, must_contain=("FAIL",))

    rc, out = run("selfcheck.py", "--output", warn_only, "--case", case)
    expect("校准 C1：partial 无 uncertainty 只 WARN 不 FAIL（退出码 0）",
           rc, out, must_contain=("[WARN]",))

    rc, out = run("contract_check.py", "--case", case,
                  "--result", os.path.join(good, "result.json"))
    expect("正向：contract_check 字段齐全", rc, out)

    rc, out = run("contract_check.py", "--case", case, "--result", broken_rj)
    expect("负路径 N3：缺契约字段必须被拒绝", rc, out, expect_fail=True)

    fin_out = os.path.join(root, "output-finalize")
    rc, out = run("finalize.py", "--work", work, "--output", fin_out, "--case", case,
                  "--skipped", "步骤3: OCR 排队超时，合成演示")
    extra = ()
    fin_rj = os.path.join(fin_out, "result.json")
    if rc == 0 and os.path.isfile(fin_rj):
        with open(fin_rj, "r", encoding="utf-8-sig") as fh:
            rj = json.load(fh)
        if not rj.get("skipped_reason"):
            extra = ("result.json 缺 skipped_reason",)
        missing = [f for f in ("parsed_document_path", "evidence_map_path", "survey_path",
                               "status", "sources", "uncertainty", "change_log")
                   if f not in rj]
        if missing:
            extra += ("契约字段缺失：%s" % missing,)
        if not os.path.isfile(os.path.join(fin_out, "parsed_document.md")):
            extra += ("缺诚实占位 parsed_document.md",)
    else:
        extra = ("finalize 未产出 result.json",)
    expect("正向：finalize 中断兜底（skipped_reason + 契约字段齐全）",
           rc, out, must_contain=extra)

    for script in ("inventory.py", "pdf_survey.py", "selfcheck.py",
                   "contract_check.py", "finalize.py"):
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
