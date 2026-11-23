#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""param_check.py — 参数抽取与冲突检测（写作09｜方法与实验章节写作）。

从材料（config/log/yaml/json/笔记等文本）与成稿（.md/.tex/.txt）中抽取
"键=值"形态的参数对，按键名归一化后交叉比对：

1. 冲突（FAIL）：同一参数在多处出现但数值不一致，或数值一致但单位不一致
   （如 config 里 lr=1e-3、日志里 lr=0.01；300 K vs 300 °C）。
2. 无来源（WARN，--strict 时 FAIL）：成稿中出现的参数在材料中查无出处——
   可能是为段落顺畅编造的数值。
3. 覆盖提示（INFO）：材料中有而成稿未引用的参数（供要素齐全性参考）。

YAML 感知（v2）：`.yaml/.yml` 材料中的锚点与别名按 YAML 语义处理——
`key: &anchor 0.01` 正常取值并登记锚点；`key: *alias` 解析为锚点值（注明经别名）；
`key: ~` / `key: null` 视为"声明未赋值"（INFO，不取值、不算冲突）；
合并键 `<<: *anchor` 记录为提示、不报语法错误。以上均不会产生误报冲突。

用法：
    python3 /skills/weekly-skill/scripts/param_check.py \
        --materials /input [--materials /path/more ...] \
        --draft /app/output/methods_section.md [--draft more.md ...] \
        --report /app/work/param_check_report.md [--strict]

