#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self_test.py —— 图谱脚本群端到端自测（全合成 fixture，含负路径）。

覆盖（每条断言打印 PASS/FAIL）：
正路径：
  K01 合法图（含 condition 列的比较边）graph_check 通过（退出码 0）；
  K02 GraphML 导出+回导一致（退出码 0）；
  K03 合法 result 草稿 contract_check 通过；
  K04 合法交付目录 selfcheck 通过；
负路径（必须被拒绝/判 FAIL）：
  K05 悬空边必须 FAIL；K06 别名撞车（重复实体）必须 FAIL；
  K07 无证据边必须 FAIL；K08 表外关系必须 FAIL；
  K09 比较边缺 condition（表有该列）必须 FAIL（比较-条件门）；
  K10 缩写候选指向多个节点必须 FAIL；
  K11 GraphML 被篡改后 --verify-only 必须 FAIL；
  K12 result 草稿缺契约字段必须 FAIL；
  K13 交付目录 case_id 不符必须 FAIL；
宽容路径：
  K14 比较边存在但整表无 condition 列 → 只 WARN，退出码 0；
  K15 缩写候选未落点 → 只 WARN，退出码 0。

用法：python3 /skills/weekly-skill/scripts/self_test.py [--keep <dir>]
退出码：0 = 全部断言通过；1 = 存在失败。stdlib-only；不依赖 CWD；
fixture 在临时目录自建自毁。
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile

NODES_CSV = """node_id,label,type,aliases
N001,Li7La3Zr2O12,Material,LLZO;锂镧锆氧
N002,LATP,Material,Li1.3Al0.3Ti1.7(PO4)3
N003,溶胶-凝胶法,Method,sol-gel
N004,离子电导率,Metric,
"""

EDGES_GOOD = """edge_id,subject,predicate,object,source_id,paragraph_id,quote,evidence_strength,value,unit,condition
E001,N003,prepares,N001,S1,sec2-p3,采用溶胶-凝胶法制备了 Li7La3Zr2O12,direct,,,
E002,N001,has_metric,N004,S1,sec3-p1,离子电导率为 3.2e-4 S/cm,direct,3.2e-4,S/cm,25 °C
E003,N001,more_stable_than,N002,S2,sec4-p2,LLZO 对锂金属更稳定,direct,,,对锂金属界面
"""

ABBREVS_CSV = """abbr,full_form,source_id,paragraph_id
LLZO,Li7La3Zr2O12,S1,sec1-p2
"""

CASE_JSON = {"case_id": "kg-selftest-synthetic",
             "output_contract": {"graph_summary": "...", "graph_files": "...",
                                 "queries": "..."}}


