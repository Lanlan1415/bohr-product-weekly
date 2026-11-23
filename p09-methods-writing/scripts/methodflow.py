"""Extract methods evidence, audit authored prose, and deliver reproducibility gaps.

Primary CLI for 写作09.  It reads actual config/log/code/protocol files without
executing them; recursively flattens JSON/YAML-like scalar assignments with file
and locator; separates real protocol steps from parameters; audits every prose
number; and emits a 13-category evidence-or-gap matrix.  Missing randomisation,
ethics, etc. is a question for the author, never a value to invent.  A category
can be not_applicable only with an explicit rationale and source in the spec.

Usage:
  python methodflow.py --case /input/case.json --input-root /input \
    --prose /app/work/methods.md --spec /app/work/method-spec.json \
    --work /app/work --out /app/output

--spec is optional and may carry coverage_overrides plus output values.  Exit:
0 success; 3 partial (source/prose/coverage gaps); 4 partial with unsupported
numbers, unit mismatch or conflicting values; 5 refused/undetermined.  Every
exit writes structured result.json and editable artefacts when available.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from numeric_consistency import audit_prose, known_value_strings  # noqa: E402

TEXT_SUFFIXES = {".json", ".yaml", ".yml", ".txt", ".log", ".md", ".cfg", ".conf",
                 ".ini", ".toml", ".py", ".sh", ".csv", ".tsv", ".xml", ".yaml.bak"}
ASSIGN = re.compile(r"^([\w\u4e00-\u9fff][\w.\-\u4e00-\u9fff]*)\s*[:=]\s*(.+?)\s*$")
NUM_UNIT = re.compile(r"^([+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z%°μ]{1,12})$")
STEP_LINE = re.compile(r"^\s*(?:(?:step|步骤)\s*\d+\s*[:：.]|(?:\d+)[.)]\s+)(.+)$", re.I)
DATA_KEYS = {"dataset", "data", "split", "train_split", "test_split", "validation_split",
             "dataset_name", "corpus", "benchmark", "data_version"}
CATEGORIES = {
    "design": ("研究设计与实验流程是否明确？", ("design", "randomized controlled", "observational",
               "cross-sectional", "cohort", "experiment_type", "研究设计", "试验设计")),
    "variables": ("自变量、因变量/结局与协变量分别是什么？", ("independent variable", "dependent variable",
               "covariate", "exposure", "outcome", "feature", "label", "输入变量", "输出变量", "自变量", "因变量", "变量")),
    "controls": ("对照/基线的名称、版本和可比条件在哪里记录？", ("control", "baseline", "comparator",
               "placebo", "ablation", "对照", "基线", "安慰剂")),
    "materials_equipment": ("材料、试剂、设备、 manufacturer/model 与硬件来源是什么？", ("instrument", "device",
               "equipment", "apparatus", "reagent", "material", "manufacturer", "model", "gpu", "hardware",
               "仪器", "设备", "试剂", "材料", "硬件")),
    "steps": ("逐步操作的输入、动作、输出与判断条件是什么？", ("procedure", "protocol", "step", "centrifuge",
               "incubate", "preprocess", "train", "步骤", "流程", "操作")),
    "parameters": ("每个参数的取值、单位、作用对象和材料定位是什么？", ("lr", "learning_rate", "epoch", "batch",
               "temperature", "concentration", "parameter", "config", "learning rate", "参数", "配置")),
    "datasets": ("数据集名称、版本、规模、预处理、划分比例与各子集用途是什么？", ("dataset", "corpus",
               "benchmark", "split", "data_version", "preprocess", "train_data", "test_data", "数据集", "划分")),
    "sample_size_repeats": ("样本量、独立重复/技术重复次数分别是什么？", ("sample_size", "sample size", "n=",
               "replicate", "repetition", "repeat", "runs", "样本量", "重复", "生物学重复", "技术重复")),
    "randomization_blinding": ("是否随机分组/随机化顺序及是否盲法？若不需要，理由在哪里？", ("randomization", "random assignment",
               "randomly assigned", "allocation", "blind", "mask", "随机分组", "随机化", "盲法", "分配隐藏")),
    "statistics": ("评价指标、统计检验、显著性/区间与多重比较策略是什么？", ("statistic", "t-test", "anova",
               "regression", "p-value", "p_value", "confidence interval", "metric", "evaluation", "统计", "检验", "置信区间")),
    "ethics_safety": ("伦理审批/知情同意或豁免，以及安全/危害控制信息在哪里？", ("ethic", "consent", "irb",
               "safety", "hazard", "biosafety", "animal", "human subjects", "伦理", "知情同意", "安全", "危害")),
    "reproducibility": ("代码/环境/数据版本、命令、随机种子和获取方式是什么？", ("commit", "version", "command",
               "seed", "environment", "container", "requirements", "repository", "复现", "环境", "版本", "命令", "随机种子")),
    "limitations": ("具体失效场景、适用边界与排除条件是什么？", ("limitation", "failure", "invalid", "exclusion",
               "restricted", "not applicable", "限制", "失效", "不适用", "排除")),
}
DIRECT_KEYS = {cat: (cat, cat.replace("_", " ")) for cat in CATEGORIES}
DIRECT_KEYS.update({"materials_equipment": ("materials_equipment", "equipment", "instruments"),
                    "sample_size_repeats": ("sample_size_repeats", "sample_size", "repeats", "replicates"),
                    "randomization_blinding": ("randomization_blinding", "randomization", "blinding"),
                    "ethics_safety": ("ethics_safety", "ethics", "safety")})


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _case_id(case: dict) -> str:
    for key in ("case_id", "id", "caseId"):
        if case.get(key) is not None and str(case.get(key)).strip():
            return str(case[key])
    return "unknown"


def _coerce(raw: Any) -> tuple[Any, str]:
    if not isinstance(raw, str):
        return raw, ""
    text = raw.strip().strip("'\"").rstrip(",")
    if re.fullmatch(r"[+-]?\d+", text):
        try:
            return int(text), ""
        except ValueError:
            pass
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", text) or re.fullmatch(r"[+-]?\d+[eE][+-]?\d+", text):
        try:
            return float(text), ""
        except ValueError:
            pass
    m = NUM_UNIT.match(text)
    if m:
        try:
            return float(m.group(1)), m.group(2)
        except ValueError:
            pass
    return text, ""


def _resolve(raw: Any, roots: list[Path]) -> Path | None:
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        return None
    path = Path(raw)
    if path.is_absolute() and path.exists():
        return path
    for root in roots:
        candidate = root / str(raw)
        if candidate.exists():
            return candidate
    return None


def _material_paths(case: dict) -> list[Any]:
    values: list[Any] = []
    materials = case.get("materials")
    if isinstance(materials, dict):
        for key, value in materials.items():
            if key == "prose":
                continue
            values.append(value)
    elif isinstance(materials, (str, list)):
        values.append(materials)
    for key in ("config", "config_dir", "logs", "log_dir", "code", "code_dir", "notes",
                "protocol", "data", "dataset", "protocol_file"):
        if key in case:
            values.append(case[key])
    flat: list[Any] = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for k in ("path", "file", "root", "directory"):
                if value.get(k):
                    flat.append(value[k]); return
            for v in value.values():
                visit(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                visit(v)
        elif isinstance(value, str):
            flat.append(value)
    for value in values:
        visit(value)
    return flat


def extract_json(value: Any, path: Path, prefix: str = "") -> list[dict]:
    """Recursively recover dotted keys; nested objects are not silently discarded."""
    rows: list[dict] = []
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(extract_json(child, path, name))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            rows.extend(extract_json(child, path, f"{prefix}[{i}]"))
    elif isinstance(value, (str, int, float, bool)) or value is None:
        coerced, unit = _coerce(value)
        rows.append({"name": prefix, "value": coerced, "unit": unit, "source": str(path),
                     "line": None, "locator": f"JSON path {prefix}",
                     "quote": f"{prefix}={json.dumps(value, ensure_ascii=False)}"})
    return rows


def extract_file(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Return parameter rows, real protocol steps, keyword-bearing evidence lines."""
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = extract_json(payload, path)
        return rows, [], []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows: list[dict] = []; steps: list[dict] = []; chunks: list[dict] = []
    all_terms = tuple(term for terms in CATEGORIES.values() for term in terms[1])
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        match = ASSIGN.match(stripped.lstrip("- "))
        # Python/INI/YAML assignment, not arbitrary equations or commented code.
        if match and not stripped.startswith("#"):
            key, raw_value = match.group(1), match.group(2)
            raw_value = re.split(r"\s+#", raw_value, maxsplit=1)[0].strip()
            value, unit = _coerce(raw_value)
            rows.append({"name": key, "value": value, "unit": unit, "source": str(path),
                         "line": lineno, "locator": f"line {lineno}",
                         "quote": stripped[:300]})
        step = STEP_LINE.match(stripped)
        if step:
            steps.append({"step_id": f"{path.stem}-S{len(steps) + 1:03d}",
                          "text": step.group(1).strip(), "source": str(path), "line": lineno,
                          "locator": f"line {lineno}", "method": "explicit step enumeration"})
        low = stripped.lower()
        if any(str(term).lower() in low for term in all_terms):
            chunks.append({"source": str(path), "line": lineno, "locator": f"line {lineno}",
                           "quote": stripped[:500]})
    return rows, steps, chunks


