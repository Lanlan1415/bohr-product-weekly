#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self_test.py —— 五脚本流水线的端到端自测（全合成 fixture，含负路径）。

覆盖（每条断言打印 PASS/FAIL）：
正路径：
  T01 中文+英文+LaTeX 混合稿 prepare→verify→finalize→audit 全通，退出码全 0；
  T02 接受的编辑确实落入 polished_text.md；
负路径（必须被拒绝并回退——该句保持原文，拒绝原因入报告）：
  T03 数字篡改（3.2e-4→3.4e-4）必须回退；
  T04 限定词加强（may→demonstrates）必须回退；
  T05 引用删除（[2,3] 被删）必须回退；
  T06 数学环境改动（kT→2kT）必须回退；
  T07 否定移除（not significant→significant / 去掉"不"）必须回退；
  T08 锚定失败（original 与原句不符）必须拒绝；
宽容路径：
  T09 id-only 记录（无 original）被接受但记 WARN；
  T10 有意守恒例外（allow_conservation_break+reason）被接受并标记；
  T11 verify 缺失时 finalize 交付原文 + skipped_reason，status=partial，退出码 0；
  T12 契约字段无法产出时 finalize 置 null + uncertainty，不删字段；
可靠性：
  T13 事后篡改检测：finalize 后改动交付物，audit 必须 FAIL；
  T14 重复运行一致性：finalize 连跑两次，_manifest.json 哈希完全一致。

用法：python3 /skills/weekly-skill/scripts/self_test.py [--keep /tmp/dir]
退出码：0 = 全部断言通过；1 = 存在失败断言。stdlib-only；不联网；
不依赖 CWD；所有 fixture 在临时目录内自建自毁（--keep 可保留查看）。
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile

# ---------------- 合成 fixture（全部为演示而虚构） ----------------

CASE_JSON = {
    "case_id": "polish-selftest-synthetic",
    "provided_notes": {"owner": "case author", "revision": 3},
    "output_contract": {
        "polished_text": "润色后全文",
        "change_log": "逐条修改记录",
        "provided_notes": "必须逐字直通的案例值",
        "unproducible_field": "故意放一个无法自动产出的字段，测试 T12",
    },
}

ORIGINAL = (
    "The Li7La3Zr2O12 (LLZO) solid electrolyte have attracted much attention [1]. "
    "The ionic conductivity was measured at 25 degC and reaches 3.2e-4 S/cm, "
    "which is higher than LATP (1.1e-4 S/cm) [2,3].\n"
    "As shown in Figure 1, the data do not significantly change with temperature, "
    "fitted by $\\sigma T = A \\exp(-E_a/kT)$.\n"
    "These results suggest that LLZO may be a promising candidate.\n"
    "结果表明，该材料在室温下不可能发生明显的相变。\n"
)

