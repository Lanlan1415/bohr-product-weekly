#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py —— 五脚本流水线的第 2 环：锚定核验 + 违规编辑自动回退。

输入 prepare.py 的产出（original_snapshot.md、sentences.tsv）与 Agent 分批产出
的句级编辑记录 edits.jsonl，逐条核验并应用，产出核验后的润色稿与机读报告。

锚定协议（最高优先级，来自冠军复盘的最贵教训）：
- 每条编辑记录必须先**逐字抄原句**（"original" 字段）再写改文（"replacement"）；
- original 与 sentences.tsv 中该 sentence_id 的当前文本做空白云容比对，
  不一致即拒绝该条（锚定失败），不得"大概对上"就改；
- 兼容 id-only 记录（只有 sentence_id、没有 original）：可应用，但记 WARN
  "无法锚定核对"——宽容路径，不整案失败；
- 同一句的链式多轮修改：后续记录的 original 应对照上一轮改后文本。

守恒门（句级，逐条执行；违规编辑**自动回退**——该句保持原文，不是只报告）：
1. 数字与单位 token 多重集合一致；2. 引用标记一致；3. 图表/公式编号一致；
4. LaTeX 公式段逐字一致；5. 限定词计数不得变化（加强或削弱都算违规）；
6. 否定词计数不得变化（否定范围不得改动）。
唯一例外：记录显式带 "allow_conservation_break": true 且给出 "reason"，
此时接受但在报告中标记"有意例外"，必须能在 change_log 找到对应依据。

产出（全部写入 --workdir）：
- polished_verified.md  核验后的润色稿（对原文做最小侵入替换，其余逐字保留）
- verify_result.json    机读结果（accepted/rejected/warnings，供 finalize 摘要）
- verify_report.md      人读报告
- rejected_edits.jsonl  被回退的编辑及原因（Agent 据此修正后重投）

用法：
    python3 /skills/weekly-skill/scripts/verify.py --workdir /app/work \
        --edits /app/work/edits.jsonl [--terms /app/work/terms.txt]

退出码：0 = 核验完成（含部分编辑被回退）；1 = 输入缺失/不可读（此时
finalize.py 会走宽容路径：交付原文 + skipped_reason）。
退出码仅表示存在建议修复项；无论退出码如何，都应照常 finalize 交付
result.json 并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
stdlib-only；utf-8-sig；不依赖 CWD；不联网。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

RE_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?:\s*[eE][+-]?\d+)?%?")
RE_CITE = re.compile(r"\[(?:[Ss]?\d+)(?:\s*[-–,]\s*[Ss]?\d+)*\]")
RE_FIGTAB = re.compile(
    r"(?i)\b(?:fig(?:ure)?s?|tables?|eq(?:uation)?s?)\.?\s*\(?\s*\d{1,3}[a-z]?\s*\)?"
    r"|[图表式]\s*\(?\s*\d{1,3}\s*\)?")
RE_FORMULA = [
    re.compile(r"\\begin\{(?:equation|align|gather|multline|eqnarray)s?\*?\}.+?"
               r"\\end\{(?:equation|align|gather|multline|eqnarray)s?\*?\}", re.DOTALL),
    re.compile(r"\$\$.+?\$\$", re.DOTALL),
    re.compile(r"\\\(.+?\\\)", re.DOTALL),
    re.compile(r"\\\[.+?\\\]", re.DOTALL),
    re.compile(r"(?<!\$)\$(?!\$)[^$\n]+?\$(?!\$)"),
]
RE_CITE_COMMAND = re.compile(
    r"\\(?:cite\w*|ref|eqref|autoref)\s*(?:\[[^\]]*\]\s*)?\{[^{}]+\}")

HEDGES_EN = ["may", "might", "could", "suggest", "suggests", "suggested",
             "indicate", "indicates", "indicated", "approximately", "likely",
             "possibly", "potentially", "appears", "appear", "seem", "seems",
             "roughly", "about"]
HEDGES_ZH = ["可能", "大约", "约", "或许", "一定程度上", "有望", "似乎", "大致"]
NEG_EN = ["not", "no", "never", "neither", "without", "hardly", "scarcely"]
NEG_ZH = ["不", "无", "未", "没有", "并非", "无法", "毫不", "难以"]

