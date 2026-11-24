"""Benchmark for the thirteen remaining sections: clean baseline plus planted defects."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S

def d(base, **kw):
    s = copy.deepcopy(base); s.update(kw); return s

BASE = {
 "conclusion_extract": {"fields":[{"name":"effect_size","definition":"reported fold change in uptake rate"},{"name":"sample_n","definition":"replicates per group"}],"source_text":"The porous coating improved uptake 3-fold (Fig. 3b, p.7).","sources_present":["body","figure"],"conclusions":[{"claim":"\u6d82\u5c42\u7684\u5438\u6536\u901f\u7387\u63d0\u9ad8\u5230\u539f\u6765\u7684 3 \u500d","condition":"n=6, 25 C","locator":"Fig 3b, p.7","claim_kind":"conclusion","source_kind":"figure","hedged":True,"effect_size":"3-fold","sample_n":6,"values":[{"value":3,"unit":"fold","verbatim":"3-fold"}]},{"claim":"\u53ea\u6d4b\u8bd5\u4e86\u4e00\u79cd\u539a\u5ea6","condition":"n/a","locator":"p.7","claim_kind":"limitation","source_kind":"body","hedged":True,"effect_size":"","effect_size_status":"not_reported","sample_n":6,"values":[]}]},
 "claim_verify": {"references":[{"key":"doe2020","title":"Porous coatings","year":2020}],"source_text":"The porous coating increased the uptake rate three-fold.","claims":[{"claim":"porous coating increases uptake rate","support":"supports","rationale":"the quoted sentence states the rate increase directly","evidence":[{"source":"doe2020","quote":"The porous coating increased the uptake rate three-fold.","locator":"Fig 3b, p.7"}]}]},
 "compare_docs": {"field_groups":["metric","conclusion"],"documents":[{"id":"A","text":"Bandgap of 3.20 eV was measured for sample A.","fields":{"bandgap":{"value":"3.20 eV","unit":"eV","locator":"Table 1 row 2","dataset":"sample A","metric":"optical bandgap","control":"annealed"},"trend":{"value":"bandgap","direction":"decreases","strength":"moderate","locator":"p.5"}}},{"id":"B","text":"Bandgap of 3.37 eV was measured for sample B.","fields":{"bandgap":{"value":"3.37 eV","unit":"eV","locator":"Table 2 row 1","dataset":"sample B","metric":"optical bandgap","control":"as-grown"},"trend":{"value":"bandgap","direction":"decreases","strength":"moderate","locator":"p.6"}}}],"fields":[{"name":"bandgap","group":"metric","definition":"reported optical bandgap","target_unit":"eV","comparability":"same optical method","condition_variance":"control state differs (annealed vs as-grown); values compared as reported, not pooled as same-condition"},{"name":"trend","group":"conclusion","definition":"direction of the bandgap trend","conflict_note":"none observed"}]},
 "formula": {"formulas":[{"id":"F1","latex":"E = h c / \\lambda","lhs_unit":"J","rhs_unit":"J","variables":[{"name":"E","definition":"photon energy","source":"paper","locator":"Eq. 1, p.3","unit":"J"},{"name":"h","definition":"Planck constant","source":"convention","locator":"Eq. 1, p.3","unit":"J*s"},{"name":"c","definition":"speed of light","source":"convention","locator":"Eq. 1, p.3","unit":"m/s"},{"name":"\u03bb","definition":"wavelength","source":"paper","locator":"Eq. 1, p.3","unit":"m"}],"steps":[{"from":"E = h \u03bd","to":"E = h c / \u03bb","justification":"\u03bd = c / \u03bb for light in vacuum"}],"boundary_conditions":"single photon, vacuum","verified":True,"numeric":{"expression":"h*c/lambda","inputs":{"h":6.626e-34,"c":2.998e8,"lambda":5.32e-7},"expected":3.734e-19,"tolerance":1e-21}}]},
 "reproduce": {"commit":"a1b2c3d4e5f6","data_version":"dataset@2024-05","commands":["python train.py --config cfg/a.yaml"],"checklist":{"materials":[{"name":"dataset","source":"repo","version":"v1.2","state":"present"}],"environment":{"dependencies":"pinned in requirements.txt","hardware":"A100 40GB","seed":"0"},"parameters":[{"name":"lr","source":"paper","locator":"Table 1, p.4"}],"run":{"logs":"logs/train.log","exit_status":"succeeded"},"results":{"tolerance":"1e-3","comparison_basis":"Table 2 main metric","statistic":"mean of 5 seeds","metrics":[{"name":"accuracy","paper":0.912,"reproduced":0.9108,"within_tolerance":True}]},"verdict":"reproducible","verdict_basis":"all metrics within tolerance"}},
 "qa": {"evidence":[{"id":"e1","quote":"The uptake rate increased with the porous coating. The increase was three-fold over control.","locator":"p.7"}],"answers":[{"question":"what is the uptake rate change","answer":"the uptake rate increased three-fold with the porous coating","cites":["e1"]}]},
 "paper_draft": {"draft":"1 Introduction\nThe coating raises uptake [doe2020] {M1}.\n2 Methods\nWe measured 3 mM samples {M2}.\n3 Results\nUptake rose three-fold [doe2020] {M1} (Fig 1).\n","abstract":"The coating raised uptake three-fold.","design":"experimental","template":{"sections":["introduction","methods","results"]},"materials":[{"id":"M1","locator":"run01.csv row 4","text":"uptake rose three-fold with the coating"},{"id":"M2","locator":"notes.md 12:04","text":"samples were prepared at 3 mM"}],"references":[{"key":"doe2020","authors":"Doe J","year":2020,"journal":"J Uptake","topic":"coating raises uptake","doi":"10.1000/x"}],"figures":[{"id":"Fig 1","caption":"Uptake rose three-fold with the coating","values":["three-fold"]}],"declarations":{"data_availability":"on request","author_contributions":"all authors","competing_interests":"none","funding":"grant 123"},"change_log":["v1 initial","v2 added methods"]},
 "structure_logic": {"manuscript_text":"1 Introduction\nUptake is limited by surface area. We ask whether a porous coating raises uptake.\n2 Methods\nWe coated samples and measured uptake.\n3 Results\nUptake rose three-fold.\n4 Discussion\nThe effect is consistent with a surface-area mechanism.\n","research_question":"whether a porous coating raises uptake","design":"experimental","conclusion":"The effect is consistent with a surface-area mechanism.","limitations":"single material, one coating thickness","contributions":[{"claim":"a porous coating raises uptake","anchor":"3 Results"}],"paragraphs":[{"id":"p1","section":"Introduction","text":"Uptake is limited by surface area","claims":[{"claim":"uptake is limited by surface area","support":"[doe2020]","strength":"moderate","support_strength":"moderate"}]},{"id":"p2","section":"Methods","text":"We coated samples and measured uptake","claims":[{"claim":"the method is sound","support":"Sec 2","strength":"weak","support_strength":"moderate"}]},{"id":"p3","section":"Results","text":"Uptake rose three-fold","claims":[{"claim":"uptake rose three-fold","support":"Fig 1","strength":"strong","support_strength":"strong"}]}],"diagnosis":[{"id":"RES","dimension":"research_question","finding":"noted","evidence":"We ask whether a porous coating raises uptake","locator":"1 Introduction","severity":"minor"}, {"id":"SEC","dimension":"section_structure","finding":"noted","evidence":"2 Methods","locator":"2 Methods","severity":"minor"}, {"id":"ARG","dimension":"argument_chain","finding":"noted","evidence":"The effect is consistent with a surface-area mechanism","locator":"4 Discussion","severity":"minor"}, {"id":"PAR","dimension":"paragraph_relation","finding":"noted","evidence":"3 Results","locator":"3 Results","severity":"minor"}, {"id":"DUP","dimension":"duplication","finding":"noted","evidence":"We coated samples and measured uptake","locator":"2 Methods","severity":"minor"}, {"id":"CON","dimension":"conclusion_scope","finding":"noted","evidence":"Uptake rose three-fold","locator":"3 Results","severity":"minor"}],"suggestions":[{"for_finding":"ARG","action":"move the mechanism sentence to Results"}]},
 "results_discussion": {"design":"experimental","results_text":"Uptake rose three-fold in the coated group (p < 0.01, t-test). Arm B showed no change.","discussion_text":"The coated samples showed higher uptake, consistent with earlier work [doe2020]. The mechanism may involve increased surface area [doe2020]. Arm B did not reach significance. Roe reports a conflicting result [roe2021]. Alternative explanations include measurement drift, monitored with the same calibration samples [doe2020].","figures":[{"id":"Fig 1","values":["3","three-fold","0.01"],"has_errorbar":True,"errorbar":"SD"}],"comparisons":[{"name":"coated vs control","significant":True,"strength":"strong"},{"name":"Arm B","significant":False}],"literature":[{"key":"doe2020","agrees":True},{"key":"roe2021","agrees":False,"finding":"no effect at low dose"}],"limitations":[{"level":"sample","text":"single material system tested"},{"level":"measurement","text":"one coating thickness measured"},{"level":"sample","text":"Findings are limited to this material and should not be extrapolated to other materials."}]},
 "proposal": {"elements":{"rationale":{"text":"Surface-area limitation is the binding constraint in the current process, and the proposed coating is the only route we can execute with the platform in hand.","evidence":"preliminary data M1"},"question":{"text":"whether a 42 nm porous coating raises uptake rate three-fold","evidence":"M1"},"objectives":{"text":"three measurable objectives","evidence":"Sec 2"},"content":{"text":"coating synthesis and rate measurement","evidence":"M2"},"innovation":{"text":"Unlike prior work that reports endpoint uptake, this proposal measures the rate at which the coating changes it, under paired controls.","evidence":"[doe2020]"},"technical_route":{"text":"three steps with fallbacks","evidence":"Sec 4"},"foundation":{"text":"platform and prior coating work","evidence":"M0"}},"paragraphs":[{"text":"why this matters","element":"rationale","evidence":"M1"}],"objectives":[{"id":"O1","measure":"rate ratio vs control","outcome":"three-fold rate","content_ref":"C1"}],"content":[{"id":"C1","text":"synthesise and measure"}],"route":[{"id":"R1","objective":"O1","input":"monomer solution","output":"coated sample","risk":"pore collapse","fallback":"template removal at lower temperature"}],"foundation_items":[{"name":"coating rig","capability":"deposit 40 nm films","evidence":"M0 run 2023-04","relation":"the same rig makes the proposed coatings","status":"done"}],"timeline":[{"period":"Y1","milestone":"coating built and characterised"}],"budget":[{"item":"consumables","justification":"monomer and substrates for 60 runs"}],"budget_justification":"each line is costed from current supplier quotes"},
 "longdoc": {"outline":[{"id":"O1","title":"intro","argument_element":"question"},{"id":"O2","title":"methods","argument_element":"method"},{"id":"O3","title":"results","argument_element":"result"},{"id":"O4","title":"discussion","argument_element":"discussion"},{"id":"O5","title":"limits","argument_element":"limitation"}],"front_matter":{"toc":["intro","methods","results","discussion","limits"],"figure_list":["Fig 1"],"reference_section":"yes","appendix":"yes"},"terminology":[{"preferred":"uptake rate","chapter":"1"}],"symbols":[{"symbol":"r","meaning":"rate"}],"references":[{"key":"doe2020","title":"coating raises uptake","topic":"coating raises uptake"}],"figures":[{"number":1,"caption":"uptake curves"}],"chapters":[{"number":1,"title":"intro","outline_id":"O1","argument_element":"question","definitions":[{"term":"uptake rate","text":"rate of uptake"}],"answers":"whether a porous coating raises uptake","authorship_declared":True,"claims":[{"text":"coating raises uptake","reference":"doe2020"}],"conclusions":[{"statement":"coating raises uptake rate","direction":"increases"}],"changelog":["v1 drafted"]},{"number":2,"title":"methods","outline_id":"O2","argument_element":"method","authorship_declared":True,"changelog":["v1 drafted"]},{"number":3,"title":"results","outline_id":"O3","argument_element":"result","authorship_declared":True,"changelog":["v1 drafted"]},{"number":4,"title":"discussion","outline_id":"O4","argument_element":"discussion","conclusions":[{"statement":"coating raises uptake rate","direction":"increases"}],"changelog":["v1 drafted"]},{"number":5,"title":"limits","outline_id":"O5","argument_element":"limitation","authorship_declared":True,
     "changelog":["v1 drafted"]}]},
 "dissemination": {"audience":"public","evidence":["doe2020"],
   "text":"A porous coating raises uptake 3-fold [doe2020].","limitations":"only one material tested",
   "source_text":"Uptake rose 3-fold under the coating.",
   "key_conclusions":["A porous coating raises uptake 3-fold"],
   "changes":[{"action":"replaced technical terms with plain language","reason":"audience is public"}]},
 "mindmap": {"max_depth":4,
   "nodes":[{"id":"r","label":"paper"},{"id":"a","label":"problem","parent":"r","evidence_exempt":True},
            {"id":"b","label":"method","parent":"r","evidence":"Sec 2","kind":"fact"},
            {"id":"c","label":"finding","parent":"r","evidence":"Fig 3b","kind":"fact"}],
   "edges":[{"from":"b","to":"c","kind":"support","basis":"p.7"}]},
}

DEFECTS = [
 ("ce_no_cond",   "conclusion_extract", lambda: (d(BASE["conclusion_extract"], conclusions=[{**BASE["conclusion_extract"]["conclusions"][0], "condition":""}]), ["extract.missing_condition"])),
 ("ce_no_loc",    "conclusion_extract", lambda: (d(BASE["conclusion_extract"], conclusions=[{**BASE["conclusion_extract"]["conclusions"][0], "locator":""}]), ["extract.missing_locator"])),
 ("ce_hedge",     "conclusion_extract", lambda: (d(BASE["conclusion_extract"], conclusions=[{**BASE["conclusion_extract"]["conclusions"][0], "claim":"Coating always raises uptake","hedged":False}]), ["extract.hedge_dropped"])),
 ("cv_no_ev",     "claim_verify", lambda: (d(BASE["claim_verify"], claims=[{**BASE["claim_verify"]["claims"][0], "evidence":[]}]), ["verify.no_evidence"])),
 ("cv_unrelated", "claim_verify", lambda: (d(BASE["claim_verify"], claims=[{**BASE["claim_verify"]["claims"][0], "evidence":[{"source":"doe2020","quote":"samples were stored at four degrees in the dark"}]}]), ["verify.evidence_unrelated"])),
 ("cv_support",   "claim_verify", lambda: (d(BASE["claim_verify"], claims=[{**BASE["claim_verify"]["claims"][0], "support":""}]), ["verify.support_undeclared"])),
 ("cd_no_schema", "compare_docs", lambda: (d(BASE["compare_docs"], fields=[]), ["compare.no_schema"])),
 ("cd_missing",   "compare_docs", lambda: (d(BASE["compare_docs"], documents=[{"id":"A","fields":{"bandgap":"3.20 eV"}},{"id":"B","fields":{}}]), ["compare.field_missing"])),
 ("fo_braces",    "formula", lambda: (d(BASE["formula"], formulas=[{**BASE["formula"]["formulas"][0], "latex":"E = h c / \\lambda{"}]), ["formula.unbalanced_braces"])),
 ("fo_dim",       "formula", lambda: (d(BASE["formula"], formulas=[{**BASE["formula"]["formulas"][0], "lhs_unit":"J","rhs_unit":"Pa"}]), ["formula.dimension_mismatch"])),
 ("fo_undef",     "formula", lambda: (d(BASE["formula"], formulas=[{**BASE["formula"]["formulas"][0], "variables":[{"name":"E","definition":"","source":"paper"}]}]), ["formula.variable_undefined"])),
 ("rp_no_env",    "reproduce", lambda: (d(BASE["reproduce"], checklist={**BASE["reproduce"]["checklist"], "environment":{"dependencies":"pinned"}}), ["repro.environment_incomplete"])),
 ("rp_param_src", "reproduce", lambda: (d(BASE["reproduce"], checklist={**BASE["reproduce"]["checklist"], "parameters":[{"name":"lr","source":""}]}), ["repro.parameter_source_undeclared"])),
 ("rp_no_tol",    "reproduce", lambda: (d(BASE["reproduce"], checklist={**BASE["reproduce"]["checklist"], "results":{}}), ["repro.no_tolerance"])),
 ("qa_uncited",   "qa", lambda: (d(BASE["qa"], answers=[{**BASE["qa"]["answers"][0], "cites":[]}]), ["qa.uncited_answer"])),
 ("qa_unknown",   "qa", lambda: (d(BASE["qa"], answers=[{**BASE["qa"]["answers"][0], "cites":["zzz"]}]), ["qa.unknown_evidence"])),
 ("pd_missing",   "paper_draft", lambda: (d(BASE["paper_draft"], draft="1 Introduction\nThe coating raises uptake [doe2020] {M1}.\n2 Methods\n"), ["pd.sections_missing"])),
 ("pd_uncited",   "paper_draft", lambda: (d(BASE["paper_draft"], draft="1 Introduction\nUptake increased with coating.\n2 Methods\n3 Results\n"), ["pd.uncited_claim"])),
 ("sl_multi",     "structure_logic", lambda: (d(BASE["structure_logic"], paragraphs=[{"section":"intro","text":"a","claims":[{"claim":"x","support":"F1"},{"claim":"y","support":"F2"}]}]), ["struct.multiple_claims"])),
 ("sl_orphan",    "structure_logic", lambda: (d(BASE["structure_logic"], paragraphs=[{"section":"intro","text":"a","claims":[]}]), ["struct.orphan_paragraph"])),
 ("rd_causal",    "results_discussion", lambda: (d(BASE["results_discussion"], design="observational",
        discussion_text="The coating causes higher uptake [doe2020]."), ["rd.causal_overreach"])),
 ("rd_unitless",  "results_discussion", lambda: (d(BASE["results_discussion"],
        results_text="We observed 7 samples with no change."), ["rd.unitless_number"])),
 ("pr_no_measure","proposal", lambda: (d(BASE["proposal"], objectives=[{"id":"O1","outcome":"faster uptake","content_ref":"C1"}]), ["prop.aim_without_measure"])),
 ("pr_no_tl",     "proposal", lambda: (d(BASE["proposal"], timeline=[{"period":"Y1"}]), ["prop.milestone_missing"])),
 ("mm_edge_dangling", "mindmap", lambda: (d(BASE["mindmap"],
     edges=BASE["mindmap"]["edges"] + [{"from":"c","to":"zz","kind":"causal","basis":"p.8"}]),
     ["map.edge_dangling"])),
 ("mm_edge_notype", "mindmap", lambda: (d(BASE["mindmap"],
     edges=BASE["mindmap"]["edges"] + [{"from":"c","to":"b","basis":"p.8"}]),
     ["map.edge_type_missing"])),
 ("mm_edge_nobasis", "mindmap", lambda: (d(BASE["mindmap"],
     edges=BASE["mindmap"]["edges"] + [{"from":"c","to":"b","kind":"causal"}]),
     ["map.edge_no_basis"])),
 ("mm_kind_missing", "mindmap", lambda: (d(BASE["mindmap"],
     nodes=BASE["mindmap"]["nodes"] + [{"id":"d","label":"risk","parent":"c","evidence":"p.9"}]),
     ["map.kind_undeclared"])),
 ("mm_decorative", "mindmap", lambda: (d(BASE["mindmap"],
     nodes=BASE["mindmap"]["nodes"] + [{"id":"x","label":"其他","parent":"c","evidence_exempt":True}]),
     ["map.decorative_label"])),
 ("ld_dangling",  "longdoc", lambda: (d(BASE["longdoc"], chapters=[
     {**BASE["longdoc"]["chapters"][0], "crossrefs": [9]},
     BASE["longdoc"]["chapters"][1]]), ["long.dangling_crossref"])),
]

# False-positive guards: standard scientific prose that must stay silent. These are the
# patterns that once pushed an agent into damaging a correct draft (deleting p-values,
# attaching citations that do not exist, rewriting "the results in Table 1"). A guard that
# reports anything is a defect of the same kind as a missed defect.
FP_CLEAN = [
 ("fp_rd_pointer", "results_discussion", lambda: d(BASE["results_discussion"],
   results_text="The results in Table 1 show a three-fold rise (p < 0.01, t-test). "
                "Arm B showed no change.")),
 ("fp_rd_stats", "results_discussion", lambda: d(BASE["results_discussion"],
   results_text="Uptake rose three-fold in the coated group (p < 0.01, t(24) = 3.2, "
                "n = 6, R² = 0.87). Arm B showed no change.")),
 ("fp_rd_dataref", "results_discussion", lambda: d(BASE["results_discussion"],
   literature=[{"key": "doe2020", "agrees": True}],
   comparisons=[{"name": "coated vs control", "significant": True, "strength": "strong"}],
   discussion_text="This increase is consistent with the dose dependence shown in Fig. 3.")),
 ("fp_pd_pointer", "paper_draft", lambda: d(BASE["paper_draft"], design="observational",
   draft="1 Introduction\nThe coating relates to uptake [doe2020] {M1}.\n2 Methods\n"
         "We measured 3 mM samples {M2}.\n3 Results\n"
         "The results in Table 1 show a three-fold rise (p < 0.05) {M1} (Fig 1).\n")),
 ("fp_pd_material", "paper_draft", lambda: d(BASE["paper_draft"],
   draft="1 Introduction\nThe coating raises uptake [doe2020] {M1}.\n2 Methods\n"
         "We measured 3 mM samples {M2}.\n3 Results\n"
         "Uptake rose three-fold {M1} (Fig 1), tested at p < 0.05.\n")),
 ("fp_qa_stats", "qa", lambda: d(BASE["qa"],
   answers=[{"question": "what is the uptake rate change",
             "answer": "the uptake rate increased three-fold with the porous coating "
                       "(p < 0.05)", "cites": ["e1"]}])),
 ("fp_diss_stats", "dissemination", lambda: d(BASE["dissemination"],
   source_text="Uptake rose 3-fold under the coating (p < 0.05) in 2020.")),
 ("fp_map_labels", "mindmap", lambda: d(BASE["mindmap"],
   nodes=BASE["mindmap"]["nodes"] + [{"id":"m","label":"方法","parent":"b","evidence":"p.3","kind":"fact"},
                                     {"id":"n","label":"aims","parent":"c","evidence":"p.4","kind":"summary"}],
   edges=BASE["mindmap"]["edges"])),
]

def main() -> int:
    rows = []
    for sec, base in BASE.items():
        f, st, _ = S.run(copy.deepcopy(base), sec)
        # Every severity, not just high/medium: a low finding still leaves the run in
        # 'review', so a baseline that trips one is not clean.
        spurious = [x['rule'] for x in f]
        rows.append({'scenario': 'clean:' + sec, 'section': sec, 'expected': [],
                     'fired': sorted({x['rule'] for x in f}), 'spurious': spurious,
                     'pass': not spurious})
        print(('PASS' if not spurious else 'FAIL') + '  clean:' + sec.ljust(22) + ' spurious=' + str(spurious))
    for name, sec, builder in DEFECTS:
        spec, expect = builder()
        f, st, _ = S.run(spec, sec)
        fired = {x['rule'] for x in f}
        missing = [r for r in expect if r not in fired]
        rows.append({'scenario': name, 'section': sec, 'expected': expect,
                     'fired': sorted(fired), 'missing': missing, 'pass': not missing})
        print(('PASS' if not missing else 'FAIL') + '  ' + name.ljust(22) + ' missing=' + str(missing))
    for name, sec, builder in FP_CLEAN:
        spec = builder()
        f, st, _ = S.run(spec, sec)
        spurious = [x['rule'] for x in f]
        rows.append({'scenario': name, 'section': sec, 'expected': [],
                     'fired': sorted({x['rule'] for x in f}), 'spurious': spurious,
                     'pass': not spurious})
        print(('PASS' if not spurious else 'FAIL') + '  ' + name.ljust(22) + ' spurious=' + str(spurious))
    passed = sum(1 for r in rows if r['pass'])
    (Path(__file__).resolve().parent / 'report_sections.json').write_text(
        json.dumps({'schema_version': 'sections-bench/v1', 'scenarios': rows,
                    'totals': {'passed': passed, 'of': len(rows)}}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print()
    print(str(passed) + '/' + str(len(rows)) + ' pass')
    return 0 if passed == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
