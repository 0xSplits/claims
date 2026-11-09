#!/usr/bin/env python3
"""Build a claim deck: one HTML page from a claims JSON file.

Usage: python3 build.py claims.json [-o deck.html]

Validates the JSON against the grammar in schema.md, then inlines the
renderer, styles, and data into template.html. No dependencies beyond the
standard library. Exit code 1 and a list of problems on invalid input.
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
GRADES = {"proven", "partial", "asserted", "gap", "deviation"}
NODE_TYPES = {"process", "decision", "terminal", "note"}
NODE_STATUS = {"same", "added", "changed", "removed", "gap", "deferred"}
EDGE_STATUS = {"same", "added", "removed", "covered", "uncovered", "async", "gap", "deferred"}
BADGES = {"✓", "!", "×"}
MAX_NODES = 12


def validate(deck):
    problems = []
    for key in ("title", "repo", "sha", "claims"):
        if key not in deck:
            problems.append(f"deck: missing '{key}'")
    if not isinstance(deck.get("claims"), list) or not deck.get("claims"):
        problems.append("deck: 'claims' must be a non-empty list")
        return problems
    if len(str(deck.get("sha", ""))) < 7:
        problems.append("deck: 'sha' should be the full or abbreviated PR head commit")

    def check_links(arr, where):
        for link in arr or []:
            if "path" not in link or "line" not in link:
                problems.append(f"{where}: link needs 'path' and 'line'")

    for i, claim in enumerate(deck["claims"], 1):
        where = f"claim {i}"
        for key in ("grade", "title", "enforced"):
            if not claim.get(key):
                problems.append(f"{where}: missing '{key}'")
        if claim.get("grade") not in GRADES:
            problems.append(f"{where}: grade must be one of {sorted(GRADES)}")
        if claim.get("grade") == "proven" and not claim.get("proofLinks"):
            problems.append(f"{where}: a 'proven' claim needs at least one proofLink to the test")
        if claim.get("grade") in {"asserted", "gap"} and claim.get("proofLinks") and claim.get("proof", "").lower().startswith("none"):
            problems.append(f"{where}: proof says 'None' but has proofLinks; describe what the linked test does and does not assert")
        check_links(claim.get("links"), where)
        check_links(claim.get("proofLinks"), where)

        diagram = claim.get("diagram")
        if not diagram or not diagram.get("nodes"):
            problems.append(f"{where}: needs a diagram with nodes")
            continue
        nodes, edges = diagram["nodes"], diagram.get("edges", [])
        ids = [n.get("id") for n in nodes]
        if len(set(ids)) != len(ids):
            problems.append(f"{where}: duplicate node ids")
        if len(nodes) > MAX_NODES:
            problems.append(f"{where}: {len(nodes)} nodes; keep a claim's diagram to {MAX_NODES} or fewer")
        cells = {}
        for n in nodes:
            for key in ("id", "label", "col", "row"):
                if key not in n:
                    problems.append(f"{where}: node needs '{key}'")
            if n.get("type", "process") not in NODE_TYPES:
                problems.append(f"{where}: node {n.get('id')} type must be one of {sorted(NODE_TYPES)}")
            if n.get("status", "same") not in NODE_STATUS:
                problems.append(f"{where}: node {n.get('id')} status must be one of {sorted(NODE_STATUS)}")
            if n.get("badge") and n["badge"] not in BADGES:
                problems.append(f"{where}: node {n.get('id')} badge must be one of {sorted(BADGES)}")
            cell = (n.get("col"), n.get("row"))
            if cell in cells:
                problems.append(f"{where}: nodes {cells[cell]} and {n.get('id')} share grid cell {cell}")
            cells[cell] = n.get("id")
        idset = set(ids)
        for e in edges:
            if e.get("from") not in idset:
                problems.append(f"{where}: edge from unknown node {e.get('from')}")
            if e.get("to") not in idset:
                problems.append(f"{where}: edge to unknown node {e.get('to')}")
            if e.get("status", "same") not in EDGE_STATUS:
                problems.append(f"{where}: edge {e.get('from')}→{e.get('to')} status must be one of {sorted(EDGE_STATUS)}")
        lit = [n for n in nodes if n.get("status", "same") != "same" and not n.get("dim")] + [e for e in edges if e.get("status", "same") != "same" and not e.get("dim")]
        if not lit:
            problems.append(f"{where}: nothing in the diagram is lit; give the claim's path a status other than 'same'")
        for lane in diagram.get("lanes", []):
            if "label" not in lane or "cols" not in lane or len(lane["cols"]) != 2:
                problems.append(f"{where}: lane needs 'label' and 'cols': [first, last]")
        for region in diagram.get("regions", []):
            if "label" not in region or "cols" not in region or "rows" not in region:
                problems.append(f"{where}: region needs 'label', 'cols', and 'rows'")
    return problems


def build(deck):
    template = (HERE / "template.html").read_text()
    css = (HERE / "flow.css").read_text()
    js = (HERE / "flow.js").read_text()
    # </script> inside a JSON string would end the script block early.
    data = json.dumps(deck, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("{{TITLE}}", deck["title"]).replace("{{CSS}}", css).replace("{{JS}}", js).replace("{{DATA}}", data)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("claims", help="claims JSON file (see schema.md)")
    parser.add_argument("-o", "--out", help="output HTML path (default: <claims stem>.html)")
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    args = parser.parse_args()

    src = pathlib.Path(args.claims)
    deck = json.loads(src.read_text())
    problems = validate(deck)
    if problems:
        print(f"{len(problems)} problem(s) in {src}:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        sys.exit(1)
    grades = {}
    for c in deck["claims"]:
        grades[c["grade"]] = grades.get(c["grade"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(grades.items()))
    if args.check:
        print(f"OK: {len(deck['claims'])} claims ({summary})")
        return
    out = pathlib.Path(args.out) if args.out else src.with_suffix(".html")
    out.write_text(build(deck))
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB): {len(deck['claims'])} claims ({summary})")


if __name__ == "__main__":
    main()