# The seven classes are ported from the locally preserved 78.67-point baseline.
# Compare class membership, not merely total hedge counts: may might is legal,
# whereas show -> prove and some -> all change the author's claim.
HEDGE_PHRASES = [
    ("at least", "restrict"), ("at most", "restrict"), ("up to", "restrict"),
    ("no more than", "restrict"), ("no less than", "restrict"),
    ("no longer", "negative"), ("in general", "weaken"), ("as a whole", "universal"),
    ("一般来说", "weaken"), ("一般而言", "weaken"), ("总的来说", "weaken"),
    ("总体而言", "weaken"), ("大体上", "weaken"),
    ("在某些情况下", "weaken"), ("在大多数情况下", "weaken"),
]
HEDGE_WORDS = {
    "weaken": ["may", "might", "could", "possibly", "perhaps", "maybe",
               "appears", "appear", "seems", "seem", "seemingly", "apparently",
               "tentatively", "arguably", "somewhat", "potential", "potentially",
               "可能", "或许", "也许", "大概", "似乎", "恐怕", "大致"],
    "boost_strong": ["strongly", "highly", "clearly", "significantly",
                     "substantially", "markedly", "dramatically", "considerably",
                     "extremely", "undoubtedly", "definitely", "certainly",
                     "will", "shall", "must", "prove", "proves", "proved", "proven",
                     "demonstrate", "demonstrates", "demonstrated", "confirm",
                     "confirms", "confirmed", "establish", "establishes", "established",
                     "显著", "明显", "强烈", "极其", "无疑", "必然", "显然",
                     "大幅", "必定", "证明", "证实", "确证"],
    "boost_mild": ["very", "quite", "rather", "fairly", "notably", "relatively",
                   "widely", "largely", "mostly", "generally", "partially", "partly",
                   "非常", "十分", "相当", "基本上", "总体上", "大体", "较为"],
    "report": ["suggest", "suggests", "suggested", "indicate", "indicates",
               "indicated", "show", "shows", "showed", "shown", "reveal", "reveals",
               "revealed", "imply", "implies", "implied", "support", "supports",
               "supported", "report", "reports", "reported", "find", "finds", "found",
               "表明", "显示", "暗示", "提示", "反映", "认为", "指出", "发现", "说明"],
    "restrict": ["only", "merely", "solely", "just", "simply", "exclusively",
                 "limited", "confined", "restricted", "approximately", "about",
                 "roughly", "around", "at least", "at most",
                 "仅", "只", "仅仅", "只不过", "限于", "至多", "至少", "最多",
                 "不超过", "唯有", "约", "大约"],
    "universal": ["all", "every", "each", "none", "everything", "everyone",
                  "entirely", "completely", "fully", "both",
                  "全部", "所有", "每个", "一切", "完全"],
    "negative": ["not", "no", "never", "cannot", "can't", "won't", "don't",
                 "without", "unlikely", "lack", "lacks", "lacked", "fail", "fails",
                 "failed", "neither", "nor", "不", "未", "无", "没有", "并非",
                 "无法", "不会", "不再", "缺乏", "尚未"],
}
TIME_WORDS = [
    "currently", "presently", "now", "then", "previously", "formerly", "recently",
    "already", "yet", "before", "after", "afterwards", "subsequently", "meanwhile",
    "during", "until", "since", "today", "yesterday", "tomorrow",
    "目前", "当前", "此前", "以前", "之前", "之后", "随后", "近年来", "当时",
    "曾经", "已经", "仍然", "至今", "同时", "期间",
]
CAUSAL_WORDS = {
    "causal": ["cause", "causes", "caused", "causing", "lead to", "leads to",
               "led to", "result in", "results in", "resulted in", "drive", "drives",
               "determine", "determines", "导致", "致使", "驱动", "决定"],
    "associative": ["associate", "associated", "correlate", "correlated", "linked",
                    "link", "相关", "关联", "联系"],
}
UNIT_WORDS = [
    "percentage points", "percent", "degrees Celsius", "degC", "°C", "℃", "°F",
    "μm", "µm", "nm", "mm", "cm", "km", "mL", "ml", "μL", "µL", "L",
    "ms", "μs", "µs", "ns", "min", "hr", "hours", "hour", "days", "day", "years",
    "year", "kg", "mg", "μg", "µg", "ng", "g", "s", "m", "h", "Hz", "kHz",
    "MHz", "GHz", "bp", "kb", "Mb", "Gb", "kDa", "Da", "mol", "mM", "μM",
    "µM", "M", "Pa", "kPa", "MPa", "GPa", "J", "kJ", "MJ", "V", "mV",
    "kV", "A", "mA", "W", "kW", "MW", "eV", "keV", "MeV", "GeV", "ppm",
    "ppb", "dB", "fold", "times", "S/cm", "mS/cm", "个", "名", "例", "人",
    "组", "份", "篇", "种", "项", "类", "条", "次", "倍", "年", "月", "天",
    "日", "时", "分", "秒", "毫秒", "微米", "纳米", "毫米", "厘米", "米",
]
UNIT_WORDS = sorted(set(UNIT_WORDS), key=lambda u: (-len(u), u.casefold(), u))


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def ws_norm(s):
    """空白宽容归一：压缩全部空白run为单空格。锚定比对专用。"""
    return " ".join((s or "").split())


