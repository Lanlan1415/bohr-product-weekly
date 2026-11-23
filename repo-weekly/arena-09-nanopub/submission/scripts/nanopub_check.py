# -*- coding: utf-8 -*-
"""nanopub_check.py — Nanopublication / RDF 结构与语法校验（阅读14 专用）

仅用 Python 标准库实现的 Turtle / TriG 基本语法与 nanopub 结构检查：

  语法层（所有 .ttl/.trig 文件）：
    S1 词法完整：字符串、IRI（<...>）无未闭合；IRI 内不含空白；
    S2 括号配平：( ) [ ] { } 成对（字符串与注释除外）；
    S3 前缀闭合：所有 prefix:local 形式的前缀均已用 @prefix/PREFIX 声明；
       裸 :local 要求声明空前缀（@prefix : <...>）；
    S4 句点结尾：顶层语句与每个图块内容以 . 结束，不允许 } 前残留 ; 或 ,。

  结构层（声明了 nanopub 命名空间或为 .trig 文件时）：
    N1 三部结构谓词齐全：np:hasAssertion / np:hasProvenance /
       np:hasPublicationInfo（np 为任意映射到 nanopub.org/nschema# 的前缀，
       也接受完整 IRI 写法）；
    N2 四个命名图齐全：Head / assertion / provenance / pubInfo（按图块标签
       的本地名判定，不区分大小写）；
    N3 assertion 图非空：至少包含一条以 . 结束的三元组。

  v2 可选增强检查（全部仅 WARN，不把 v1 能通过的稿件判 FAIL——
  校验器校准纪律）：
    N4 provenance 图建议含 wasDerivedFrom 与 hasEvidenceAnchor；
    N5 pubInfo 图建议含 confidence 置信度标注；
    N6 建议标注 ex:conditionScope（条件范围）与 ex:evidenceForm
       （证据形式：实验数据/计算结果/引用支持/作者声明）。

用法：
    python nanopub_check.py <file.trig|file.ttl> [更多文件...]
    python nanopub_check.py --dir <目录>

退出码：0 全部通过（允许 WARN）；1 任一文件存在 FAIL；2 参数错误。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
只读被检查文件；读文件一律 utf-8-sig；不依赖网络与 CWD。
"""
import argparse
import os
import re
import sys

