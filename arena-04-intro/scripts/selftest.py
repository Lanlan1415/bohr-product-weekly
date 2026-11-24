#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py — 本地自测：夹具全链（parse_library → coverage_check → anchor_check →
gap_chain_check → write_matrix），python -I 运行全链退出码 0。

夹具位于 scripts/fixtures/（全部为虚构内容）：
    library.bib        5 条虚构文献（BibTeX 子集）
    draft.md           草稿：故意含 1 条编造引用 (Nakamura et al., 2019)
    materials.md       底稿方法摘要（含 Figure 1-3 / Table 1-2，无 Figure 4）
    groups.json        3 组分组：故意含 1 个单篇组（图拓扑方法）
    contributions.json 4 条贡献：故意含 1 个底稿中不存在的 Figure 4、1 条作者判断
    anchors.json       3 条锚点：故意含 1 条坏 quote（原文写的是“五万条”，quote 写“10 条”）
    gap_chain.json     4 环链条：故意含 1 个缺 basis 的环节（step 2）
    review_items.json  人工复核清单（覆盖作者判断环与未对齐贡献）

用法
    python -I scripts/selftest.py [--keep]

退出码：0 = 全部断言通过；1 = 存在失败项（逐条打印）。
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES = SCRIPT_DIR / "fixtures"

SCRIPTS = ["parse_library.py", "coverage_check.py", "anchor_check.py",
           "gap_chain_check.py", "write_matrix.py"]

failures = []
passed = 0


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print("  PASS  %s" % name)
        return True
    failures.append("%s %s" % (name, ("— " + detail) if detail else ""))
    print("  FAIL  %s  %s" % (name, detail))
    return False


def run(script, args, cwd=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "-I", str(SCRIPT_DIR / script)] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, env=env, cwd=cwd,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def parse_json_out(proc):
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None


def count(report, code):
    return sum(1 for f in report.get("findings", []) if f.get("code") == code)


