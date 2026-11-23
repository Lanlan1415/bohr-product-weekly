"""Functional bench for knowledge cards, reciprocal links, retrieval and idempotency."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import annotate
import reader

HERE = Path(__file__).resolve().parent
CLI = HERE / "annotate_cli.py"
DOC = ("1 Introduction\nPorous coatings raise the uptake rate three-fold.\n\n"
       "2 Methods\nWe measured uptake at 25 C with six replicates per arm.\n\n"
       "3 Discussion\nOnly one coating thickness was tested.")


def make(tmp, name="cards"):
    ws = reader.Workspace(tmp / (name + ".json"))
    text = "\n".join(line for line in DOC.splitlines() if line.strip())
    ws.add_document("paper", text, [2, 4])
    ann = annotate.Annotator(ws)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "color": "yellow",
         "note": "结果：uptake 提高三倍", "tags": ["吸收率", "uptake"],
         "topics": ["涂层"], "key_concepts": ["吸收速率"], "entities": ["coating"],
         "source_time": "2024-05-02"},
        {"quote": "six replicates", "page": 2, "type": "underline", "color": "red",
         "note": "结果：uptake 与六次重复一致", "tags": ["重复性"],
         "topics": ["实验设计"], "key_concepts": ["重复"], "entities": ["replicate"],
         "source_time": "2024-06-03"},
    ])
    return ws, ann


def hashes(path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.iterdir()) if p.is_file()}


def scenarios():
    sc = []
    add = lambda name, fn: sc.append((name, fn))

    def card_grounding(tmp):
        _, ann = make(tmp)
        notes = ann.structured_notes()
        card = ann.knowledge_cards(notes)[0]
        n = next(n for n in notes if n["quote"] == "three-fold")
        card = next(c for c in ann.knowledge_cards(notes) if c["annotation_ids"] == [n["annotation_id"]])
        return (card["source_excerpt"] == "three-fold" and card["reader_comment"] == "结果：uptake 提高三倍"
                and card["summary_kind"] == "reader_comment" and card["anchor"] == n["anchor"]
                and card["key_concepts"] == ["coating", "uptake", "吸收率", "吸收速率"])

    add("card_separates_source_and_reader_comment", card_grounding)

    def topics_entities(tmp):
        _, ann = make(tmp)
        cards = ann.knowledge_cards(ann.structured_notes())
        c1 = next(c for c in cards if c["doc_id"] == "paper" and c["source_excerpt"] == "three-fold")
        c2 = next(c for c in cards if c["source_excerpt"] == "six replicates")
        return (c1["topics"] == ["涂层"] and c1["entities"] == ["coating"]
                and c1["source_time"] == "2024-05-02" and c2["topics"] == ["实验设计"])

    add("topics_concepts_entities_preserved", topics_entities)

    def reciprocal(tmp):
        _, ann = make(tmp)
        notes = ann.structured_notes()
        links = ann.links(notes)
        cards = ann.knowledge_cards(notes, links)
        if len(links) != 1:
            return False
        a, b = links[0]["between_cards"]
        ca = next(c for c in cards if c["card_id"] == a)
        cb = next(c for c in cards if c["card_id"] == b)
        return (links[0]["bidirectional"] and links[0]["directions"] == [[a, b], [b, a]]
                and ca["related_card_ids"] == [b] and cb["related_card_ids"] == [a]
                and ca["backlinks"] == [b] and cb["backlinks"] == [a]
                and ca["wikilinks"] == ["[[" + b + "]]"])

    add("forward_links_and_backlinks_symmetric", reciprocal)

    def version_backlinks(tmp):
        ws, ann = make(tmp)
        v2 = DOC.replace("six replicates", "eight replicates")
        ws.add_document("paper-v2", "\n".join(x for x in v2.splitlines() if x.strip()), [2, 4])
        ann.ingest("paper-v2", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
        notes = ann.structured_notes()
        cards = ann.knowledge_cards(notes)
        related = [c for c in cards if c["source_excerpt"] == "three-fold"]
        return len(related) == 2 and all(c["backlinks"] for c in related)

    add("version_siblings_have_backlinks", version_backlinks)

    def filters(tmp):
        _, ann = make(tmp)
        notes = ann.structured_notes()
        checks = [
            ann.retrieve("三倍", notes, tag="吸收率"),
            ann.retrieve("三倍", notes, topic="涂层"),
            ann.retrieve("三倍", notes, concept="吸收速率"),
            ann.retrieve("三倍", notes, entity="coating"),
            ann.retrieve("三倍", notes, since="2024-01-01", until="2024-05-31"),
        ]
        empty = ann.retrieve("三倍", notes, topic="不存在")
        later = ann.retrieve("三倍", notes, since="2025-01-01")
        correct = all(len(h) == 1 and h[0]["quote"] == "three-fold" for h in checks)
        return correct and empty == [] and later == []

    add("tag_topic_concept_entity_time_filters", filters)

    def source_time_no_fabrication(tmp):
        ws = reader.Workspace(tmp / "nodate.json")
        ws.add_document("d", "保存温度为 4 C。", [])
        ann = annotate.Annotator(ws)
        ann.ingest("d", [{"quote": "4 C", "note": "结果：四度"}])
        notes = ann.structured_notes()
        card = ann.knowledge_cards(notes)[0]
        return (card["source_time"] is None and card["anchor"]["page"] == 1
                and ann.retrieve("四度", notes, since="2024-01-01") == [])

    add("missing_source_time_not_invented", source_time_no_fabrication)

    def followups(tmp):
        ws, ann = make(tmp)
        ann.ingest("paper", [{"quote": "Only one coating thickness", "page": 3,
                              "kind": "doubt", "note": "存疑：单一厚度能否外推"}])
        cards = ann.knowledge_cards(ann.structured_notes())
        actions = {a["card_id"]: a for a in ann.follow_up_actions(cards)}
        doubt = next(c for c in cards if c["note_kind"] == "doubt")
        normal = next(c for c in cards if c["source_excerpt"] == "three-fold")
        return (actions[doubt["card_id"]]["action"] == "verify-against-source"
                and actions[normal["card_id"]]["action"] == "scheduled-retrieval-review"
                and all(a["review_schedule"]["state"] == "not_started"
                        and a["review_schedule"]["due_date"] is None for a in actions.values()))

    add("followup_and_unstarted_review_schedule", followups)

    def export(tmp):
        _, ann = make(tmp)
        out = tmp / "export"
        res = ann.export(out)
        expected = {"notes.md", "cards.md", "review.csv", "index.json"}
        index = json.loads((out / "index.json").read_text(encoding="utf-8"))
        cards_md = (out / "cards.md").read_text(encoding="utf-8")
        with (out / "review.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return (expected == {p.name for p in out.iterdir()} and res["cards"] == 2
                and len(index["cards"]) == 2 and len(index["follow_up_actions"]) == 2
                and "backlinks: [[" in cards_md and len(rows) == 2
                and all(r["state"] == "not_started" and r["due_date"] == "" for r in rows))

    add("cards_notes_index_review_export", export)

    def store_idempotence(tmp):
        ws, ann = make(tmp)
        first = ({"quote": "three-fold", "page": 1, "type": "highlight", "color": "yellow",
                  "note": "结果：uptake 提高三倍", "tags": ["吸收率", "uptake"],
                  "topics": ["涂层"], "key_concepts": ["吸收速率"], "entities": ["coating"],
                  "source_time": "2024-05-02"},)
        ann.ingest("paper", list(first))
        ws.save()
        before = ws.path.read_bytes()
        ann.ingest("paper", list(first))
        ws.save()
        after = ws.path.read_bytes()
        return before == after

    add("workspace_byte_idempotent_reingest", store_idempotence)

    def edits_have_diff(tmp):
        ws = reader.Workspace(tmp / "edit.json")
        ws.add_document("paper", "\n".join(line for line in DOC.splitlines() if line.strip()), [2, 4])
        ann = annotate.Annotator(ws)
        base = {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：旧评论"}
        ann.ingest("paper", [base])
        updated = dict(base, note="结果：新评论", tags=["修订"])
        ann.ingest("paper", [updated])
        changes = ws.data.get("changes", [])
        events = list(ws.data.get("events", []))
        ann.ingest("paper", [updated])
        return (len(changes) == 1 and changes[0]["fields"]["note_text"]["old"] == "结果：旧评论"
                and changes[0]["fields"]["note_text"]["new"] == "结果：新评论"
                and ws.data["events"] == events)

    add("annotation_edit_field_diff_idempotent", edits_have_diff)

    def export_determinism(tmp):
        _, ann = make(tmp)
        ann.export(tmp / "e1")
        ann.export(tmp / "e2")
        return hashes(tmp / "e1") == hashes(tmp / "e2")

    add("all_exports_byte_deterministic", export_determinism)

    def result_exports_contract(tmp):
        store = tmp / "result-store.json"
        doc = tmp / "doc.txt"
        doc.write_text("1 Introduction\nPorous coatings raise uptake three-fold.\n\f2 Methods\nSix replicates.", encoding="utf-8")
        annotations = tmp / "annotations.json"
        annotations.write_text(json.dumps([{"quote": "three-fold", "page": 1,
            "type": "highlight", "note": "结果：三倍", "topics": ["涂层"]}]), encoding="utf-8")
        case = tmp / "case.json"
        case.write_text(json.dumps({"case_id": "cards-contract", "output_contract": {
            "annotations": [], "knowledge_cards": [], "follow_up": [], "deliverable": "cards",
            "undocumented_object": {"required": True}}}), encoding="utf-8")
        commands = [
            ["--store", str(store), "load", "--doc-id", "paper", "--doc-file", str(doc)],
            ["--store", str(store), "ingest", "--doc-id", "paper", "--annotations", str(annotations)],
            ["--store", str(store), "result", "--out", str(tmp / "result"), "--case", str(case)],
        ]
        procs = [subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI)] + cmd,
                                capture_output=True, text=True, timeout=120) for cmd in commands]
        if any(p.returncode != 0 or "Traceback" in p.stderr for p in procs):
            return False
        out = tmp / "result"
        r = json.loads((out / "result.json").read_text(encoding="utf-8"))
        return (r["case_id"] == "cards-contract" and r["annotations"] == r["notes"]
                and r["knowledge_cards"] == r["cards"] and r["follow_up"] == r["follow_up_actions"]
                and r["deliverable"] == "cards" and r["undocumented_object"] is None
                and all((out / name).exists() for name in ("notes.md", "cards.md", "review.csv", "index.json")))

    add("result_auto_export_and_contract_aliases", result_exports_contract)

    return sc


def main():
    rows = []
    for name, fn in scenarios():
        try:
            with tempfile.TemporaryDirectory() as td:
                ok = bool(fn(Path(td)))
            error = ""
        except Exception as exc:
            ok, error = False, f"{type(exc).__name__}: {exc}"
        rows.append({"scenario": name, "pass": ok, "error": error})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<48} {error}")
    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "knowledge-cards-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_knowledge_cards.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