def structured_evidence(case: dict) -> list[dict]:
    """Read explicit case fields without inventing nested interpretations."""
    out = []
    roots = [case]
    if isinstance(case.get("methods"), dict):
        roots.append(case["methods"])
    if isinstance(case.get("experiment"), dict):
        roots.append(case["experiment"])
    for root in roots:
        for category, keys in DIRECT_KEYS.items():
            for key in keys:
                value = root.get(key)
                if value not in (None, "", [], {}):
                    out.append({"category": category, "source": "case.json",
                                "locator": f"field {key}", "quote": copy.deepcopy(value)})
    raw_steps = case.get("steps") or (case.get("methods", {}) or {}).get("steps") \
        if isinstance(case.get("methods", {}), dict) else case.get("steps")
    if isinstance(raw_steps, list):
        for i, step in enumerate(raw_steps):
            if isinstance(step, (str, dict)):
                out.append({"category": "steps", "source": "case.json",
                            "locator": f"steps[{i}]", "quote": copy.deepcopy(step)})
    return out


def coverage_matrix(case: dict, rows: list[dict], steps: list[dict], chunks: list[dict],
                    direct: list[dict], overrides: Any) -> tuple[list[dict], list[dict]]:
    coverage: list[dict] = []; questions: list[dict] = []
    overrides = overrides if isinstance(overrides, dict) else {}
    for category, (question, terms) in CATEGORIES.items():
        termset = tuple(str(t).lower() for t in terms)
        evidence = []
        for row in rows:
            hay = f"{row['name']} {row.get('quote', '')}".lower()
            matched = any(term in hay for term in termset)
            if category == "parameters":
                matched = True
            if category == "steps":
                # A parameter named preprocessing/train is not an ordered protocol.
                # Only explicit step records and procedural source sentences count below.
                matched = False
            if category == "datasets":
                matched = any(t in row["name"].lower() for t in DATA_KEYS) or "dataset" in row["name"].lower()
            if category == "randomization_blinding" and "seed" in row["name"].lower() and not any(
                    x in hay for x in ("randomiz", "blind", "随机分组", "盲法")):
                matched = False  # RNG seed is not evidence of allocation randomisation/blinding
            if matched:
                evidence.append({"kind": "parameter", "name": row["name"], "value": row["value"],
                                 "unit": row.get("unit"), "source": row["source"],
                                 "locator": row.get("locator"), "quote": row.get("quote")})
        if category == "steps":
            evidence.extend({"kind": "step", **step} for step in steps)
        for chunk in chunks:
            if any(term in chunk["quote"].lower() for term in termset):
                evidence.append({"kind": "source_excerpt", **chunk})
        evidence.extend({"kind": "case_field", **x} for x in direct if x["category"] == category)
        # Stable dedup, bounded while always retaining the first locatable evidence.
        unique = []
        seen = set()
        for item in evidence:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key); unique.append(item)
        override = overrides.get(category)
        if unique:
            state = "reported"
        elif isinstance(override, dict) and str(override.get("status")).lower() == "not_applicable" \
                and str(override.get("rationale") or "").strip() and str(override.get("source") or "").strip():
            state = "not_applicable"
            unique = [{"kind": "declared_not_applicable", "rationale": override["rationale"],
                       "source": override["source"]}]
        else:
            state = "missing"
            questions.append({"category": category, "question": question,
                              "action": "answer from an actual supplied source, or declare not_applicable "
                                        "with a case-specific rationale and source; never infer it"})
        coverage.append({"category": category, "state": state,
                         "evidence": unique[:30], "evidence_count": len(unique),
                         "gap_question": None if state != "missing" else question})
    return coverage, questions


