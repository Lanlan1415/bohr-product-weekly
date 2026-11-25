# Usage

This skill is triggered by `SKILL.md` when a case asks for research-quality appraisal.

1. Put the official case at `/input/case.json`; keep `task.md` and source documents under `/input`.
2. The agent reads the source documents, fills the evidence table, and writes
   `/app/output/appraisal_table.md` and `/app/output/result.json`.
3. If the case specifies `output_contract`, copy every named field into `result.json`.
4. Run a quick self-check:
   - every quote exists in the supplied source;
   - every non-`insufficient` judgment has a locator;
   - every unknown item is listed in `limits` or `uncertainty`;
   - `case_id` and all contract keys are present.

Runtime: Python 3.9+ or any text-capable agent; no network dependency.