NP_NS = "nanopub.org/nschema#"
NP_PREDICATES = ["hasAssertion", "hasProvenance", "hasPublicationInfo"]
REQUIRED_GRAPHS = ["head", "assertion", "provenance", "pubinfo"]


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def scan(text):
    """词法扫描：剥离注释，登记字符串/IRI 区间，检查未闭合与配平。

    返回 (masked, errors)：masked 为字符串与 IRI 内容被空格替换后的文本
    （保留外层引号与尖括号，长度不变），errors 为 [(行号, 说明)]。
    """
    chars = list(text)
    errors = []
    stack = []  # (括号, 行号)
    i, line = 0, 1
    n = len(chars)
    while i < n:
        c = chars[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c == "#":  # 注释到行尾（masked 中抹除，避免注释里的符号误触发）
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        if c == "<":  # IRI
            start_line = line
            j = i + 1
            bad_ws = False
            while j < n and chars[j] != ">":
                if chars[j] == "\n":
                    errors.append((start_line, "IRI 跨行未闭合"))
                    break
                if chars[j] in " \t":
                    bad_ws = True
                j += 1
            if j >= n or chars[j] != ">":
                if not any(e[0] == start_line and "IRI" in e[1] for e in errors):
                    errors.append((start_line, "IRI 未闭合（缺少 >）"))
                i = j
                continue
            if bad_ws:
                errors.append((start_line, "IRI 内含空白字符"))
            for k in range(i + 1, j):
                chars[k] = " "
            i = j + 1
            continue
        if text.startswith('"""', i) or text.startswith("'''", i):  # 长字符串
            q = text[i:i + 3]
            start_line = line
            j = i + 3
            while j < n and not text.startswith(q, j):
                if chars[j] == "\\":
                    j += 1
                j += 1
            if j >= n:
                errors.append((start_line, "长字符串未闭合（缺少 %s）" % q))
                j = n
            body = text[i:j + 3]
            line += body.count("\n")
            for k in range(i + 1, min(j + 2, n)):
                if chars[k] != "\n":
                    chars[k] = " "
            i = j + 3
            continue
        if c in "\"'":  # 单行字符串
            start_line = line
            j = i + 1
            while j < n and chars[j] != c and chars[j] != "\n":
                if chars[j] == "\\":
                    j += 1
                j += 1
            if j >= n or chars[j] != c:
                errors.append((start_line, "字符串未闭合（缺少 %s）" % c))
                i = j
                continue
            for k in range(i + 1, j):
                chars[k] = " "
            i = j + 1
            continue
        if c in "([{":
            stack.append((c, line))
            i += 1
            continue
        if c in ")]}":
            if not stack:
                errors.append((line, "多余的闭括号 %s" % c))
            else:
                open_c, open_line = stack.pop()
                if "([{".index(open_c) != ")]}".index(c):
                    errors.append((line, "括号不配平：%s（第%d行开）与 %s"
                                   % (open_c, open_line, c)))
            i += 1
            continue
        i += 1
    for open_c, open_line in stack:
        errors.append((open_line, "括号未闭合：%s" % open_c))
    return "".join(chars), errors


def strip_comments(text):
    """抹除注释（保留 IRI 与字符串内容），供前缀声明解析使用。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "<":
            j = text.find(">", i + 1)
            j = n if j < 0 else j + 1
            out.append(text[i:j])
            i = j
            continue
        if text.startswith('"""', i) or text.startswith("'''", i):
            q = text[i:i + 3]
            j = text.find(q, i + 3)
            j = n if j < 0 else j + 3
            out.append(text[i:j])
            i = j
            continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j])
            i = j
            continue
        if c == "#":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_prefixes(decl_text):
    """返回 {前缀: IRI}；空前缀用 '' 作键。输入需保留 IRI 内容。"""
    prefixes = {}
    for m in re.finditer(
            r"@prefix\s+([A-Za-z][\w-]*)?\s*:\s*<([^>]*)>\s*\.", decl_text):
        prefixes[m.group(1) or ""] = m.group(2)
    for m in re.finditer(
            r"(?im)^\s*PREFIX\s+([A-Za-z][\w-]*)?\s*:\s*<([^>]*)>", decl_text):
        prefixes[m.group(1) or ""] = m.group(2)
    return prefixes


def find_prefixed_names(masked):
    """返回 (带前缀名列表, 裸冒号本地名列表)。"""
    named = re.findall(r"(?<![\w#/>'\"])([A-Za-z][\w-]*):([A-Za-z0-9_][\w.\-]*)",
                       masked)
    bare = re.findall(r"(?<![\w<\"']):([A-Za-z][\w.\-]*)", masked)
    return named, bare


def find_graph_blocks(masked):
    """返回 [(标签, 块内容)]；块内容为花括号内的 masked 文本。"""
    blocks = []
    for m in re.finditer(r"([^\s{};.,\[\]()]+)\s*\{", masked):
        label = m.group(1)
        if label.upper() == "GRAPH":
            continue
        depth, j = 1, m.end()
        while j < len(masked) and depth:
            if masked[j] == "{":
                depth += 1
            elif masked[j] == "}":
                depth -= 1
            j += 1
        blocks.append((label, masked[m.end():j - 1]))
    return blocks


def local_name(label):
    """取图标签的本地名：去 <>、去前缀、去 # 与 / 之后部分。"""
    s = label.strip("<>")
    if s.startswith(":"):
        s = s[1:]
    if ":" in s and "/" not in s.split(":")[0]:
        s = s.split(":", 1)[1]
    for sep in ("#", "/"):
        if sep in s:
            s = s.rsplit(sep, 1)[1]
    return s