def dataset_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        name = row["name"].lower()
        if any(key in name for key in DATA_KEYS):
            out.append({"name": row["value"], "parameter": row["name"], "source": row["source"],
                        "locator": row.get("locator"), "status": "from_source"})
    if not out:
        return [{"name": None, "status": "not_in_source",
                 "reason": "no dataset/version/split key in the supplied files"}]
    return out


def find_conflicts(rows: list[dict]) -> list[dict]:
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        by_name.setdefault(row["name"], []).append(row)
    out = []
    for name, group in sorted(by_name.items()):
        variants = []
        for row in group:
            signature = json.dumps([row["value"], row.get("unit")], ensure_ascii=False, sort_keys=True)
            if all(json.dumps([x["value"], x.get("unit")], ensure_ascii=False, sort_keys=True) != signature
                   for x in variants):
                variants.append(row)
        if len(variants) > 1:
            out.append({"name": name, "status": "needs_author_confirmation",
                        "values": [{"value": x["value"], "unit": x.get("unit"),
                                    "source": x["source"], "locator": x.get("locator")} for x in variants],
                        "reason": "the same fully-qualified key has different values across sources; "
                                  "condition scopes were not guessed"})
    return out


def contract_names(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        wrappers = {"fields", "required", "lists", "optional"}
        if raw and set(raw).issubset(wrappers):
            out = []
            for value in raw.values():
                for name in contract_names(value):
                    if name not in out:
                        out.append(name)
            return out
        return [str(k) for k in raw]
    out = []
    if isinstance(raw, (list, tuple)):
        for e in raw:
            name = e if isinstance(e, str) else str(e.get("name") or e.get("field") or e.get("key") or "") if isinstance(e, dict) else ""
            if name and name not in out:
                out.append(name)
    return out


DERIVED = {"case_id", "status", "status_reason", "sources", "uncertainty", "change_records",
           "limits", "parameter_table", "datasets", "steps", "prose", "number_audit",
           "reproducibility", "limitations", "coverage", "gap_analysis", "evidence_map",
           "conflicts", "findings", "deliverable", "output_contract_fields"}


def echo_contract(case: dict, result: dict) -> None:
    for field in contract_names(case.get("output_contract")):
        if field in DERIVED and field in result:
            if result[field] is None and not any(field in str(note) for note in result.setdefault("limits", [])):
                result["limits"].append(f"output_contract field '{field}' is null because the engine could not derive it")
            continue
        if field in case and field != "output_contract" and case[field] is not None:
            result[field] = copy.deepcopy(case[field])
        else:
            result[field] = None
            result.setdefault("limits", []).append(
                f"output_contract field '{field}' was not derivable; left null")
    fields = contract_names(case.get("output_contract"))
    if fields:
        result["output_contract_fields"] = fields


def _refused(case: dict, out: Path, message: str, status: str = "refused") -> dict:
    result = {"schema_version": "methodflow/v1", "case_id": _case_id(case), "status": status,
              "status_reason": message, "sources": [], "uncertainty": [{"item": "input",
              "reason": message, "needs_human": True}], "change_records": [], "limits": [message],
              "parameter_table": [], "datasets": [{"name": None, "status": "not_in_source"}],
              "steps": [], "prose": "", "number_audit": {"unsupported": [], "known_values": [],
              "summary": {}}, "reproducibility": {"config_files": [], "parameters_extracted": 0,
              "command": None, "seed_present": False, "missing": []}, "limitations": [message],
              "coverage": [], "gap_analysis": [], "evidence_map": [], "conflicts": [],
              "findings": [{"rule": "methods.input_unreadable", "severity": "high", "message": message}]}
    echo_contract(case, result); _write(out / "result.json", result)
    return result


def build(case: dict, case_path: Path, input_root: Path | None, prose_arg: str,
          work: Path, out: Path) -> tuple[dict, int]:
    roots = [case_path.parent]
    if input_root:
        roots.append(input_root)
    roots.append(work)
    materials = case.get("materials") if isinstance(case.get("materials"), dict) else {}
    config_declared = materials.get("config_dir") or materials.get("config") or case.get("config")
    files: list[Path] = []; missing: list[str] = []
    for raw in _material_paths(case):
        found = _resolve(raw, roots)
        if found is None:
            missing.append(str(raw)); continue
        candidates = [found] if found.is_file() else sorted(p for p in found.rglob("*")
                      if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)
        files.extend(candidates[:500])
    # Stable dedup and hard resource boundary.
    unique_files = []; seen = set()
    for path in files:
        key = str(path)
        if key not in seen:
            seen.add(key); unique_files.append(path)
    files = unique_files[:1000]
    if config_declared and _resolve(config_declared, roots) is None:
        return _refused(case, out, f"declared config path is missing: {config_declared}"), 5
    if not files:
        return _refused(case, out, "no readable config/log/code/protocol files were found",
                        "undetermined"), 5
    rows: list[dict] = []; steps: list[dict] = []; chunks: list[dict] = []
    unreadable = []
    for path in files:
        try:
            r, s, c = extract_file(path)
            rows.extend(r); steps.extend(s); chunks.extend(c)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            unreadable.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    if not rows and not steps and not chunks:
        return _refused(case, out, "materials were found but contained no extractable scientific evidence",
                        "undetermined"), 5
    direct = structured_evidence(case)
    if isinstance(case.get("steps"), list):
        for i, step in enumerate(case["steps"]):
            if isinstance(step, str):
                steps.append({"step_id": f"case-S{i + 1:03d}", "text": step, "source": "case.json",
                              "line": None, "locator": f"steps[{i}]", "method": "case structured steps"})
            elif isinstance(step, dict):
                steps.append({"step_id": str(step.get("id") or f"case-S{i + 1:03d}"),
                              "text": step.get("text") or step.get("action") or json.dumps(step, ensure_ascii=False),
                              "input": step.get("input"), "output": step.get("output"),
                              "source": "case.json", "line": None, "locator": f"steps[{i}]",
                              "method": "case structured steps"})
    prose_raw = prose_arg or materials.get("prose") or "methods.md"
    prose_path = _resolve(prose_raw, [work, *roots])
    prose_note = "" if prose_path else f"prose file not found: {prose_raw}"
    prose = prose_path.read_text(encoding="utf-8-sig", errors="replace") if prose_path else ""
    # Numeric support may come from any actual protocol/log excerpt, while the
    # parameter_table remains restricted to explicit key-value parameters.
    audit_rows = list(rows)
    audit_rows.extend({"name": "protocol_step", "value": s["text"], "unit": "",
                       "source": s["source"], "line": s.get("line")} for s in steps)
    audit_rows.extend({"name": "source_excerpt", "value": c["quote"], "unit": "",
                       "source": c["source"], "line": c.get("line")} for c in chunks)
    audit_rows.extend({"name": x["category"], "value": json.dumps(x["quote"], ensure_ascii=False),
                       "unit": "", "source": x["source"], "line": None} for x in direct)
    audit = audit_prose(prose, audit_rows)
    unsupported = audit["unsupported_numbers"]
    conflicts = find_conflicts(rows)
    overrides = case.get("coverage_overrides")
    coverage, questions = coverage_matrix(case, rows, steps, chunks, direct, overrides)
    gaps = list(questions)
    for item in unreadable:
        gaps.append({"category": "material_readability", "question": f"Unreadable source: {item['path']}",
                     "action": item["error"], **item})
    datasets = dataset_rows(rows)
    # Actual structured steps take precedence over case strings, not parameters masquerading as steps.
    commands = case.get("command") or case.get("commands") or None
    if isinstance(commands, list):
        commands = [str(x) for x in commands if str(x).strip()]
    seed_present = any(row["name"].lower().split(".")[-1] in {"seed", "random_seed", "rng_seed"} for row in rows)
    repro_required = {
        "code_version": any(any(t in row["name"].lower() for t in ("commit", "code_version", "git_sha")) for row in rows),
        "data_version": any("data_version" in row["name"].lower() or "dataset_version" in row["name"].lower() for row in rows),
        "environment": any(any(t in row["name"].lower() for t in ("environment", "requirements", "container", "python_version", "dependencies")) for row in rows),
        "command": bool(commands), "seed": seed_present,
    }
    repro_missing = [k for k, present in repro_required.items() if not present]
    limitations = []
    for gap in gaps:
        limitations.append({"item": gap["category"], "reason": gap["question"],
                            "needs_author": True, "action": gap["action"]})
    for item in unsupported:
        limitations.append({"item": "prose_number", "reason": item["context"],
                            "number": item["number"], "needs_author": True})
    for item in conflicts:
        limitations.append({"item": "parameter_conflict", "reason": item["reason"],
                            "name": item["name"], "needs_author": True})
    if any(x.get("status") == "not_in_source" for x in datasets):
        limitations.append({"item": "dataset", "reason": "dataset identity/version/split not found",
                            "needs_author": True})
    if prose_note or not prose.strip():
        limitations.append({"item": "prose", "reason": prose_note or "prose is empty",
                            "needs_author": True})
    findings = []
    for item in unsupported:
        findings.append({"rule": "methods.unsupported_prose_number", "severity": "high",
                         "number": item["number"], "line": item["line"], "context": item["context"]})
    for item in conflicts:
        findings.append({"rule": "methods.parameter_conflict", "severity": "high",
                         "name": item["name"], "values": item["values"]})
    for gap in questions:
        findings.append({"rule": "methods.coverage_gap", "severity": "medium",
                         "category": gap["category"], "question": gap["question"]})
    if not prose.strip():
        findings.append({"rule": "methods.prose_missing", "severity": "high", "message": prose_note})
    hard = bool(unsupported or conflicts)
    partial = bool(limitations or repro_missing)
    status = "partial" if hard or partial else "success"
    if status == "success":
        reason = "prose numbers are source-supported; all 13 categories and reproducibility anchors are covered"
    elif hard:
        reason = "unsupported prose numbers or same-key parameter conflicts require author correction/confirmation"
    else:
        reason = "usable partial chapter/evidence delivered; named source or reproducibility gaps remain"
    sources = [{"source_id": f"SRC-{i + 1:04d}", "parameter": row["name"],
                "path": row["source"], "locator": row.get("locator"),
                "quote": row.get("quote"), "value": row["value"], "unit": row.get("unit")}
               for i, row in enumerate(rows)]
    evidence_map = sources + [{"source_id": f"STEP-{i + 1:04d}", "path": s["source"],
                               "locator": s.get("locator"), "quote": s["text"], "kind": "protocol_step"}
                              for i, s in enumerate(steps)]
    uncertainty = [dict(x) for x in limitations]
    result = {
        "schema_version": "methodflow/v1", "case_id": _case_id(case), "status": status,
        "status_reason": reason, "sources": sources, "uncertainty": uncertainty,
        "change_records": [{"id": "methods-evidence-1", "action": "extract",
                            "before": len(files), "after": len(rows),
                            "reason": "files and scalar evidence processed; no experiment run"},
                           {"id": "methods-coverage-1", "action": "audit",
                            "before": 13, "after": len(questions),
                            "reason": "13 categories audited; missing categories are author questions"}],
        "limits": [x["reason"] for x in limitations] +
                  (["reproducibility anchors missing: " + ", ".join(repro_missing)] if repro_missing else []) +
                  (["declared material paths not found: " + ", ".join(missing)] if missing else []) +
                  ["scripts inspect source text only; no experiment, code execution, statistical reanalysis, "
                   "randomisation, ethics approval or dataset download was performed"],
        "parameter_table": rows, "datasets": datasets, "steps": steps, "prose": prose,
        "number_audit": {"unsupported": unsupported, "known_values": sorted(known_value_strings(rows)),
                         "summary": {k: v for k, v in audit.items() if k != "unsupported_numbers"}},
        "reproducibility": {"config_files": [str(p) for p in files], "parameters_extracted": len(rows),
                            "command": commands, "seed_present": seed_present,
                            "required_anchors": repro_required, "missing": repro_missing},
        "limitations": limitations, "coverage": coverage, "gap_analysis": gaps,
        "evidence_map": evidence_map, "conflicts": conflicts, "findings": findings,
        "deliverable": {"methods_file": "methods.md", "parameter_table_file": "parameter_table.json",
                        "evidence_map_file": "evidence_map.json", "gap_analysis_file": "gap_analysis.json",
                        "editable": True, "experiments_executed": False},
    }
    echo_contract(case, result)
    out.mkdir(parents=True, exist_ok=True)
    (out / "methods.md").write_text(prose, encoding="utf-8")
    _write(out / "result.json", result); _write(out / "parameter_table.json", rows)
    _write(out / "evidence_map.json", evidence_map); _write(out / "gap_analysis.json", gaps)
    _write(out / "coverage.json", coverage)
    return result, (4 if hard else 3 if status == "partial" else 0)


def load_case(case_path: Path, spec_path: Path | None) -> dict:
    case = _load(case_path)
    if not isinstance(case, dict):
        raise ValueError("case must be a JSON object")
    if spec_path:
        spec = _load(spec_path)
        if not isinstance(spec, dict):
            raise ValueError("method spec must be a JSON object")
        merged = dict(case); merged.update(spec)
        if "case_id" not in spec:
            merged["case_id"] = _case_id(case)
        return merged
    return case


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True); ap.add_argument("--spec")
    ap.add_argument("--input-root"); ap.add_argument("--prose", default="")
    ap.add_argument("--work", required=True); ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out); case = {}
    try:
        case = load_case(Path(args.case), Path(args.spec) if args.spec else None)
        result, rc = build(case, Path(args.case), Path(args.input_root) if args.input_root else None,
                           args.prose, Path(args.work), out)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result = _refused(case, out, f"case/spec could not be read: {exc}"); rc = 5
    except Exception as exc:
        result = _refused(case, out, f"methods pipeline failed at structured boundary: "
                                     f"{type(exc).__name__}: {exc}"); rc = 5
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "parameters": len(result.get("parameter_table", [])),
                      "steps": len(result.get("steps", [])),
                      "coverage_gaps": len(result.get("gap_analysis", [])),
                      "unsupported": len(result.get("number_audit", {}).get("unsupported", [])),
                      "exit": rc, "wrote": str(out / "result.json")}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
