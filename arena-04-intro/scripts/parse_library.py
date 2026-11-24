#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_library.py — 文献库解析：BibTeX 子集 / JSON / 编号列表 → 统一条目表 (JSON)。

用途
    把案例提供的可引文献库解析成统一条目表，供后续分组、转述、核验脚本使用。
    纯标准库实现，不联网，对中文/Unicode 安全。

支持格式
    1. BibTeX 子集：@article/@inproceedings/@book 等常规条目；
       支持 {花括号} / "引号" / 裸数字三种取值、`#` 拼接、@string 预定义串；
       支持 @comment/@preamble（跳过）。不支持 .bst 样式与交叉引用宏展开。
    2. JSON：条目列表，或带 references/papers/library/entries/refs/items/data 键的对象；
       字段名接受常见别名（author/authors/作者、title/标题、journal/venue/来源 等）。
    3. 编号列表：形如 `[1] 作者. 年份. 标题.` 或 `1. ...` / `1、 ...` 的纯文本（启发式解析，
       结果带 LIST_FORMAT_HEURISTIC 警告，标题等字段为尽力而为）。

用法
    python parse_library.py --input refs.bib --output entries.json
    python parse_library.py --input refs.json --format json
    python parse_library.py --input refs.txt --format list

输出
    stdout 与 --output 文件均为 JSON 报告：
    {"script", "format", "count", "entries": [{id,type,title,authors,year,venue,doi,url,
     keywords,abstract,fields}], "warnings": [...]}

退出码
    0 成功（含 count=0 的空库，报告内有 EMPTY_LIBRARY 提示）
    2 输入错误（文件不存在 / 无法识别格式 / JSON 非条目列表）
