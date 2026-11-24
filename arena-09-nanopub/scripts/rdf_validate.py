"""Independent RDF Dataset/TriG integrity validation.

RDFLib is used when the preinstalled scientific image provides it. The builder
always runs the local lexical/graph checker too. Install is not a package
requirement; absence is reported, never disguised as an independent parse.

Usage: python rdf_validate.py nanopubs.trig [--json report.json]
Exit: 0 structurally valid, 1 invalid RDF/graph integrity, 2 usage/read error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

NP = "http://www.nanopub.org/nschema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def validate(path, import_rdflib=True):
    base = {"file": str(path), "format": "trig", "valid": False,
            "parser": "rdflib" if import_rdflib else "unavailable",
            "nanopublications": [], "errors": [], "warnings": []}
    if not import_rdflib:
        base["warnings"].append("RDFLib unavailable: no independent Dataset parse was claimed")
        return base
    try:
        from rdflib import Dataset, URIRef
        from rdflib.term import Node
    except ImportError:
        base["parser"] = "unavailable"
        base["warnings"].append("RDFLib unavailable: no independent Dataset parse was claimed")
        return base
    except Exception as exc:
        base["errors"].append("RDFLib import failed: %s" % str(exc)[:200])
        return base
    try:
        ds = Dataset(default_union=False)
        ds.parse(str(path), format="trig")
    except Exception as exc:
        base["errors"].append("TriG parse failed: %s" % str(exc)[:300])
        return base
    base["triple_count"] = len(ds)
    graph_by_id = {str(g.identifier): g for g in ds.graphs()}
    np_nodes = set()
    for graph in ds.graphs():
        np_nodes |= {s for s, p, o in graph if str(p) == RDF + "type" and str(o) == NP + "Nanopublication"}
    for node in sorted(np_nodes, key=str):
        row = {"root": str(node), "root_scope": "supplied or deterministic local URN; publication is not inferred"}
        links = {}
        for graph in ds.graphs():
            for name in ("hasAssertion", "hasProvenance", "hasPublicationInfo"):
                objects = [o for o in graph.objects(node, URIRef(NP + name))]
                if len(objects) > 1:
                    base["errors"].append("%s has multiple %s targets" % (node, name))
                if objects:
                    links[name] = objects[0]
        missing = [name for name in ("hasAssertion", "hasProvenance", "hasPublicationInfo") if name not in links]
        if missing:
            base["errors"].append("%s missing graph links: %s" % (node, ",".join(missing)))
        for name, target in links.items():
            if str(target) not in graph_by_id:
                base["errors"].append("%s target graph does not exist: %s" % (name, target))
            else:
                target_graph = graph_by_id[str(target)]
                count = len(target_graph)
                row[name] = {"graph": str(target), "triples": count}
                if count == 0:
                    base["errors"].append("%s target graph is empty: %s" % (name, target))
        if isinstance(links.get("hasAssertion"), URIRef):
            assertion = graph_by_id.get(str(links["hasAssertion"]))
            if assertion is not None:
                spo = [(s, p, o) for s, p, o in assertion if not str(p).startswith(RDF)]
                if not spo:
                    base["errors"].append("assertion graph has no scientific SPO triple: %s" % node)
                row["scientific_spo_triples"] = len(spo)
                for s, p, o in assertion.triples((None, URIRef(RDF + "subject"), None)):
                    pass
        base["nanopublications"].append(row)
    if not np_nodes:
        base["errors"].append("no np:Nanopublication root found")
    base["graph_count"] = len(graph_by_id)
    base["valid"] = not base["errors"]
    return base


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--json", dest="report")
    args = ap.parse_args(argv)
    path = Path(args.file)
    if not path.is_file():
        print(json.dumps({"valid": False, "errors": ["file not found"]}))
        return 2
    report = validate(path)
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