# 每条：(edit_id, sentence 关键词定位用, original, replacement, 期望)
def _edits_for(sent):
    """按 prepare 实际切分结果生成编辑记录（sent = {id: text}）。"""
    by_key = {}
    for sid, text in sent.items():
        by_key.setdefault(text, sid)
    ids = list(sent)
    s1, s2, s3, s4, s5 = ids[0], ids[1], ids[2], ids[3], ids[4]
    good = [
        # T01/T02：合法 L1 修改（主谓一致），不改任何守恒对象
        {"edit_id": "C001", "sentence_id": s1, "level": "L1",
         "original": sent[s1],
         "replacement": sent[s1].replace("have attracted", "has attracted"),
         "type": "主谓一致", "reason": "主语单数"},
        # T09：id-only 合法修改（时态），无 original 字段 → 接受 + WARN
        {"edit_id": "C002", "sentence_id": s2, "level": "L1",
         "replacement": sent[s2].replace("reaches", "reached"),
         "type": "时态一致", "reason": "实验叙述过去时"},
        # T10：有意例外——作者书面确认该句可直陈（去掉 may）；
        # 句级守恒会判违规，凭 allow_conservation_break+reason 放行并标记；
        # 整文档级 conservation_check 对限定词只 WARN，不阻塞交付。
        {"edit_id": "C003", "sentence_id": s4, "level": "L3",
         "original": sent[s4],
         "replacement": sent[s4].replace("may be a promising",
                                         "is a promising"),
         "type": "限定词调整", "reason": "作者书面确认该句证据充分、可直陈",
         "allow_conservation_break": True},
    ]
    negative = [
        # T03 数字篡改
        {"edit_id": "N01", "sentence_id": s2, "level": "L1",
         "original": sent[s2],
         "replacement": sent[s2].replace("3.2e-4", "3.4e-4"),
         "type": "伪造", "reason": "负路径测试：数字篡改"},
        # T04 限定词加强
        {"edit_id": "N02", "sentence_id": s4, "level": "L3",
         "original": sent[s4],
         "replacement": sent[s4].replace("may be", "is"),
         "type": "伪造", "reason": "负路径测试：限定词加强"},
        # T05 引用删除
        {"edit_id": "N03", "sentence_id": s2, "level": "L1",
         "original": sent[s2],
         "replacement": sent[s2].replace(" [2,3]", ""),
         "type": "伪造", "reason": "负路径测试：引用删除"},
        # T06 数学环境改动
        {"edit_id": "N04", "sentence_id": s3, "level": "L1",
         "original": sent[s3],
         "replacement": sent[s3].replace("kT", "2kT"),
         "type": "伪造", "reason": "负路径测试：公式篡改"},
        # T07a 否定移除（英）
        {"edit_id": "N05", "sentence_id": s3, "level": "L1",
         "original": sent[s3],
         "replacement": sent[s3].replace("do not significantly", "significantly"),
         "type": "伪造", "reason": "负路径测试：否定移除（英）"},
        # T07b 否定移除（中）
        {"edit_id": "N06", "sentence_id": s5, "level": "L1",
         "original": sent[s5],
         "replacement": sent[s5].replace("不可能", "可能"),
         "type": "伪造", "reason": "负路径测试：否定移除（中）"},
        # T08 锚定失败（original 与原句不符）
        {"edit_id": "N07", "sentence_id": s1, "level": "L1",
         "original": "This is a completely different sentence that was never said.",
         "replacement": sent[s1], "type": "伪造",
         "reason": "负路径测试：锚定失败"},
    ]
    return good, negative


