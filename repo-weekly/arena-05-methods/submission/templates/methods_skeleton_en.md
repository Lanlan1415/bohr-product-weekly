# Methods & Experiments Section Skeleton (English)

> Usage: fill `{{placeholders}}` only from materials and attach `[S#]`; where materials are silent, write `[To be confirmed: ...]` — never delete a subsection, never invent a value. Subsections may be adapted to the target venue, but none of the six element categories may be absent as a whole. Sentence patterns: `references/sentence_patterns.md`.

## 3. Methods and Experiments

### 3.1 Experimental Setup
- Hardware and environment: {{hardware, OS, framework+version, CUDA}}. [S#]
- Randomness and repetitions: {{number of runs, seeds, reporting convention}}. [S#]
- Code and dependencies: {{repository/version, environment file}}. [S#]

### 3.2 Datasets and Splits
{{Dataset name, version, size}} [S#]. Preprocessing: {{steps in order}} [S#]. Split: {{ratio + randomization + seed}} [S#]. Role of each subset: {{training / tuning / final reporting}}.

### 3.3 Procedure
1. {{Step 1: input → operation → output → termination criterion}}. [S#]
2. {{Step 2}}. [S#]
3. ... (describe training, validation, and testing in separate paragraphs; do not mix conditions)

### 3.4 Hyperparameters
All hyperparameters are listed in Table 1; the text refers to the canonical values only. [S#]

**Table 1. Hyperparameters and their sources (excerpt; full version in param_table.md)**

| Parameter | Value | Unit | Applies to | Source |
|-----------|-------|------|-----------|--------|
| {{name}} | {{value}} | {{unit}} | {{object}} | [S# location] |

### 3.5 Baselines and Evaluation
- Baselines: {{name + version/source}}; equal-budget note: {{}}. [S#]
- Metrics: {{metric + definition/source}}; statistics: {{runs, mean ± std, significance test}}. [S#]
- Results: {{only comparisons actually present in the materials, values with [S#]}}.

### 3.6 Reproducibility and Limitations
- Reproduction checklist: code {{}}; environment {{}}; command {{}}; data access {{}}; expected artifacts {{}}.
- Limitations: {{specific failure scenario + evidence [S#] + applicable scope}}.

### 3.7 Open Questions and Material Gaps
- Q1: {{gap + what is needed from the authors}}.
- Q2: ...