def extract_formulas(text):
    found, occupied = [], []
    for pat in RE_FORMULA:
        for m in pat.finditer(text):
            span = m.span()
            if any(s <= span[0] < e or s < span[1] <= e for s, e in occupied):
                continue
            occupied.append(span)
            found.append(" ".join(m.group(0).split()))
    return Counter(found)


def count_words(text, words, zh=False):
    c = 0
    if zh:
        for w in words:
            c += text.count(w)
    else:
        for w in words:
            c += len(re.findall(r"(?i)\b%s\b" % re.escape(w), text))
    return c


def norm_counter(tokens, strip_commas=False, casefold=False):
    c = Counter()
    for t in tokens:
        if strip_commas:
            t = t.replace(",", "")
        if casefold:
            t = " ".join(t.casefold().split()).replace(" ", "")
        c[t] += 1
    return c


def _phrase_counter(text, phrases):
    out = Counter()
    for phrase in phrases:
        if phrase.isascii():
            hits = re.findall(r"(?i)(?<![A-Za-z'])" + re.escape(phrase) +
                              r"(?![A-Za-z])", text)
            out[phrase.casefold()] += len(hits)
        else:
            out[phrase] += text.count(phrase)
    return +out


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def hedge_counter(text):
    """Return {claim-strength class: multiset of protected expressions}."""
    occupied, found = [], Counter()
    for phrase, cls in HEDGE_PHRASES:
        for m in re.finditer(re.escape(phrase), text, re.I if phrase.isascii() else 0):
            if any(_overlap(m.span(), s) for s in occupied):
                continue
            occupied.append(m.span())
            found[(cls, m.group(0).casefold())] += 1
    for cls, words in HEDGE_WORDS.items():
        for phrase in sorted(set(words), key=len, reverse=True):
            for m in re.finditer(re.escape(phrase), text, re.I if phrase.isascii() else 0):
                if any(_overlap(m.span(), s) for s in occupied):
                    continue
                if phrase.isascii():
                    left = text[m.start() - 1] if m.start() else ""
                    right = text[m.end()] if m.end() < len(text) else ""
                    if (left and (left.isalpha() or left == "'")) or \
                            (right and right.isalpha()):
                        continue
                occupied.append(m.span())
                found[(cls, m.group(0).casefold())] += 1
    by_class = {}
    for (cls, token), count in found.items():
        by_class.setdefault(cls, Counter())[token] += count
    return by_class


def unit_counter(text):
    """Capture the unit attached to each numeric token without guessing units."""
    found = Counter()
    for m in RE_NUMBER.finditer(text):
        end = m.end()
        suffix = text[end:end + 32]
        leading = re.match(r"\s*", suffix).group(0)
        rest = suffix[len(leading):]
        unit = ""
        for candidate in UNIT_WORDS:
            if rest.startswith(candidate):  # unit case is scientific meaning: mM != mm
                after = rest[len(candidate):]
                if candidate.isascii() and candidate[-1].isalpha() and \
                        after[:1].isalpha():
                    continue
                unit = candidate
                break
        if unit:
            canonical = {"degc": "°C", "degrees celsius": "°C", "℃": "°C",
                         "µm": "μm", "µl": "μL", "µs": "μs",
                         "µg": "μg"}.get(unit.casefold(), unit)
            found[canonical] += 1
        else:
            found["<unitless>"] += 1
    return found