def load_mod(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="五脚本流水线端到端自测（全合成）")
    parser.add_argument("--keep", default=None, help="保留 fixture 目录以便查看")
    args = parser.parse_args(argv)

    prepare = load_mod("prepare.py")
    verify = load_mod("verify.py")
    finalize = load_mod("finalize.py")
    audit = load_mod("audit.py")

    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                             (" —— " + detail) if detail else ""))

    root = args.keep or tempfile.mkdtemp(prefix="polish_selftest_")
    workdir = os.path.join(root, "work")
    outdir = os.path.join(root, "output")
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    case_path = os.path.join(root, "case.json")
    text_path = os.path.join(root, "manuscript.md")
    with open(case_path, "w", encoding="utf-8") as f:
        json.dump(CASE_JSON, f, ensure_ascii=False)
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(ORIGINAL)

    # ---- prepare ----
    rc = prepare.main(["--text", text_path, "--workdir", workdir,
                       "--case", case_path])
    check("T00 prepare 退出码 0", rc == 0)
    sentences = verify.load_sentences(os.path.join(workdir, "sentences.tsv"))
    check("T00b 切分出 5 个句单元（4 句英文+1 句中文）",
          len(sentences) == 5, "实际 %d" % len(sentences))

    # ---- verify：负路径记录先投（锚定原始句），合法编辑后投 ----
    good, negative = _edits_for(sentences)
    edits_path = os.path.join(workdir, "edits" + ".jsonl")
    with open(edits_path, "w", encoding="utf-8") as f:
        for rec in negative + good:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    rc = verify.main(["--workdir", workdir, "--edits", edits_path])
    vr = json.loads(read_text(os.path.join(workdir, "verify_result.json")))
    acc_ids = {a["edit_id"] for a in vr["accepted"]}
    rej = {r["edit_id"]: r["reason"] for r in vr["rejected"]}
    check("T01 verify 退出码 0", rc == 0)
    check("T02 合法编辑被接受（C001/C002/C003）",
          {"C001", "C002", "C003"} <= acc_ids, "接受集：%s" % sorted(acc_ids))
    check("T03 数字篡改必须回退", "N01" in rej and "数字" in rej.get("N01", ""),
          rej.get("N01", "未被拒绝！"))
    check("T04 限定词加强必须回退", "N02" in rej and "限定词" in rej.get("N02", ""),
          rej.get("N02", "未被拒绝！"))
    check("T05 引用删除必须回退", "N03" in rej and "引用" in rej.get("N03", ""),
          rej.get("N03", "未被拒绝！"))
    check("T06 数学环境改动必须回退", "N04" in rej and "数学" in rej.get("N04", ""),
          rej.get("N04", "未被拒绝！"))
    check("T07a 否定移除（英）必须回退", "N05" in rej and "否定" in rej.get("N05", ""),
          rej.get("N05", "未被拒绝！"))
    check("T07b 否定移除（中）必须回退", "N06" in rej and "否定" in rej.get("N06", ""),
          rej.get("N06", "未被拒绝！"))
    check("T08 锚定失败必须拒绝", "N07" in rej and "锚定" in rej.get("N07", ""),
          rej.get("N07", "未被拒绝！"))
    check("T09 id-only 记录接受且记 WARN",
          "C002" in acc_ids and any("id-only" in w for w in vr["warnings"]))
    check("T10 有意例外接受且标记",
          "C003" in acc_ids and any("有意守恒例外" in w for w in vr["warnings"]))

    polished = read_text(os.path.join(workdir, "polished_verified.md"))
    check("T02b 接受的编辑落入润色稿", "has attracted" in polished)
    check("T03b 被回退的篡改未落入润色稿（无 3.4e-4）",
          "3.4e-4" not in polished and "3.2e-4" in polished)
    check("T05b 被回退句保持原文（[2,3] 未被删）", "[2,3]" in polished)
    check("T07c 中文否定保留（不可能）", "不可能" in polished)
    check("T10b 有意例外的编辑已应用（may 被作者确认移除）",
          "results suggest that LLZO is a promising" in polished)

    # ---- finalize ----
    rc = finalize.main(["--workdir", workdir, "--output", outdir,
                        "--case", case_path])
    check("T01b finalize 退出码 0", rc == 0)
    result = json.loads(read_text(os.path.join(outdir, "result.json")))
    check("T12 无法产出的契约字段被置 null 且未删字段",
          "unproducible_field" in result and result["unproducible_field"] is None
          and any("unproducible_field" in u for u in result["uncertainty"]))
    check("T12b 可产出的契约字段已填",
          result.get("polished_text") == "polished_text.md")
    check("T12c case 同名值逐字直通且字段清单完整",
          result.get("provided_notes") == CASE_JSON["provided_notes"]
          and set(result.get("output_contract_fields") or []) == set(CASE_JSON["output_contract"]))
    check("T02c 修改理由与保护元素 before/after 可审计",
          all(s.get("reason") and s.get("protected_elements") for s in result["before_after_digest"]["samples"])
          and any("protected_elements" in s for s in result["before_after_digest"]["samples"]))
    check("T01c before_after_digest 存在且计数正确",
          result["before_after_digest"]["accepted"] == 3
          and result["before_after_digest"]["rejected"] == 7)
    check("T01d 改后回读通道 pass",
          result["quality_gate"].get("readback") == "pass")
    check("T01e 有回退时 status=partial（诚实）",
          result["status"] == "partial")

    # ---- audit ----
    rc = audit.main(["--output", outdir, "--case", case_path,
                     "--workdir", workdir])
    check("T01f audit 退出码 0（干净交付）", rc == 0)

    # ---- T13 事后篡改检测 ----
    p_out = os.path.join(outdir, "polished_text.md")
    with open(p_out, "a", encoding="utf-8") as f:
        f.write("tampered sentence.\n")
    rc = audit.main(["--output", outdir, "--case", case_path,
                     "--workdir", workdir])
    check("T13 事后篡改必须被 audit 检出（退出码 1）", rc == 1)
    # 恢复：重跑 finalize 覆盖交付物
    finalize.main(["--workdir", workdir, "--output", outdir, "--case", case_path])

    # ---- T14 重复运行一致性 ----
    finalize.main(["--workdir", workdir, "--output", outdir, "--case", case_path])
    man1 = read_text(os.path.join(outdir, "_manifest.json"))
    finalize.main(["--workdir", workdir, "--output", outdir, "--case", case_path])
    man2 = read_text(os.path.join(outdir, "_manifest.json"))
    check("T14 重复运行 finalize 产物哈希一致", man1 == man2)

    # ---- T11 宽容路径：verify 缺失 ----
    root2 = tempfile.mkdtemp(prefix="polish_selftest_bare_")
    work2, out2 = os.path.join(root2, "work"), os.path.join(root2, "output")
    os.makedirs(work2)
    prepare.main(["--text", text_path, "--workdir", work2, "--case", case_path])
    rc = finalize.main(["--workdir", work2, "--output", out2,
                        "--case", case_path])
    r2 = json.loads(read_text(os.path.join(out2, "result.json")))
    bare = read_text(os.path.join(out2, "polished_text.md"))
    check("T11 verify 缺失时 finalize 仍导出（退出码 0）", rc == 0)
    check("T11b 交付原文 + skipped_reason + status=partial",
          bare == ORIGINAL and r2.get("skipped_reason")
          and r2["status"] == "partial")
    if not args.keep:
        shutil.rmtree(root2, ignore_errors=True)

    # ---- T15/T16：好句不被无意义“润色”；歧义备选须确认且不落稿 ----
    root3 = tempfile.mkdtemp(prefix="polish_selftest_noop_")
    work3, out3 = os.path.join(root3, "work"), os.path.join(root3, "output")
    os.makedirs(work3)
    prepare.main(["--text", text_path, "--workdir", work3, "--case", case_path])
    sent3 = verify.load_sentences(os.path.join(work3, "sentences.tsv"))
    sid3 = next(iter(sent3))
    noop_path = os.path.join(work3, "edits" + ".jsonl")
    with open(noop_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"edit_id": "KEEP01", "sentence_id": sid3,
                            "original": sent3[sid3], "replacement": sent3[sid3],
                            "type": "keep_original", "reason": "No error; retain author wording"},
                           ensure_ascii=False) + "\n")
    verify.main(["--workdir", work3, "--edits", noop_path])
    with open(os.path.join(work3, "change_log.md"), "w", encoding="utf-8") as f:
        f.write("# 合成修改记录\n")
    with open(os.path.join(work3, "evidence_map.md"), "w", encoding="utf-8") as f:
        f.write("# 合成来源映射\n")
    finalize.main(["--workdir", work3, "--output", out3, "--case", case_path])
    noop_vr = json.loads(read_text(os.path.join(work3, "verify_result.json")))
    noop_result = json.loads(read_text(os.path.join(out3, "result.json")))
    check("T15 no-op 原句逐字不变且不计为润色修改",
          read_text(os.path.join(out3, "polished_text.md")) == ORIGINAL
          and not noop_vr["accepted"] and len(noop_vr["unchanged"]) == 1
          and noop_result["before_after_digest"]["accepted"] == 0)
    check("T15b 只有 no-op 时交付可为 success，而非制造修改",
          noop_result["status"] == "success")

    pending_rec = {"edit_id": "AMB01", "sentence_id": sid3, "original": sent3[sid3],
                   "replacement": "An unsupported fluent rewrite.",
                   "type": "register", "reason": "Meaning depends on author intent",
                   "ambiguity": "whether 'significant' is statistical or rhetorical",
                   "alternative": {"proposed": True,
                                   "options": [sent3[sid3], "An unsupported fluent rewrite."]}}
    with open(noop_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(pending_rec, ensure_ascii=False) + "\n")
    verify.main(["--workdir", work3, "--edits", noop_path])
    finalize.main(["--workdir", work3, "--output", out3, "--case", case_path])
    pending_vr = json.loads(read_text(os.path.join(work3, "verify_result.json")))
    pending_result = json.loads(read_text(os.path.join(out3, "result.json")))
    check("T16 歧义候选不落地，列作者确认与 before/candidates/reason",
          read_text(os.path.join(out3, "polished_text.md")) == ORIGINAL
          and not pending_vr["accepted"] and len(pending_vr["confirmations"]) == 1
          and pending_vr["confirmations"][0]["author_confirmation"] is None
          and pending_result["status"] == "partial")

    # ---- T17：敌意守恒与非 object 记录全部结构化回退 ----
    root4 = tempfile.mkdtemp(prefix="polish_selftest_hostile_")
    work4 = os.path.join(root4, "work")
    os.makedirs(work4)
    prepare.main(["--text", text_path, "--workdir", work4, "--case", case_path])
    sent4 = verify.load_sentences(os.path.join(work4, "sentences.tsv"))
    ids4 = list(sent4)
    hostile = [
        {"edit_id": "UNIT", "sentence_id": ids4[1], "original": sent4[ids4[1]],
         "replacement": sent4[ids4[1]].replace("S/cm", "mS/cm"), "reason": "hostile unit change"},
        {"edit_id": "TIME", "sentence_id": ids4[1], "original": sent4[ids4[1]],
         "replacement": "Currently, " + sent4[ids4[1]], "reason": "hostile temporal insertion"},
        {"edit_id": "CITECMD", "sentence_id": ids4[0], "original": sent4[ids4[0]],
         "replacement": sent4[ids4[0]] + " \\cite{new2026}", "reason": "hostile citation insertion"},
        {"edit_id": "CAUSE", "sentence_id": ids4[3], "original": sent4[ids4[3]],
         "replacement": sent4[ids4[3]].replace("suggest", "prove"), "reason": "hostile causal strengthening"},
    ]
    hostile_path = os.path.join(work4, "edits" + ".jsonl")
    with open(hostile_path, "w", encoding="utf-8") as f:
        for rec in hostile:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.write("42\n")
    verify.main(["--workdir", work4, "--edits", hostile_path])
    hostile_vr = json.loads(read_text(os.path.join(work4, "verify_result.json")))
    hostile_rej = {r["edit_id"]: r["reason"] for r in hostile_vr["rejected"]}
    check("T17 单位篡改回退", "UNIT" in hostile_rej and "单位" in hostile_rej["UNIT"])
    check("T17b 时间指向新增回退", "TIME" in hostile_rej and "时间" in hostile_rej["TIME"])
    check("T17c LaTeX 引用新增回退", "CITECMD" in hostile_rej and "引用" in hostile_rej["CITECMD"])
    check("T17d 因果/断言加强回退", "CAUSE" in hostile_rej)
    check("T17e 非 object JSON 记录不崩溃且全文未改",
          "line-5" in hostile_rej and not hostile_vr["accepted"]
          and read_text(os.path.join(work4, "polished_verified.md")) == ORIGINAL)
    if not args.keep:
        shutil.rmtree(root3, ignore_errors=True)
        shutil.rmtree(root4, ignore_errors=True)

    # ---- 汇总 ----
    fails = [r for r in results if not r[1]]
    print("=" * 60)
    print("self_test：%d 项断言，%d 通过，%d 失败"
          % (len(results), len(results) - len(fails), len(fails)))
    if args.keep:
        print("fixture 保留在：%s" % root)
    elif os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
