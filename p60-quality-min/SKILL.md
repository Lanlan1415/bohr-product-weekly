---
name: literature-quality-appraisal
description: >
  Appraise the research quality of supplied scientific documents with an explicit
  dimension-by-dimension evidence table. Use when /input/case.json or the task asks for
  study quality, risk of bias, design/reporting appraisal, evidence strength, or a
  reproducible quality assessment. Produces an editable appraisal table and result.json;
  never invents evidence, locators, statistics, or approval details.
---

# Literature quality appraisal

Read the actual files before judging them. The input case is the authority.

## Workflow

1. Read `/input/task.md` and `/input/case.json`. Record `case_id`, the requested
   `output_contract`, document paths, review question, and any required appraisal scale.
2. Read every supplied document. For PDFs use the platform PDF text tool; use OCR only when
   the page has no text layer. Keep the document id, page/section/table/figure locator, and a
   short verbatim quote for every factual observation.
3. Determine each study's design: RCT, non-randomised intervention, cohort, case-control,
   cross-sectional, diagnostic accuracy, systematic review/meta-analysis, qualitative, modeling,
   or protocol. Apply only dimensions that fit that design.
4. Complete the core dimensions below. Add design-specific domains when the task or rubric asks.
5. Assign each dimension a judgment: `low`, `some_concerns`, `high`, or `insufficient`.
   `insufficient` is mandatory when the needed information is not in the supplied material.
6. Derive the overall assessment from the dimension judgments and state the rule used. Do not
   turn a reporting gap into proof that a bias exists, and do not turn abstract-only evidence
   into a low-risk judgment.
7. Write an editable `/app/output/appraisal_table.md` and `/app/output/result.json`.
   If the task names another artifact, produce that as well.

## Required appraisal dimensions

| dimension | judge | minimum evidence |
|---|---|---|
| research question and design fit | Is the design capable of answering the question? | question quote + design description |
| sample and selection | sampling, eligibility, sample size, losses/exclusions | sample section or table |
| measurement and outcomes | definitions, instruments, blinding, outcome prespecification | methods/outcome quote |
| analysis and statistics | analysis matched to design; effect size, uncertainty, multiplicity, assumptions | analysis section/table |
| confounding and bias | design-specific bias domains; direction if plausible | passage/table locator |
| reporting completeness | missing items relative to the relevant reporting guideline | section-level gap map |
| reproducibility and provenance | data/code/version/environment/registration available | repository/registration quote |
| conclusions and scope | conclusions supported by results; causal language appropriate | results + conclusion quotes |
| ethics, consent and conflicts | approval/consent/COI statements, or explicitly `not_reported` | declaration quote |

Every row must contain: `dimension`, `judgment`, `evidence_quote`, `locator`, `rationale`,
`risk_if_any`, and `reviewer_note`. A quote must be an exact substring of the supplied
material. If no exact evidence exists, use `null` plus an `insufficient` judgment and explain
the search scope in `limits`.

## Output contract

`result.json` must:

- put `case_id` at the top level;
- reproduce every key named by the input `output_contract` at the top level, preserving its name
  and value type;
- include `status` (`success`, `partial`, `undetermined`, or `refused`), `appraisals`,
  `overall`, `sources`, `uncertainty`, `limits`, and `review_actions`;
- include, for each document, `document_id`, `design`, `appraisal_rows`, `overall_judgment`,
  `overall_basis`, and `unresolved_gaps`;
- include an `appraisal_table.md` that a second reviewer can fill in and audit.

If an `output_contract` field cannot be derived, keep the key with `null` and list the reason
under `limits`; never silently drop it.

## Boundaries

- This is a structured quality appraisal, not a substitute for peer review or a clinical decision.
- Do not claim to have run an official RoB 2, ROBINS-I, QUADAS-2 or GRADE assessment unless the
  input supplies the required signalling questions and the output explicitly follows that method.
- Do not fabricate page numbers, quotations, sample sizes, effect estimates, approval numbers, or
  publication status.
- If only an abstract is available, mark design-specific and risk-of-bias rows `insufficient`.
- If documents conflict, report both with their locators and do not silently choose one.
- Save an honest partial result before refining it. The platform budget is limited.