def main(argv=None):
    ap = argparse.ArgumentParser(description="夹具全链自测（所有脚本以 python -I 子进程运行）")
    ap.add_argument("--keep", action="store_true", help="保留临时目录以便排查")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    tmpdir = tempfile.mkdtemp(prefix="irww-selftest-")
    print("临时目录：%s" % tmpdir)
    print("夹具目录：%s" % FIXTURES)

    entries_json = Path(tmpdir) / "entries.json"
    matrix_csv = Path(tmpdir) / "comparison_matrix.csv"

    # ---------- 0. --help ----------
    print("\n[0] 每个脚本 --help 可用（退出码 0）")
    for s in SCRIPTS:
        p = run(s, ["--help"])
        check("%s --help" % s, p.returncode == 0 and "usage" in p.stdout.lower(),
              "rc=%d stderr=%s" % (p.returncode, p.stderr[:200]))

    # ---------- 1. parse_library：BibTeX 子集 ----------
    print("\n[1] parse_library 解析 BibTeX 子集")
    p = run("parse_library.py", ["--input", FIXTURES / "library.bib", "--output", entries_json])
    rep = parse_json_out(p)
    check("parse_library 退出码 0", p.returncode == 0, p.stderr[:300])
    check("解析出 5 条条目", bool(rep) and rep.get("count") == 5,
          "count=%r" % (rep or {}).get("count"))
    entries = (rep or {}).get("entries", [])
    ids = {e.get("id") for e in entries}
    expected_ids = {"liu2021arimad", "chen2020mp", "wang2022lstmae", "zhao2023transc", "li2021gdnx"}
    check("条目键完整", ids == expected_ids, "ids=%r" % ids)
    check("字段齐备（title/authors/year/abstract 非空）",
          all(e.get("title") and e.get("authors") and e.get("year") and e.get("abstract") for e in entries))
    check("作者拆分（liu2021arimad → 2 位作者）",
          any(e.get("id") == "liu2021arimad" and len(e.get("authors", [])) == 2 for e in entries))

    # 1b. JSON 格式
    print("[1b] parse_library 解析 JSON 格式")
    json_in = Path(tmpdir) / "library.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump({"references": [
            {"id": "demo1", "title": "虚构条目一", "author": "王, 五", "year": 2021,
             "abstract": "这是摘要内容一。", "venue": "虚构学报"},
            {"key": "demo2", "title": "虚构条目二", "authors": ["张三", "李四"], "year": "2022",
             "abstract": "这是摘要内容二。"}]}, f, ensure_ascii=False)
    p = run("parse_library.py", ["--input", json_in])
    rep = parse_json_out(p)
    check("JSON 格式解析 2 条", bool(rep) and rep.get("count") == 2, p.stdout[:200])
    check("JSON 别名归一（author→authors 列表）",
          bool(rep) and rep["entries"][0].get("authors") == ["王, 五"])

    # 1c. 编号列表格式
    print("[1c] parse_library 解析编号列表")
    list_in = Path(tmpdir) / "library.txt"
    list_in.write_text("[1] 王五, 李四. 2021. 虚构的检测方法研究. 虚构学报.\n"
                       "2. Zhang San. 2022. A fictional survey of detectors. Fake Press.\n",
                       encoding="utf-8")
    p = run("parse_library.py", ["--input", list_in])
    rep = parse_json_out(p)
    check("编号列表解析 2 条", bool(rep) and rep.get("count") == 2, p.stdout[:200])
    check("编号列表带启发式警告",
          bool(rep) and any(w.get("code") == "LIST_FORMAT_HEURISTIC" for w in rep.get("warnings", [])))

    # ---------- 2. coverage_check：检出编造引用等 ----------
    print("\n[2] coverage_check 检出 1 条编造引用 + 1 个底稿外图表号 + 1 个单篇组")
    p = run("coverage_check.py", ["--draft", FIXTURES / "draft.md", "--entries", entries_json,
                                  "--groups", FIXTURES / "groups.json",
                                  "--contributions", FIXTURES / "contributions.json",
                                  "--materials", FIXTURES / "materials.md"])
    rep = parse_json_out(p)
    check("coverage_check 检出错误时退出码 1", p.returncode == 1, "rc=%d %s" % (p.returncode, p.stderr[:200]))
    check("恰好 1 条编造引用", bool(rep) and count(rep, "CITATION_NOT_IN_LIBRARY") == 1,
          "n=%d" % (count(rep, "CITATION_NOT_IN_LIBRARY") if rep else -1))
    check("编造对象为 Nakamura et al. 2019",
          bool(rep) and any("Nakamura" in f.get("detail", "") for f in rep.get("findings", [])))
    check("恰好 1 个底稿外图表号（Figure 4）",
          bool(rep) and count(rep, "CONTRIBUTION_ARTIFACT_MISSING") == 1
          and any("Figure 4" in f.get("detail", "") for f in rep.get("findings", [])))
    check("恰好 1 个单篇组（GROUP_TOO_SMALL）",
          bool(rep) and count(rep, "GROUP_TOO_SMALL") == 1)
    check("未引条目 = li2021gdnx（覆盖率 0.8）",
          bool(rep) and rep.get("coverage", {}).get("uncited") == ["li2021gdnx"]
          and abs(rep.get("coverage", {}).get("ratio", 0) - 0.8) < 1e-6,
          "coverage=%r" % (rep or {}).get("coverage"))
    check("作者判断贡献被标记", bool(rep) and count(rep, "CLAIM_AUTHOR_JUDGMENT") == 1)
    check("报告 ok=false（存在 error）", bool(rep) and rep.get("ok") is False)

    # ---------- 3. anchor_check：检出坏 quote ----------
    print("\n[3] anchor_check 检出 1 条坏 quote（并验证空白归一/逐字命中）")
    p = run("anchor_check.py", ["--anchors", FIXTURES / "anchors.json", "--entries", entries_json])
    rep = parse_json_out(p)
    check("anchor_check 检出错误时退出码 1", p.returncode == 1, "rc=%d %s" % (p.returncode, p.stderr[:200]))
    rows = (rep or {}).get("results", [])
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    bad_rows = [r for r in rows if r.get("status") == "quote_not_found"]
    check("2 条锚点逐字命中（含跨行 quote 归一）", len(ok_rows) == 2,
          "ok=%d" % len(ok_rows))
    check("恰好 1 条坏 quote", len(bad_rows) == 1 and bad_rows[0].get("ref") == "wang2022lstmae",
          "bad=%r" % [r.get("ref") for r in bad_rows])
    check("坏 quote 附带最接近句提示", bool(bad_rows) and bad_rows[0].get("hint"))
    check("报告 ok=false", bool(rep) and rep.get("ok") is False)

    # ---------- 4. gap_chain_check：检出缺 basis 环节 ----------
    print("[4] gap_chain_check：合法夹具链 exit 0；运行时清空 basis 应检出 exit 1")
    p = run("gap_chain_check.py", ["--chain", FIXTURES / "gap_chain.json",
                                   "--review", FIXTURES / "review_items.json",
                                   "--entries", entries_json])
    rep = parse_json_out(p)
    check("合法链退出码 0", p.returncode == 0, "rc=%d %s" % (p.returncode, p.stderr[:200]))
    check("合法链无 error", bool(rep) and rep.get("summary", {}).get("errors") == 0)
    chain_bad = Path(tmpdir) / "gap_chain_badbasis.json"
    with open(FIXTURES / "gap_chain.json", encoding="utf-8") as f:
        chain_bad_obj = json.load(f)
    chain_bad_obj["gap_chain"][1]["basis"] = ""
    with open(chain_bad, "w", encoding="utf-8") as f:
        json.dump(chain_bad_obj, f, ensure_ascii=False)
    p = run("gap_chain_check.py", ["--chain", chain_bad,
                                   "--review", FIXTURES / "review_items.json",
                                   "--entries", entries_json])
    rep = parse_json_out(p)
    check("坏链退出码 1", p.returncode == 1, "rc=%d %s" % (p.returncode, p.stderr[:200]))
    check("恰好 1 个缺 basis 环节", bool(rep) and count(rep, "STEP_BASIS_MISSING") == 1,
          "n=%d" % (count(rep, "STEP_BASIS_MISSING") if rep else -1))
    check("作者判断环（step 3）已登记复核，不报错",
          bool(rep) and count(rep, "AUTHOR_JUDGMENT_NOT_IN_REVIEW") == 0
          and rep.get("author_judgment_steps") == [3])
    check("evidence.quote 逐字回查通过（无 EVIDENCE_QUOTE_NOT_FOUND）",
          bool(rep) and count(rep, "EVIDENCE_QUOTE_NOT_FOUND") == 0)
    check("链尾指向本文（无 LAST_STEP_NOT_THIS_WORK）",
          bool(rep) and count(rep, "LAST_STEP_NOT_THIS_WORK") == 0)
    check("坏链报告 ok=false（存在 error）", bool(rep) and rep.get("ok") is False)

    # 4b. 作者判断环未登记时必须报错（反向验证）
    print("[4b] 反向验证：作者判断环未登记复核时报 AUTHOR_JUDGMENT_NOT_IN_REVIEW")
    chain_noreview = Path(tmpdir) / "gap_chain_noreview.json"
    with open(FIXTURES / "gap_chain.json", encoding="utf-8") as f:
        chain_obj = json.load(f)
    for s in chain_obj["gap_chain"]:
        if s.get("step") == 2:
            s["basis"] = "补上的依据"
    with open(chain_noreview, "w", encoding="utf-8") as f:
        json.dump(chain_obj, f, ensure_ascii=False)
    p = run("gap_chain_check.py", ["--chain", chain_noreview])
    rep = parse_json_out(p)
    check("未提供 review 时告警 REVIEW_ITEMS_NOT_PROVIDED",
          bool(rep) and count(rep, "REVIEW_ITEMS_NOT_PROVIDED") >= 1)
    check("STEP_BASIS_MISSING 清零", bool(rep) and count(rep, "STEP_BASIS_MISSING") == 0)

    # 4c. 缺 basis 且文献环无证据同时报（多缺陷可见性）
    print("[4c] 反向验证：链尾未指向本文时报 LAST_STEP_NOT_THIS_WORK")
    chain_badtail = Path(tmpdir) / "gap_chain_badtail.json"
    chain_obj["gap_chain"][-1]["basis"] = "该方向值得进一步研究"
    chain_obj["gap_chain"][-1].pop("kind", None)
    with open(chain_badtail, "w", encoding="utf-8") as f:
        json.dump(chain_obj, f, ensure_ascii=False)
    p = run("gap_chain_check.py", ["--chain", chain_badtail, "--review", FIXTURES / "review_items.json"])
    rep = parse_json_out(p)
    check("报 LAST_STEP_NOT_THIS_WORK", bool(rep) and count(rep, "LAST_STEP_NOT_THIS_WORK") == 1)

    # ---------- 5. write_matrix：groups → CSV ----------
    print("\n[5] write_matrix 导出比较矩阵 CSV")
    p = run("write_matrix.py", ["--groups", FIXTURES / "groups.json", "--output", matrix_csv,
                                "--entries", entries_json])
    rep = parse_json_out(p)
    check("write_matrix 退出码 0", p.returncode == 0, p.stderr[:300])
    check("导出 5 行 × 3 组", bool(rep) and rep.get("rows") == 5 and rep.get("groups") == 3)
    with open(matrix_csv, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    check("CSV 行数 = 1 表头 + 5 条目", len(rows) == 6, "rows=%d" % len(rows))
    check("CSV 表头列序正确", rows and rows[0][:3] == ["group", "group_basis", "ref"],
          "header=%r" % (rows[0] if rows else None))
    check("CSV 含单篇组与三列内容", any("图拓扑方法" in r[0] and r[6] for r in rows[1:]))
    check("单篇组缺失三列时告警机制可用（本夹具三列齐全 → 无 INCOMPLETE_ROW）",
          bool(rep) and all(w.get("code") != "INCOMPLETE_ROW" for w in rep.get("warnings", [])))

    # ---------- 汇总 ----------
    print("\n===== 自测汇总 =====")
    print("通过 %d 项；失败 %d 项" % (passed, len(failures)))
    for f in failures:
        print("  FAIL: %s" % f)
    if args.keep:
        print("临时目录已保留：%s" % tmpdir)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