def check_file(path):
    text = read_text(path)
    masked, lex_errors = scan(text)
    fails, warns, infos = [], [], []

    # S1/S2 词法与配平
    for ln, msg in lex_errors:
        fails.append("第%d行：%s" % (ln, msg))
    if not lex_errors:
        infos.append("S1/S2 词法完整、括号配平")

    # S3 前缀闭合（声明从保留 IRI 的去注释文本解析；使用点在 masked 上匹配）
    prefixes = parse_prefixes(strip_comments(text))
    named, bare = find_prefixed_names(masked)
    undeclared = sorted({p for p, _l in named
                         if p not in prefixes
                         and p.lower() not in ("prefix", "base")})
    if undeclared:
        fails.append("未声明的前缀：%s" % "、".join(undeclared))
    if bare and "" not in prefixes:
        fails.append("使用裸 :local 形式 %d 处但未声明空前缀（@prefix : <...>）"
                     % len(bare))
    if not undeclared and (not bare or "" in prefixes):
        shown = sorted("<默认>" if p == "" else p for p in prefixes)
        infos.append("S3 前缀闭合（已声明：%s）" % ("、".join(shown) or "无"))

    # S4 句点结尾
    blocks = find_graph_blocks(masked)
    top = masked
    for m in re.finditer(r"[^\s{};.,\[\]()]+\s*\{", masked):
        depth, j = 1, m.end()
        while j < len(masked) and depth:
            depth += {"{": 1, "}": -1}.get(masked[j], 0)
            j += 1
        top = top.replace(masked[m.start():j], " ", 1)
    body_no_directives = re.sub(
        r"(?im)^\s*(@prefix|@base|prefix|base)\b[^.]*\.", " ", top)
    tail = body_no_directives.rstrip()
    if tail and not tail.endswith("."):
        fails.append("顶层语句未以句点 . 结束")
    for label, content in blocks:
        c = content.rstrip()
        if c and not c.endswith("."):
            fails.append("图块 %s 内容未以句点 . 结束" % label)
        if re.search(r"[;,]\s*$", c):
            fails.append("图块 %s 结尾残留 ; 或 ,（疑似缺最后一条宾语）" % label)
    if not any("句点" in f or "残留" in f for f in fails):
        infos.append("S4 语句均以句点结束")

    # 结构层：是否按 nanopub 检查
    np_prefixes = [p for p, iri in prefixes.items() if NP_NS in iri]
    is_trig = bool(blocks) or path.lower().endswith(".trig")
    if np_prefixes or is_trig:
        # N1 三部结构谓词
        found = []
        for pred in NP_PREDICATES:
            pat_prefix = any(
                re.search(r"(?<![\w])%s:%s\b" % (re.escape(p), pred), masked)
                for p in np_prefixes)
            pat_iri = re.search(
                r"<%s%s>" % (re.escape("http://www.nanopub.org/nschema#"), pred),
                text)
            if pat_prefix or pat_iri:
                found.append(pred)
        missing = [p for p in NP_PREDICATES if p not in found]
        if missing:
            fails.append("缺少 nanopub 三部结构谓词：%s" % "、".join(missing))
        else:
            infos.append("N1 hasAssertion/hasProvenance/hasPublicationInfo 齐全")
        if not np_prefixes and is_trig:
            warns.append("未声明映射到 %s 的前缀（np 谓词按完整 IRI 识别）" % NP_NS)

        # N2 四个命名图
        graph_locals = {local_name(l).lower() for l, _c in blocks}
        missing_g = [g for g in REQUIRED_GRAPHS if g not in graph_locals]
        if missing_g:
            fails.append("缺少命名图：%s（需 Head/assertion/provenance/pubInfo）"
                         % "、".join(missing_g))
        else:
            infos.append("N2 四个命名图齐全")

        # N3 assertion 非空
        assertion_bodies = [c for l, c in blocks
                            if local_name(l).lower() == "assertion"]
        if assertion_bodies:
            if not any(re.search(r"[^;,\s][ \t]*\.", c) for c in assertion_bodies):
                fails.append("assertion 图为空（没有任何以 . 结束的三元组）")
            else:
                infos.append("N3 assertion 图非空")

        # ---- v2 可选增强检查（全部仅 WARN，不把 v1 能通过的稿件判 FAIL）----
        # N4 证据挂接：provenance 图建议同时含 wasDerivedFrom 与 hasEvidenceAnchor
        prov_bodies = [c for l, c in blocks
                       if local_name(l).lower() == "provenance"]
        if prov_bodies:
            prov_all = "\n".join(prov_bodies)
            if "wasDerivedFrom" not in prov_all:
                warns.append("N4 provenance 图缺少 wasDerivedFrom（断言应挂回"
                             "论文 DOI/来源 IRI 或标注未报告）")
            if "hasEvidenceAnchor" not in prov_all:
                warns.append("N4 provenance 图缺少 hasEvidenceAnchor（断言应带"
                             "最小充分证据锚点串；无证据的断言必须降级或移出）")
            if "wasDerivedFrom" in prov_all and "hasEvidenceAnchor" in prov_all:
                infos.append("N4 provenance 证据挂接齐全")
        # N5 置信度标注：pubInfo 图建议含 confidence
        pub_bodies = [c for l, c in blocks
                      if local_name(l).lower() == "pubinfo"]
        if pub_bodies and not any("confidence" in c for c in pub_bodies):
            warns.append("N5 pubInfo 图缺少 confidence 置信度标注"
                         "（受控词表 high/medium/low + 依据）")
        elif pub_bodies:
            infos.append("N5 pubInfo 含置信度标注")
        # N6 v2 建议的语义增强：条件范围与证据形式
        prov_all = "\n".join(prov_bodies) if prov_bodies else ""
        if prov_bodies:
            if "conditionScope" not in prov_all:
                warns.append("N6 未标注 ex:conditionScope（v2 建议：写明断言生效的"
                             "条件范围/适用边界；无条件时说明原因）")
            if "evidenceForm" not in prov_all:
                warns.append("N6 未标注 ex:evidenceForm（v2 建议：证据形式分类——"
                             "实验数据/计算结果/引用支持/作者声明）")
    else:
        infos.append("未声明 nanopub 命名空间，跳过三部结构检查（纯 Turtle 模式）")
    return fails, warns, infos


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Nanopublication / Turtle / TriG 结构与语法校验（stdlib-only）")
    ap.add_argument("files", nargs="*", help="待检查的 .trig/.ttl 文件（绝对路径）")
    ap.add_argument("--dir", default=None, help="改为检查目录下全部 .trig/.ttl")
    args = ap.parse_args(argv)

    targets = list(args.files)
    if args.dir:
        if not os.path.isdir(args.dir):
            print("错误：目录不存在：%s" % args.dir)
            return 2
        for root, _d, files in os.walk(args.dir):
            for name in sorted(files):
                if name.lower().endswith((".trig", ".ttl")):
                    targets.append(os.path.join(root, name))
    targets = [t for t in targets if os.path.splitext(t)[1].lower()
               in (".trig", ".ttl")]
    if not targets:
        print("错误：没有待检查的 .trig/.ttl 文件（用 --help 查看用法）")
        return 2

    any_fail = False
    for path in targets:
        if not os.path.isfile(path):
            print("[FAIL] %s：文件不存在" % path)
            any_fail = True
            continue
        fails, warns, infos = check_file(path)
        print("== %s ==" % path)
        for msg in infos:
            print("  [PASS] " + msg)
        for msg in warns:
            print("  [WARN] " + msg)
        for msg in fails:
            print("  [FAIL] " + msg)
        if fails:
            any_fail = True
    print("----")
    print("校验结论：%s（共 %d 个文件）"
          % ("未通过" if any_fail else "通过", len(targets)))
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