def citation_counter(text):
    numeric = [t.replace(" ", "") for t in RE_CITE.findall(text)]
    commands = [" ".join(t.split()) for t in RE_CITE_COMMAND.findall(text)]
    return Counter(numeric + commands)


def protected_elements(old, new, terms=()):
    """Exact before/after evidence for every protected class (reference pattern)."""
    old_h, new_h = hedge_counter(old), hedge_counter(new)
    classes = sorted(set(old_h) | set(new_h))
    return {
        "numbers": _change_record(RE_NUMBER.findall(old), RE_NUMBER.findall(new)),
        "units": _change_record(sorted(unit_counter(old).elements()),
                                sorted(unit_counter(new).elements())),
        "citations": _change_record(sorted(citation_counter(old).elements()),
                                    sorted(citation_counter(new).elements())),
        "figure_table_equation_refs": _change_record(RE_FIGTAB.findall(old),
                                                     RE_FIGTAB.findall(new)),
        "formulas": _change_record(sorted(extract_formulas(old).elements()),
                                   sorted(extract_formulas(new).elements())),
        "temporal_markers": _change_record(sorted(_phrase_counter(old, TIME_WORDS).elements()),
                                           sorted(_phrase_counter(new, TIME_WORDS).elements())),
        "hedges_by_class": {
            cls: _change_record(sorted(old_h.get(cls, Counter()).elements()),
                                sorted(new_h.get(cls, Counter()).elements()))
            for cls in classes
        },
        "approved_terms": {
            term: _change_record([term] * old.count(term), [term] * new.count(term))
            for term in terms
        },
    }


def _change_record(before, after):
    before, after = list(before), list(after)
    return {"before": before, "after": after,
            "status": "Same" if before == after else "Changed"}


def conservation_violations(old, new, terms):
    """句级守恒检查，返回违规说明列表（空 = 通过）。"""
    bad = []
    old_nc, new_nc = RE_CITE.sub(" ", old), RE_CITE.sub(" ", new)
    if norm_counter(RE_NUMBER.findall(old_nc), True) != \
            norm_counter(RE_NUMBER.findall(new_nc), True):
        bad.append("数字不一致")
    if unit_counter(old_nc) != unit_counter(new_nc):
        bad.append("数字/单位不一致")
    if citation_counter(old) != citation_counter(new):
        bad.append("引用标记不一致")
    if norm_counter(RE_FIGTAB.findall(old), casefold=True) != \
            norm_counter(RE_FIGTAB.findall(new), casefold=True):
        bad.append("图表/公式编号不一致")
    if extract_formulas(old) != extract_formulas(new):
        bad.append("数学环境（LaTeX 公式）被改动")
    old_h, new_h = hedge_counter(old), hedge_counter(new)
    for cls in sorted(set(old_h) | set(new_h)):
        old_n = sum(old_h.get(cls, Counter()).values())
        new_n = sum(new_h.get(cls, Counter()).values())
        if old_n != new_n:
            bad.append("限定词强度变化：%s %d→%d" % (cls, old_n, new_n))
    for name, words, zh in (("否定词(英)", NEG_EN, False),
                            ("否定词(中)", NEG_ZH, True)):
        co, cn = count_words(old, words, zh), count_words(new, words, zh)
        if co != cn:
            bad.append("否定范围变化：%s %d→%d" % (name, co, cn))
    if _phrase_counter(old, TIME_WORDS) != _phrase_counter(new, TIME_WORDS):
        bad.append("时间语义标记变化（时态/时间指向须人工核对）")
    for cls, words in CAUSAL_WORDS.items():
        if sum(_phrase_counter(old, words).values()) != \
                sum(_phrase_counter(new, words).values()):
            bad.append("因果/相关关系变化：%s" % cls)
    for t in terms:
        co, cn = old.count(t), new.count(t)
        if cn < co:
            bad.append("批准术语 %r 在句内减少（%d→%d）：术语链断裂" % (t, co, cn))
    return bad