def load_mod(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="图谱脚本群端到端自测（全合成）")
    parser.add_argument("--keep", default=None)
    args = parser.parse_args(argv)

    graph_check = load_mod("graph_check.py")
    roundtrip = load_mod("graphml_roundtrip.py")
    contract = load_mod("contract_check.py")
    selfcheck = load_mod("selfcheck.py")

    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok)))
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                             (" —— " + detail) if detail else ""))

    root = args.keep or tempfile.mkdtemp(prefix="kg_selftest_")
    nodes = os.path.join(root, "graph_nodes.csv")
    edges = os.path.join(root, "graph_edges.csv")
    abbrevs = os.path.join(root, "abbrev_candidates.csv")
    gml = os.path.join(root, "graph.graphml")
    case_p = os.path.join(root, "case.json")
    write(nodes, NODES_CSV)
    write(edges, EDGES_GOOD)
    write(abbrevs, ABBREVS_CSV)
    write(case_p, json.dumps(CASE_JSON, ensure_ascii=False))
    pred = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "references", "predicates.txt")

    def gc(edge_text=EDGES_GOOD, ab=None, extra=None):
        write(edges, edge_text)
        a = ["--edges", edges, "--nodes", nodes, "--predicates", pred]
        if ab:
            a += ["--abbrevs", ab]
        if extra:
            a += extra
        return graph_check.main(a)

    # ---- K01 正路径 ----
    check("K01 合法图 graph_check 通过", gc(ab=abbrevs) == 0)

    # ---- K05-K10 负路径：graph_check 逐项拦截 ----
    bad_dangle = EDGES_GOOD + "E009,N001,uses,N999,S1,sec1-p1,使用某物,direct,,,\n"
    check("K05 悬空边必须 FAIL", gc(bad_dangle) == 1)
    bad_alias_nodes = NODES_CSV + "N005,llzo,Material,\n"
    write(nodes, bad_alias_nodes)
    check("K06 别名撞车（重复实体）必须 FAIL", gc() == 1)
    write(nodes, NODES_CSV)
    bad_ev = EDGES_GOOD + "E009,N001,uses,N003,S1,,,direct,,,\n"
    check("K07 无证据边必须 FAIL", gc(bad_ev) == 1)
    bad_pred = EDGES_GOOD + "E009,N001,enhances,N002,S1,sec1-p1,增强了性能,direct,,,\n"
    check("K08 表外关系必须 FAIL", gc(bad_pred) == 1)
    bad_cond = EDGES_GOOD.replace("对锂金属界面\n", "\n")
    check("K09 比较边缺 condition 必须 FAIL（比较-条件门）", gc(bad_cond) == 1)
    # 缩写冲突：另建一个别名同样命中 LLZO 的节点
    conflict_nodes = NODES_CSV + "N005,某电解质,Material,LLZO\n"
    write(nodes, conflict_nodes)
    check("K10 缩写候选指向多个节点必须 FAIL", gc(ab=abbrevs) == 1)
    write(nodes, NODES_CSV)

    # ---- K14/K15 宽容路径：只 WARN 不 FAIL ----
    nocond = ("edge_id,subject,predicate,object,source_id,paragraph_id,quote,"
              "evidence_strength\n"
              "E003,N001,more_stable_than,N002,S2,sec4-p2,LLZO 对锂金属更稳定,direct\n")
    check("K14 无 condition 列的比较边只 WARN（退出码 0）", gc(nocond) == 0)
    unknown_abbr = os.path.join(root, "abbr_unknown.csv")
    write(unknown_abbr, "abbr,full_form,source_id,paragraph_id\n"
                        "XYZ,X y z 材料,S9,sec1-p1\n")
    check("K15 缩写候选未落点只 WARN（退出码 0）", gc(ab=unknown_abbr) == 0)

    # ---- K02/K11 GraphML ----
    write(edges, EDGES_GOOD)
    check("K02 GraphML 导出+回导一致",
          roundtrip.main(["--nodes", nodes, "--edges", edges,
                          "--graphml", gml]) == 0)
    with open(gml, "r", encoding="utf-8") as f:
        tampered = f.read().replace("溶胶-凝胶法", "篡改-凝胶法")
    write(gml, tampered)
    check("K11 GraphML 被篡改后 --verify-only 必须 FAIL",
          roundtrip.main(["--nodes", nodes, "--edges", edges,
                          "--graphml", gml, "--verify-only"]) == 1)

    # ---- K03/K12 contract_check ----
    draft_good = {"case_id": "kg-selftest-synthetic", "graph_summary": "g.md",
                  "graph_files": ["a.csv"], "queries": [], "status": "partial"}
    draft_p = os.path.join(root, "result_draft.json")
    write(draft_p, json.dumps(draft_good, ensure_ascii=False))
    check("K03 合法草稿 contract_check 通过",
          contract.main(["--case", case_p, "--result", draft_p]) == 0)
    draft_bad = {"case_id": "kg-selftest-synthetic", "graph_summary": "g.md"}
    write(draft_p, json.dumps(draft_bad, ensure_ascii=False))
    check("K12 缺契约字段的草稿必须 FAIL",
          contract.main(["--case", case_p, "--result", draft_p]) == 1)

    # ---- K04/K13 selfcheck ----
    outdir = os.path.join(root, "output")
    os.makedirs(outdir, exist_ok=True)
    write(os.path.join(outdir, "graph_edges.csv"), EDGES_GOOD)
    write(os.path.join(outdir, "graph_nodes.csv"), NODES_CSV)
    write(os.path.join(outdir, "graph_summary.md"),
          "# 摘要\n\n## 查询演示\n\n### 查询1：A\n### 查询2：B\n### 查询3：C\n"
          "证据 [S1 §sec2-p3]\n")
    write(os.path.join(outdir, "result.json"),
          json.dumps({"case_id": "kg-selftest-synthetic",
                      "graph_summary": "graph_summary.md",
                      "graph_files": ["graph_nodes.csv", "graph_edges.csv"],
                      "queries": [1, 2, 3], "status": "success",
                      "sources": ["S1"], "uncertainty": [],
                      "change_log": ["x"]}, ensure_ascii=False))
    check("K04 合法交付目录 selfcheck 通过",
          selfcheck.main(["--output", outdir, "--case", case_p]) == 0)
    write(os.path.join(outdir, "result.json"),
          json.dumps({"case_id": "WRONG", "status": "success"},
                     ensure_ascii=False))
    check("K13 case_id 不符必须 FAIL",
          selfcheck.main(["--output", outdir, "--case", case_p]) == 1)

    fails = [r for r in results if not r[1]]
    print("=" * 60)
    print("self_test：%d 项断言，%d 通过，%d 失败"
          % (len(results), len(results) - len(fails), len(fails)))
    if args.keep:
        print("fixture 保留在：%s" % root)
    else:
        shutil.rmtree(root, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