退出码：0 = 无 FAIL 级发现；1 = 存在 FAIL（或运行错误）。
规则：stdlib-only；utf-8-sig 读文件；只读输入；不依赖网络与 CWD；
路径输出用正斜杠。
"""

import argparse
import os
import re
import sys

# 键名归一化别名表：归一化后的别名 -> 规范名
ALIASES = {
    "learningrate": "learning_rate", "lr": "learning_rate", "学习率": "learning_rate",
    "batchsize": "batch_size", "批大小": "batch_size", "批次大小": "batch_size",
    "batch": "batch_size",
    "epochs": "epochs", "epoch": "epochs", "numepochs": "epochs",
    "训练轮数": "epochs", "轮数": "epochs", "迭代轮数": "epochs",
    "seed": "seed", "randomseed": "seed", "随机种子": "seed",
    "temperature": "temperature", "温度": "temperature", "temp": "temperature",
    "weightdecay": "weight_decay", "权重衰减": "weight_decay",
    "dropout": "dropout", "dropoutrate": "dropout",
    "optimizer": "optimizer", "优化器": "optimizer",
    "momentum": "momentum", "动量": "momentum",
    "testsize": "test_size", "测试集比例": "test_size",
    "trainingsplit": "train_split", "划分比例": "split_ratio", "split": "split_ratio",
}

# 配置形态：key = value / key: value（yaml/json/ini/log 常见）
RE_CONFIG = re.compile(
    r"^\s*[\"']?(?P<key>[A-Za-z_][\w\.\-]{0,40}|[一-鿿][一-鿿A-Za-z0-9_\-]{0,20})"
    r"[\"']?\s*[:=]\s*[\"']?(?P<val>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>[A-Za-zμ°%/][\wμ°%/\^\-\.]{0,10})?[\"']?\s*[,}]?\s*(?:#.*)?$")

# 散文形态（中英）：<名> 为/设为/取/= <数><单位>
RE_PROSE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_\- ]{1,30}|[一-鿿]{2,12})"
    r"\s*(?:设为|设置为|取为|取|为|是|of|to|=|:)\s*"
    r"(?P<val>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>K|°C|℃|GB|GiB|MB|MiB|ms|s|ms/step|Hz|%|epoch[s]?|steps?)?"
    r"(?![\d])")

TEXT_EXTS = {".txt", ".md", ".tex", ".yaml", ".yml", ".json", ".cfg", ".ini",
             ".toml", ".log", ".csv", ".tsv", ".py", ".sh", ".bib", ".xml"}

YAML_EXTS = {".yaml", ".yml"}

# YAML 锚点值：key: &anchor <值> ；YAML 别名引用：key: *alias ；YAML 空值：key: ~ / null
RE_YAML_ANCHOR = re.compile(
    r"^\s*[\"']?(?P<key>[A-Za-z_][\w\.\-]{0,40})[\"']?\s*:\s*"
    r"&(?P<anchor>[A-Za-z0-9_\-]+)\s+(?P<rest>.*)$")
RE_YAML_ALIAS = re.compile(
    r"^\s*[\"']?(?P<key>[A-Za-z_][\w\.\-]{0,40})[\"']?\s*:\s*"
    r"\*(?P<alias>[A-Za-z0-9_\-]+)\s*(?:#.*)?$")
RE_YAML_NULL = re.compile(
    r"^\s*[\"']?(?P<key>[A-Za-z_][\w\.\-]{0,40})[\"']?\s*:\s*"
    r"(?:~|null)\s*(?:#.*)?$", re.IGNORECASE)
RE_YAML_MERGE = re.compile(r"^\s*<<:\s*\*(?P<alias>[A-Za-z0-9_\-]+)")

VALUE_TOL = 1e-9  # 相对容差，判定两个浮点数是否相等


def norm_key(raw):
    """键名归一化：去空白/下划线/连字符、小写，再查别名表。

    v2：查不到时做后缀匹配——散文形态常带前缀（"本次采用学习率""最终的lr"），
    若归一化键以某个长度 ≥2 的别名结尾，按该别名归一化；这正是"把被覆盖旧值
    写成'本次采用'时仍能拦下冲突"的拦截依据。
    """
    k = re.sub(r"[\s_\-]+", "", raw.strip()).lower()
    if k in ALIASES:
        return ALIASES[k]
    for alias in sorted(ALIASES, key=len, reverse=True):
        if len(alias) >= 2 and len(k) > len(alias) and k.endswith(alias):
            return ALIASES[alias]
    return raw.strip().lower().replace(" ", "_")


def norm_unit(u):
    if not u:
        return ""
    u = u.strip()
    table = {"℃": "°C", "celsius": "°C", "gib": "GB", "mib": "MB",
             "epochs": "epoch", "steps": "step"}
    return table.get(u.lower(), u)


def parse_value(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def extract_from_file(path, role):
    """从单个文本文件抽取参数出现点。role ∈ {materials, draft}。

    返回 (occ, yaml_notes)。yaml_notes 为 YAML 锚点/别名/空值处理记录（INFO）。
    """
    occ = []  # dict(key, value, unit, file, line, role)
    yaml_notes = []
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
    except OSError as exc:
        print("警告：无法读取 %s（%s）" % (path, exc), file=sys.stderr)
        return occ, yaml_notes
    fname = os.path.basename(path)
    is_yaml = os.path.splitext(fname)[1].lower() in YAML_EXTS
    anchors = {}  # anchor 名 -> (value, unit)
    for ln, line in enumerate(lines, 1):
        if len(line) > 2000:
            continue
        m = RE_CONFIG.match(line)
        if m and m.group("val"):
            v = parse_value(m.group("val"))
            if v is not None:
                occ.append(dict(key=norm_key(m.group("key")), value=v,
                                unit=norm_unit(m.group("unit")),
                                file=fname, line=ln, role=role,
                                raw_key=m.group("key").strip()))
            continue
        if is_yaml:
            # key: &anchor <值> —— 剥掉锚点标记后按配置形态取值
            ma = RE_YAML_ANCHOR.match(line)
            if ma:
                stripped = "%s: %s" % (ma.group("key"), ma.group("rest"))
                mv = RE_CONFIG.match(stripped)
                if mv and mv.group("val"):
                    v = parse_value(mv.group("val"))
                    if v is not None:
                        anchors[ma.group("anchor")] = (v, norm_unit(mv.group("unit")))
                        occ.append(dict(key=norm_key(ma.group("key")), value=v,
                                        unit=norm_unit(mv.group("unit")),
                                        file=fname, line=ln, role=role,
                                        raw_key=ma.group("key").strip()))
                        yaml_notes.append(
                            "%s:L%d 锚点 &%s 取值 %s（键 %s，已正常取值）"
                            % (fname, ln, ma.group("anchor"),
                               fmt_val(v), ma.group("key").strip()))
                else:
                    yaml_notes.append(
                        "%s:L%d 锚点 &%s 为非数值/嵌套值（键 %s），跳过取值，不报错"
                        % (fname, ln, ma.group("anchor"), ma.group("key").strip()))
                continue
            # key: *alias —— 解析为已登记锚点的值
            mal = RE_YAML_ALIAS.match(line)
            if mal:
                tgt = anchors.get(mal.group("alias"))
                if tgt:
                    occ.append(dict(key=norm_key(mal.group("key")), value=tgt[0],
                                    unit=tgt[1], file=fname, line=ln, role=role,
                                    raw_key=mal.group("key").strip()))
                    yaml_notes.append(
                        "%s:L%d 别名 *%s 解析为 %s（键 %s，经别名取值）"
                        % (fname, ln, mal.group("alias"), fmt_val(tgt[0]),
                           mal.group("key").strip()))
                else:
                    yaml_notes.append(
                        "%s:L%d 别名 *%s 的锚点未见数值定义（键 %s），跳过，不报错"
                        % (fname, ln, mal.group("alias"), mal.group("key").strip()))
                continue
            # key: ~ / null —— 声明未赋值，INFO 记录，不取值不算冲突
            mn = RE_YAML_NULL.match(line)
            if mn:
                yaml_notes.append(
                    "%s:L%d 键 %s 为空值（~/null，声明未赋值），不计入冲突"
                    % (fname, ln, mn.group("key").strip()))
                continue
            # 合并键 <<: *anchor —— 记录提示，不报错
            mm = RE_YAML_MERGE.match(line)
            if mm:
                yaml_notes.append(
                    "%s:L%d 合并键 <<: *%s（嵌套合并），其标量值按各自行正常取值"
                    % (fname, ln, mm.group("alias")))
                continue
        for m in RE_PROSE.finditer(line):
            v = parse_value(m.group("val"))
            if v is None:
                continue
            occ.append(dict(key=norm_key(m.group("key")), value=v,
                            unit=norm_unit(m.group("unit")),
                            file=fname, line=ln, role=role,
                            raw_key=m.group("key").strip()))
    return occ, yaml_notes


def iter_text_files(paths):
    """展开目录/文件参数为文本文件列表（只读遍历）。"""
    out = []
    for p in paths:
        ap = os.path.abspath(p)
        if os.path.isdir(ap):
            for root, dirs, files in os.walk(ap):
                dirs.sort()
                for name in sorted(files):
                    if os.path.splitext(name)[1].lower() in TEXT_EXTS:
                        out.append(os.path.join(root, name))
        elif os.path.isfile(ap):
            out.append(ap)
        else:
            print("警告：路径不存在，已跳过：%s" % p, file=sys.stderr)
    return out


def same_value(a, b):
    if a == 0 or b == 0:
        return abs(a - b) < 1e-12
    return abs(a - b) / max(abs(a), abs(b)) < VALUE_TOL


def fmt_val(v):
    return ("%g" % v)


def analyze(occ):
    """返回 (conflicts, unsourced, uncovered)。occ 为全部出现点。"""
    by_key = {}
    for o in occ:
        by_key.setdefault(o["key"], []).append(o)

    conflicts = []
    unsourced = []
    for key, items in sorted(by_key.items()):
        # 取值分组（数值+单位联合判等）
        groups = []
        for o in items:
            placed = False
            for g in groups:
                gu = g["unit"]
                units_compat = (not gu or not o["unit"] or gu == o["unit"])
                if units_compat and same_value(g["value"], o["value"]):
                    if not gu and o["unit"]:
                        g["unit"] = o["unit"]
                    g["items"].append(o)
                    placed = True
                    break
            if not placed:
                groups.append(dict(value=o["value"], unit=o["unit"], items=[o]))
        if len(groups) > 1:
            conflicts.append((key, groups))
        mats = [o for o in items if o["role"] == "materials"]
        drafts = [o for o in items if o["role"] == "draft"]
        if drafts and not mats:
            unsourced.append((key, drafts))
    # 覆盖提示：材料有、成稿无（仅信息级）
    uncovered = [(k, [o for o in v if o["role"] == "materials"])
                 for k, v in sorted(by_key.items())
                 if any(o["role"] == "materials" for o in v)
                 and not any(o["role"] == "draft" for o in v)]
    return conflicts, unsourced, uncovered


def loc(o):
    return "%s:L%d" % (o["file"], o["line"])


def render_report(occ, conflicts, unsourced, uncovered, strict, yaml_notes=None):
    lines = []
    lines.append("# 参数抽取与冲突检测报告")
    lines.append("")
    n_mat = len({o["file"] for o in occ if o["role"] == "materials"})
    n_drf = len({o["file"] for o in occ if o["role"] == "draft"})
    lines.append("材料来源：%d 个文件；成稿：%d 个文件；抽取参数出现点 %d 处，归并参数 %d 个。"
                 % (n_mat, n_drf, len(occ), len({o['key'] for o in occ})))
    lines.append("")
    lines.append("## 1. 取值冲突（%d 项，FAIL）" % len(conflicts))
    if not conflicts:
        lines.append("- 无")
    for key, groups in conflicts:
        lines.append("- **%s** 存在 %d 种取值：" % (key, len(groups)))
        for g in groups:
            srcs = "; ".join("%s:%s" % (o["role"], loc(o)) for o in g["items"])
            unit = (" " + g["unit"]) if g["unit"] else ""
            lines.append("  - `%g%s` ← %s" % (g["value"], unit, srcs))
    lines.append("")
    level = "FAIL" if strict else "WARN"
    lines.append("## 2. 成稿无来源参数（%d 项，%s）" % (len(unsourced), level))
    if not unsourced:
        lines.append("- 无")
    for key, items in unsourced:
        lines.append("- **%s**：出现于 %s；材料中无此参数，疑似编造或遗漏来源，"
                     "须删除、补来源或标 [待确认]。"
                     % (key, "; ".join(loc(o) for o in items)))
    lines.append("")
    lines.append("## 3. 材料有而成稿未引用的参数（%d 项，INFO）" % len(uncovered))
    if not uncovered:
        lines.append("- 无")
    for key, items in uncovered:
        lines.append("- `%s` ← %s" % (key, "; ".join(loc(o) for o in items[:5])))
    lines.append("")
    yaml_notes = yaml_notes or []
    lines.append("## 4. YAML 锚点/别名/空值处理（%d 项，INFO）" % len(yaml_notes))
    if not yaml_notes:
        lines.append("- 无")
    for note in yaml_notes:
        lines.append("- %s" % note)
    lines.append("")
    lines.append("> 处置规则：冲突不得擅自二选一——查日志实际加载值/实验记录定位最终取值，"
                 "判不了就在正文与 evidence_map 双处标 [待确认]（见 references/method_rules.md §4）。")
    return "\n".join(lines) + "\n"


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="参数抽取与冲突检测：材料与成稿交叉比对 键=值 参数（stdlib-only）。")
    parser.add_argument("--materials", action="append", required=True,
                        help="材料目录或文件，可重复（只读）")
    parser.add_argument("--draft", action="append", default=[],
                        help="成稿文件，可重复；缺省时只查材料内部冲突")
    parser.add_argument("--report", required=True, help="报告输出路径（.md）")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：成稿无来源参数也计 FAIL")
    args = parser.parse_args(argv)

    mat_files = iter_text_files(args.materials)
    drf_files = [f for f in iter_text_files(args.draft)]
    if not mat_files:
        print("错误：未找到任何材料文本文件。", file=sys.stderr)
        return 1

    occ = []
    yaml_notes = []
    for f in mat_files:
        o, n = extract_from_file(f, "materials")
        occ.extend(o)
        yaml_notes.extend(n)
    for f in drf_files:
        o, n = extract_from_file(f, "draft")
        occ.extend(o)
        yaml_notes.extend(n)

    conflicts, unsourced, uncovered = analyze(occ)

    report = render_report(occ, conflicts, unsourced, uncovered, args.strict,
                           yaml_notes)
    out_path = os.path.abspath(args.report)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
    except OSError as exc:
        print("错误：无法写出报告：%s" % exc, file=sys.stderr)
        return 1

    # 控制台摘要
    print("参数抽取与冲突检测：出现点 %d 处，归并参数 %d 个"
          % (len(occ), len({o['key'] for o in occ})))
    for key, groups in conflicts:
        vals = " / ".join("%g%s" % (g["value"], g["unit"] or "") for g in groups)
        print("[FAIL] 参数冲突：%s（%s）" % (key, vals))
    lvl = "FAIL" if args.strict else "WARN"
    for key, items in unsourced:
        print("[%s] 成稿参数无材料来源：%s（%s）"
              % (lvl, key, "; ".join(loc(o) for o in items)))
    fails = len(conflicts) + (len(unsourced) if args.strict else 0)
    print("结果：%s（%d 个 FAIL，%d 个 WARN，%d 个 INFO）退出码 %d -> %s"
          % ("未通过" if fails else "通过", fails,
             0 if args.strict else len(unsourced),
             len(uncovered) + len(yaml_notes),
             1 if fails else 0, out_path.replace(os.sep, "/")))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