def load_sentences(path):
    table = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if i == 0 and line.startswith("sentence_id\t"):
                continue
            if not line.strip() or "\t" not in line:
                continue
            sid, sent = line.split("\t", 1)
            table[sid.strip()] = sent
    return table


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="锚定核验 + 守恒门 + 违规编辑自动回退")
    parser.add_argument("--workdir", required=True, help="工作目录（prepare 产出所在）")
    parser.add_argument("--edits", required=True, help="编辑记录 edits.jsonl")
    parser.add_argument("--terms", default=None,
                        help="术语表（默认 <workdir>/terms.txt，存在即启用）")
    args = parser.parse_args(argv)

    workdir = os.path.abspath(args.workdir)
    snap_path = os.path.join(workdir, "original_snapshot.md")
    sent_path = os.path.join(workdir, "sentences.tsv")
    for p, tag in ((snap_path, "original_snapshot.md"), (sent_path, "sentences.tsv")):
        if not os.path.isfile(p):
            print("[FAIL] 缺少 %s（%s）——请先运行 prepare.py" % (tag, p))
            return 1
    if not os.path.isfile(os.path.abspath(args.edits)):
        print("[FAIL] 编辑记录不存在：%s" % args.edits)
        return 1

    original = read_text(snap_path)
    sentences = load_sentences(sent_path)
    current = dict(sentences)  # sentence_id -> 当前文本（随接受的编辑更新）

    terms_path = args.terms or os.path.join(workdir, "terms.txt")
    terms = []
    if os.path.isfile(os.path.abspath(terms_path)):
        for ln in read_text(os.path.abspath(terms_path)).splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                terms.append(ln)

    accepted, rejected, warnings = [], [], []
    unchanged, confirmations = [], []
    polished = original

    with open(os.path.abspath(args.edits), "r", encoding="utf-8-sig") as f:
        raw_lines = [ln for ln in f if ln.strip()]

    for lineno, ln in enumerate(raw_lines, 1):
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError as exc:
            rejected.append({"edit_id": "line-%d" % lineno, "sentence_id": "",
                             "reason": "JSON 解析失败：%s" % exc, "reverted": True})
            continue
        if not isinstance(rec, dict):
            rejected.append({"edit_id": "line-%d" % lineno, "sentence_id": "",
                             "reason": "编辑记录不是 JSON object，未应用", "reverted": True})
            continue
        eid = str(rec.get("edit_id") or "line-%d" % lineno)
        sid = str(rec.get("sentence_id") or "")
        rep = rec.get("replacement")
        intentional = bool(rec.get("allow_conservation_break")) and rec.get("reason")

        def reject(reason):
            rejected.append({"edit_id": eid, "sentence_id": sid,
                             "reason": reason, "reverted": True})

        if sid not in current:
            reject("sentence_id 不存在：%r（对照 sentences.tsv）" % sid)
            continue
        if not isinstance(rep, str) or not rep.strip():
            reject("replacement 为空：删句属内容改动，润色不允许；"
                   "如确需删节请走【备选】机制请作者定夺")
            continue

        old = current[sid]
        # ---- 锚定协议 ----
        if "original" in rec and rec.get("original") is not None:
            rec_orig = str(rec.get("original"))
            if ws_norm(rec_orig) == ws_norm(old):
                pass  # 锚定成功（对当前文本）
            elif ws_norm(rec_orig) == ws_norm(sentences[sid]):
                # 抄的是最初原句，但该句已被前序编辑改过：链式记录错位
                reject("锚定到原始句但该句已被前序编辑改变：链式修改时 "
                       "后续记录必须抄上一轮改后文本")
                continue
            else:
                reject("锚定失败：original 与 %s 的当前文本不符"
                       "（空白宽容比对）；必须先逐字抄原句再写改文" % sid)
                continue
        else:
            warnings.append("%s：id-only 记录（无 original 字段），无法锚定核对，"
                            "仅按 sentence_id 定位——建议补齐原句抄录" % eid)

        # Ambiguous alternatives are candidates, never a new manuscript baseline.
        alternative = rec.get("alternative") if isinstance(rec.get("alternative"), dict) else {}
        ambiguity = rec.get("ambiguity") or rec.get("uncertainty") or alternative.get("issue")
        confirmed = rec.get("author_confirmation") in (
            True, "true", "yes", "approved", "confirmed", "作者已确认", "已确认")
        if alternative.get("proposed") or (ambiguity and not confirmed):
            options = rec.get("alternatives") or alternative.get("options") or [rep, old]
            confirmations.append({
                "edit_id": eid, "sentence_id": sid, "before": old,
                "candidates": options, "recommended_candidate": rep,
                "reason": str(rec.get("reason") or ""),
                "ambiguity": ambiguity or "alternative marked as proposed",
                "author_confirmation": None,
                "resolution": "kept_original_pending_author_confirmation",
                "protected_elements": protected_elements(old, old, terms),
            })
            continue

        # A no-op is an unchanged observation, not a fabricated polishing change.
        if rep == old:
            unchanged.append({
                "edit_id": eid, "sentence_id": sid,
                "level": str(rec.get("level") or ""),
                "type": str(rec.get("type") or "keep_original"),
                "before": old, "after": rep,
                "reason": str(rec.get("reason") or "原句保留；本条不构成编辑"),
                "ambiguity": ambiguity,
                "author_confirmation": rec.get("author_confirmation"),
                "protected_elements": protected_elements(old, rep, terms),
            })
            continue
        if not str(rec.get("reason") or "").strip():
            reject("修改理由缺失：实际文字变化不会计入润色稿")
            continue

        # ---- 守恒门 ----
        violations = conservation_violations(old, rep, terms)
        if violations:
            if intentional:
                warnings.append("%s：有意守恒例外（%s）——依据：%s；"
                                "请在 change_log 保留该依据"
                                % (eid, "；".join(violations), rec.get("reason")))
            else:
                reject("守恒门违规，已自动回退：%s" % "；".join(violations))
                continue

        # ---- 应用：对全文做最小侵入替换 ----
        if polished.count(old) > 1:
            warnings.append("%s：原句在文中出现 %d 处，已替换第一处；"
                            "如目标位置不同请用更长上下文锚定"
                            % (eid, polished.count(old)))
        if old not in polished:
            reject("内部错误：当前句文本在润色稿中定位失败（疑似前序编辑破坏），"
                   "已回退")
            continue
        polished = polished.replace(old, rep, 1)
        current[sid] = rep
        accepted.append({"edit_id": eid, "sentence_id": sid,
                         "level": str(rec.get("level") or ""),
                         "type": str(rec.get("type") or ""),
                         "before": old, "after": rep,
                         "reason": str(rec.get("reason") or ""),
                         "ambiguity": ambiguity,
                         "author_confirmation": rec.get("author_confirmation"),
                         "protected_elements": protected_elements(old, rep, terms),
                         "intentional_exception": bool(intentional)})

    # ---- 落盘 ----
    write_text(os.path.join(workdir, "polished_verified.md"), polished)
    rej_path = os.path.join(workdir, "rejected_edits.jsonl")
    write_text(rej_path, "".join(json.dumps(r, ensure_ascii=False) + "\n"
                                 for r in rejected))
    result = {"sentences_total": len(sentences),
              "edits_total": len(raw_lines),
              "accepted": accepted, "unchanged": unchanged,
              "confirmations": confirmations, "rejected": rejected,
              "warnings": warnings}
    write_text(os.path.join(workdir, "verify_result.json"),
               json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    rep_lines = ["# verify 核验报告", "",
                 "- 编辑记录 %d 条：接受 %d / 保持原文 %d / 待作者确认 %d / 回退 %d；警告 %d 条"
                 % (len(raw_lines), len(accepted), len(unchanged), len(confirmations),
                    len(rejected), len(warnings)),
                 "- 产出：polished_verified.md（违规句与未确认备选保持原文）", "",
                 "## 回退清单（须修正后重投或放弃）", ""]
    for r in rejected:
        rep_lines.append("- %s（%s）：%s"
                         % (r["edit_id"], r["sentence_id"] or "?", r["reason"]))
    if not rejected:
        rep_lines.append("- 无")
    rep_lines += ["", "## 警告", ""]
    for w in warnings:
        rep_lines.append("- %s" % w)
    if not warnings:
        rep_lines.append("- 无")
    write_text(os.path.join(workdir, "verify_report.md"),
               "\n".join(rep_lines) + "\n")

    print("=" * 60)
    print("verify：锚定核验 + 守恒门（违规自动回退）")
    print("=" * 60)
    print("[INFO] 编辑 %d 条：接受 %d / 保持原文 %d / 待确认 %d / 回退 %d / 警告 %d"
          % (len(raw_lines), len(accepted), len(unchanged), len(confirmations),
             len(rejected), len(warnings)))
    for r in rejected:
        print("[REVERT] %s：%s" % (r["edit_id"], r["reason"]))
    for w in warnings:
        print("[WARN] %s" % w)
    print("[OK] polished_verified.md / verify_result.json / verify_report.md 已写入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