"""

import argparse
import json
import re
import sys
import unicodedata

SCRIPT = "parse_library"
VERSION = "1.0.0"

ENTRY_START = re.compile(r"@(\w+)\s*[{(]")
FIELD_NAME = re.compile(r"\s*([A-Za-z][\w\-\.+]*)\s*=")
BARE_TOKEN = re.compile(r"[^,#\s{}()\"]+")
WS = " \t\r\n"


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def norm(s):
    return norm_ws(unicodedata.normalize("NFC", s or ""))


def skip_ws(text, i):
    while i < len(text) and text[i] in WS:
        i += 1
    return i


def read_braced(text, i):
    """text[i] == '{'，返回 (内部内容, 下一位置)。"""
    depth = 0
    j = i
    n = len(text)
    start = i + 1
    while j < n:
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:j], j + 1
        j += 1
    return text[start:], n  # 未闭合：调用方负责告警


def read_quoted(text, i):
    """text[i] == '"'，花括号内的引号不终止字符串。"""
    depth = 0
    j = i + 1
    n = len(text)
    while j < n:
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c == '"' and depth == 0:
            return text[i + 1:j], j + 1
        j += 1
    return text[i + 1:], n


def parse_value_chain(text, i, strings, warnings, where):
    """解析一个字段的取值（含 `#` 拼接链），返回 (值, 下一位置)。"""
    parts = []
    n = len(text)
    while True:
        i = skip_ws(text, i)
        if i >= n:
            break
        c = text[i]
        if c == "{":
            val, i = read_braced(text, i)
            parts.append(val)
        elif c == '"':
            val, i = read_quoted(text, i)
            parts.append(val)
        else:
            m = BARE_TOKEN.match(text, i)
            if not m:
                break
            tok = m.group(0)
            i = m.end()
            low = tok.lower()
            if low in strings:
                parts.append(strings[low])
            elif tok.isdigit():
                parts.append(tok)
            else:
                parts.append(tok)
                warnings.append({"code": "UNRESOLVED_STRING",
                                 "detail": "%s：引用了未定义的 @string 名 %r，按字面保留" % (where, tok)})
        i = skip_ws(text, i)
        if i < n and text[i] == "#":
            i += 1
            continue
        break
    return "".join(parts), i


def parse_fields(src, strings, warnings, where):
    fields = {}
    i = 0
    n = len(src)
    while i < n:
        i = skip_ws(src, i)
        if i >= n:
            break
        if src[i] == ",":
            i += 1
            continue
        m = FIELD_NAME.match(src, i)
        if not m:
            warnings.append({"code": "FIELD_PARSE_SKIP",
                             "detail": "%s：偏移 %d 处无法识别为“字段名=取值”，跳过该片段" % (where, i)})
            break
        name = m.group(1).lower()
        i = m.end()
        value, i = parse_value_chain(src, i, strings, warnings, where)
        fields[name] = value
    return fields


def parse_bibtex(text):
    entries = []          # (entry_type, key, fields)
    warnings = []
    strings = {}          # @string 名（小写）→ 值
    n = len(text)
    pos = 0
    while True:
        m = ENTRY_START.search(text, pos)
        if not m:
            break
        etype = m.group(1).lower()
        open_pos = m.end() - 1
        open_ch = text[open_pos]
        close_ch = "}" if open_ch == "{" else ")"
        depth = 1
        j = m.end()
        while j < n and depth > 0:
            c = text[j]
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
            j += 1
        if depth != 0:
            warnings.append({"code": "UNCLOSED_ENTRY",
                             "detail": "@%s（偏移 %d）花括号不闭合，该条目已跳过" % (etype, m.start())})
            pos = m.end()
            continue
        body = text[m.end():j - 1]
        pos = j
        if etype in ("comment", "preamble"):
            continue
        if etype == "string":
            fields = parse_fields(body, strings, warnings, "@string")
            for k, v in fields.items():
                strings[k] = v
            continue
        comma = body.find(",")
        if comma == -1:
            key, field_src = body.strip(), ""
        else:
            key, field_src = body[:comma].strip(), body[comma + 1:]
        if not key:
            warnings.append({"code": "MISSING_KEY", "detail": "@%s 条目缺少引用键，已跳过" % etype})
            continue
        fields = parse_fields(field_src, strings, warnings, "@" + key)
        entries.append((etype, key, fields))
    return entries, warnings


def split_authors(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"\s+and\s+|;\s*", raw, flags=re.IGNORECASE)
    out = []
    for it in items:
        if isinstance(it, dict):
            nm = it.get("name") or " ".join(x for x in [it.get("first", ""), it.get("last", "")] if x)
            it = nm
        it = norm(str(it))
        if it:
            out.append(it)
    return out


def extract_year(*candidates):
    for c in candidates:
        if not c:
            continue
        m = re.search(r"(19|20)\d{2}", str(c))
        if m:
            return m.group(0)
    return None


def split_keywords(raw):
    if not raw:
        return []
    return [norm(x) for x in re.split(r"[,;，；]", norm(raw)) if norm(x)]


def normalize_entry(etype, key, fields, idx, source_format):
    authors = split_authors(fields.get("author") or fields.get("authors") or fields.get("editor") or "")
    year = extract_year(fields.get("year"), fields.get("date"), fields.get("pub_year"))
    venue = norm(fields.get("journal") or fields.get("booktitle") or fields.get("conference")
                 or fields.get("publisher") or fields.get("howpublished") or "")
    entry = {
        "id": norm(key) or "entry-%d" % (idx + 1),
        "type": norm(etype) or source_format,
        "title": norm(fields.get("title") or fields.get("标题") or ""),
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": norm(fields.get("doi") or ""),
        "url": norm(fields.get("url") or fields.get("link") or ""),
        "keywords": split_keywords(fields.get("keywords") or fields.get("keyword") or fields.get("tags") or ""),
        "abstract": norm(fields.get("abstract") or fields.get("summary") or fields.get("摘要") or ""),
        "fields": {k: norm(v) for k, v in fields.items()},
        "source_format": source_format,
    }
    return entry


ALIASES = {
    "id": ("id", "key", "ref", "citekey", "citation_key", "citationkey", "编号", "序号"),
    "title": ("title", "标题", "题目", "name"),
    "author": ("author", "authors", "作者", "creator", "creators"),
    "year": ("year", "年份", "date", "pub_year", "发表年"),
    "venue": ("venue", "journal", "booktitle", "conference", "source", "来源", "期刊", "publication", "出版源"),
    "doi": ("doi", "DOI"),
    "url": ("url", "link", "链接"),
    "keywords": ("keywords", "keyword", "tags", "关键词", "标签"),
    "abstract": ("abstract", "summary", "note", "annote", "摘要", "简介"),
    "type": ("type", "entrytype", "类型"),
}


def pick_field(rec, names):
    for nm in names:
        if nm in rec and rec[nm] not in (None, ""):
            return rec[nm]
    # 大小写不敏感兜底
    lower = {str(k).lower(): v for k, v in rec.items()}
    for nm in names:
        if nm.lower() in lower and lower[nm.lower()] not in (None, ""):
            return lower[nm.lower()]
    return None


def normalize_json_record(rec, idx):
    fields = {}
    for canon, names in ALIASES.items():
        v = pick_field(rec, names)
        if v is not None:
            fields[canon] = v
    authors = split_authors(fields.get("author", ""))
    year = extract_year(fields.get("year"))
    entry = {
        "id": norm(str(fields.get("id") or "entry-%d" % (idx + 1))),
        "type": norm(str(fields.get("type") or "json")),
        "title": norm(str(fields.get("title") or "")),
        "authors": authors,
        "year": year,
        "venue": norm(str(fields.get("venue") or "")),
        "doi": norm(str(fields.get("doi") or "")),
        "url": norm(str(fields.get("url") or "")),
        "keywords": split_keywords(fields.get("keywords") or ""),
        "abstract": norm(str(fields.get("abstract") or "")),
        "fields": {k: norm(str(v)) for k, v in rec.items() if isinstance(v, (str, int, float))},
        "source_format": "json",
    }
    return entry


LIST_LINE = re.compile(r"^\s*(?:\[(\d{1,3}[a-z]?)\]|(\d{1,3})[\.、\)])\s*(.+)$", re.A)


def parse_numbered_list(text):
    warnings = []
    raw_items = []
    cur = None
    for line in text.splitlines():
        m = LIST_LINE.match(line)
        if m:
            if cur:
                raw_items.append(cur)
            num = m.group(1) or m.group(2)
            cur = {"id": num, "text": m.group(3).strip()}
        else:
            if cur is not None and line.strip():
                cur["text"] += " " + line.strip()
    if cur:
        raw_items.append(cur)
    entries = []
    for idx, it in enumerate(raw_items):
        text1 = norm_ws(it["text"])
        ym = re.search(r"(?<!\d)((19|20)\d{2})(?!\d)", text1)
        year = ym.group(1) if ym else None
        segs = [s.strip() for s in re.split(r"(?<=[.。])\s+", text1) if s.strip()]
        title = segs[1] if len(segs) >= 2 else text1
        fields = {"citation_raw": text1}
        e = {
            "id": it["id"],
            "type": "list-item",
            "title": title[:200],
            "authors": [text1.split(".")[0].strip()] if "." in text1 else [],
            "year": year,
            "venue": "",
            "doi": "",
            "url": "",
            "keywords": [],
            "abstract": "",
            "fields": fields,
            "source_format": "list",
        }
        entries.append(e)
    if entries:
        warnings.append({"code": "LIST_FORMAT_HEURISTIC",
                         "detail": "编号列表为启发式解析：title/authors 为尽力而为，"
                                   "建议逐条人工核对或改用 BibTeX/JSON 提供（引用键以编号为准）"})
    return entries, warnings


JSON_WRAP_KEYS = ("references", "papers", "library", "entries", "refs", "items", "data", "文献库", "文献列表")


def detect_format(text):
    # BibTeX：条目可在任意位置（文件首部允许 % 注释/说明文字）
    if re.search(r"@\w+\s*[{(]", text):
        return "bibtex"
    try:
        obj = json.loads(text)
        if isinstance(obj, list) or isinstance(obj, dict):
            return "json"
    except (ValueError, TypeError):
        pass
    if re.search(r"^\s*(?:\[\d{1,3}[a-z]?\]|\d{1,3}[\.、)])\s+\S", text, re.M):
        return "list"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="文献库解析：BibTeX 子集 / JSON / 编号列表 → 统一条目表（纯标准库）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python parse_library.py --input refs.bib --output entries.json")
    ap.add_argument("--input", required=True, help="文献库文件路径（.bib/.json/.txt 均可，自动识别）")
    ap.add_argument("--format", choices=["auto", "bibtex", "json", "list"], default="auto",
                    help="强制指定格式（默认 auto 自动识别）")
    ap.add_argument("--output", help="条目表 JSON 输出路径（默认仅打印到 stdout）")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        with open(args.input, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "READ_FAILED", "detail": str(e)},
                         ensure_ascii=False))
        return 2

    fmt = args.format if args.format != "auto" else detect_format(text)
    warnings = []
    entries = []
    if fmt == "bibtex":
        raw, warnings = parse_bibtex(text)
        seen = set()
        for idx, (etype, key, fields) in enumerate(raw):
            if key in seen:
                warnings.append({"code": "DUPLICATE_KEY",
                                 "detail": "引用键 %r 重复，仅保留首个条目" % key})
                continue
            seen.add(key)
            entries.append(normalize_entry(etype, key, fields, idx, "bibtex"))
    elif fmt == "json":
        try:
            obj = json.loads(text)
        except ValueError as e:
            print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "JSON_PARSE_FAILED",
                              "detail": str(e)}, ensure_ascii=False))
            return 2
        if isinstance(obj, dict):
            for k in JSON_WRAP_KEYS:
                if k in obj and isinstance(obj[k], list):
                    obj = obj[k]
                    break
            else:
                obj = None
        if not isinstance(obj, list):
            print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "JSON_SHAPE_UNSUPPORTED",
                              "detail": "JSON 需为条目列表，或含 references/papers/library/entries/refs/items/data 键"},
                             ensure_ascii=False))
            return 2
        entries = [normalize_json_record(rec, i) for i, rec in enumerate(obj) if isinstance(rec, dict)]
    elif fmt == "list":
        entries, warnings = parse_numbered_list(text)
    else:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "FORMAT_UNRECOGNIZED",
                          "detail": "无法识别格式：既不是 BibTeX（@开头）、JSON，也不是编号列表"},
                         ensure_ascii=False))
        return 2

    if not entries:
        warnings.append({"code": "EMPTY_LIBRARY", "detail": "未解析出任何条目，后续分组/核验将以 partial 降级"})

    report = {
        "script": SCRIPT,
        "version": VERSION,
        "format": fmt,
        "count": len(entries),
        "entries": entries,
        "warnings": warnings,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
