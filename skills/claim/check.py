#!/usr/bin/env python3
"""Check a claim tree: validate it, grade every node, print the qualified root claim.

Usage: python3 check.py tree.json [--html tree.html]
       python3 check.py tree.json --digest NODE
       python3 check.py --self-test

The grammar and rollup rules are in schema.md. No dependencies beyond the
standard library. Exit code 1 and a list of problems on invalid input.
"""
import argparse
import collections
import datetime
import hashlib
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
RANK = ["gap", "open", "asserted", "partial", "proven"]
LEAF_GRADES = {"proven", "partial", "asserted", "gap"}
ENFORCERS = {"test", "lint", "type", "agent", "review", "comment"}
MECHANICAL = {"test", "lint", "type"}
KINDS = ("children", "grade", "ref")
MAX_CHILDREN = 7


def weakest(*grades):
    return min(grades, key=RANK.index)


def digest(claims, cid):
    """Fingerprint of a branch's wording, so a reworded child voids the review."""
    node = claims[cid]
    text = [node.get("claim")] + [claims.get(k, {}).get("claim") for k in node["children"]]
    return hashlib.sha256(json.dumps(text).encode()).hexdigest()[:12]


def review_state(claims, cid):
    reviewed = claims[cid].get("reviewed")
    if not reviewed:
        return "not reviewed"
    return "reviewed" if reviewed.get("digest") == digest(claims, cid) else "changed since review"


def pending(node):
    try:
        return datetime.date.fromisoformat(node["liveFrom"]) > datetime.date.today()
    except (KeyError, TypeError, ValueError):
        return False


def validate(tree, where):
    claims = tree.get("claims")
    if not isinstance(claims, dict) or tree.get("root") not in claims:
        return [f"{where}: needs 'claims' and a 'root' that names one of them"]
    problems = []
    for cid, node in claims.items():
        at = f"{where}#{cid}"
        if not node.get("claim"):
            problems.append(f"{at}: missing 'claim'")
        kinds = [k for k in KINDS if k in node]
        if len(kinds) > 1:
            problems.append(f"{at}: has {' and '.join(kinds)}; a node is one kind")
        if "children" in node:
            kids = node["children"]
            if not 1 <= len(kids) <= MAX_CHILDREN:
                problems.append(f"{at}: needs 1 to {MAX_CHILDREN} children, has {len(kids)}")
            problems += [f"{at}: child '{k}' does not exist" for k in kids if k not in claims]
            if not node.get("basis"):
                problems.append(f"{at}: a branch needs 'basis'")
            reviewed = node.get("reviewed")
            if reviewed is not None and not all(reviewed.get(f) for f in ("by", "date", "digest")):
                problems.append(f"{at}: 'reviewed' needs 'by', 'date', and 'digest'")
        if "grade" in node:
            grade, by, evidence = node["grade"], node.get("enforcedBy"), node.get("evidence", [])
            if grade not in LEAF_GRADES:
                problems.append(f"{at}: grade '{grade}' is not one of {sorted(LEAF_GRADES)}")
            if grade != "gap" and by not in ENFORCERS:
                problems.append(f"{at}: 'enforcedBy' must be one of {sorted(ENFORCERS)}")
            if grade == "proven" and by not in MECHANICAL:
                problems.append(f"{at}: proven needs enforcedBy test, lint, or type, not '{by}'")
            if grade == "proven" and not evidence:
                problems.append(f"{at}: proven needs an evidence link")
            if grade in ("partial", "gap") and not node.get("note"):
                problems.append(f"{at}: {grade} needs a 'note' naming what is missing")
            if "liveFrom" in node:
                try:
                    datetime.date.fromisoformat(node["liveFrom"])
                except (TypeError, ValueError):
                    problems.append(f"{at}: 'liveFrom' must be a YYYY-MM-DD date")
        for field in ("evidence", "source"):
            for link in node.get(field, []):
                # A source may be a web page, such as another company's docs; evidence is always code.
                if field == "source" and str(link.get("url", "")).startswith("https://"):
                    continue
                missing = [f for f in ("repo", "sha", "path", "line") if f not in link]
                if missing:
                    problems.append(f"{at}: {field} link missing {', '.join(missing)}")

    seen = set()

    def reach(cid):
        if cid in seen or cid not in claims:
            return
        seen.add(cid)
        for k in claims[cid].get("children", []):
            reach(k)

    reach(tree["root"])
    problems += [f"{where}#{cid}: nothing reaches this node" for cid in claims if cid not in seen]
    return problems


def check(path):
    """Grade the tree at path and every tree it refs. Returns (problems, grades, trees)."""
    trees, grades, problems = {}, {}, []

    def tree_at(p):
        if p not in trees:
            try:
                trees[p] = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError) as e:
                problems.append(f"{p.name}: {e}")
                trees[p] = None
                return None
            found = validate(trees[p], p.name)
            problems.extend(found)
            if found and "claims" not in trees[p]:
                trees[p] = None
        return trees[p]

    def grade(p, cid, stack):
        key = (p, cid)
        if key in grades:
            return grades[key]
        if key in stack:
            problems.append(f"{p.name}#{cid}: cycle")
            return "open"
        node = tree_at(p)["claims"][cid]
        inner = stack | {key}
        if "ref" in node:
            file, _, target = node["ref"].partition("#")
            ref_path = (p.parent / file).resolve()
            ref_tree = tree_at(ref_path) if ref_path.exists() else None
            target = target or (ref_tree or {}).get("root")
            if ref_tree is None or target not in ref_tree["claims"]:
                problems.append(f"{p.name}#{cid}: ref '{node['ref']}' does not resolve")
                g = "open"
            else:
                g = grade(ref_path, target, inner)
        elif "children" in node:
            kids = [grade(p, k, inner) for k in node["children"] if k in tree_at(p)["claims"]]
            g = weakest(*kids) if kids else "open"
            if review_state(tree_at(p)["claims"], cid) != "reviewed":
                g = weakest(g, "asserted")
        elif pending(node):
            g = "gap"
        else:
            g = node["grade"] if node.get("grade") in LEAF_GRADES else "open"
        grades[key] = g
        return g

    path = path.resolve()
    tree = tree_at(path)
    if tree is not None:
        grade(path, tree["root"], frozenset())
    return problems, grades, trees


def qualifiers(p, cid, grades, trees):
    claims = trees[p]["claims"]
    node = claims[cid]
    if grades[(p, cid)] == "proven":
        return []
    if "children" not in node:
        why = f"live from {node['liveFrom']}" if pending(node) else grades[(p, cid)]
        return [f"{node['claim']} ({why})"]
    state = review_state(claims, cid)
    own = [] if state == "reviewed" else [f"{node['claim']} (definition {state})"]
    return own + [q for k in node["children"] for q in qualifiers(p, k, grades, trees)]


def report(path):
    path = path.resolve()
    problems, grades, trees = check(path)
    if problems:
        return problems, None, None
    tree = trees[path]
    claims = tree["claims"]

    def render(cid, depth):
        node = claims[cid]
        ref = f"  -> {node['ref']}" if "ref" in node else ""
        line = f"{'  ' * depth}{grades[(path, cid)]:<9} {cid}: {node['claim']}{ref}"
        return [line] + [l for k in node.get("children", []) for l in render(k, depth + 1)]

    root = claims[tree["root"]]["claim"]
    qs = list(dict.fromkeys(qualifiers(path, tree["root"], grades, trees)))
    statement = f"{root}, except: {'; '.join(qs)}." if qs else f"{root}."
    tally = collections.Counter(grades[(path, cid)] for cid, node in claims.items() if "children" not in node)
    counts = ", ".join(f"{tally[g]} {g}" for g in reversed(RANK) if tally[g])
    page = {
        "title": f"{path.stem.replace('-', ' ').title()} Claims",
        "statement": statement,
        "tally": {g: tally[g] for g in reversed(RANK) if tally[g]},
        "tree": nested(path, tree["root"], grades, trees),
    }
    return [], "\n".join(render(tree["root"], 0) + ["", f"Grades: {counts}", "", statement]), page


def nested(p, cid, grades, trees):
    """The node and everything below it, refs inlined, in the shape tree.html draws."""
    node = trees[p]["claims"][cid]
    if "ref" in node:
        file, _, target = node["ref"].partition("#")
        ref_path = (p.parent / file).resolve()
        return {**nested(ref_path, target or trees[ref_path]["root"], grades, trees), "ref": node["ref"]}
    grade = grades[(p, cid)]
    out = {
        "id": cid,
        "name": node["claim"],
        "grade": grade,
        "note": node.get("note"),
        "basis": node.get("basis"),
        "enforcedBy": node.get("enforcedBy"),
        "reviewed": node.get("reviewed"),
        "review": review_state(trees[p]["claims"], cid) if "children" in node else None,
        "liveFrom": node.get("liveFrom"),
        "evidence": [github(link) for link in node.get("evidence", [])],
        "source": [github(link) for link in node.get("source", [])],
        "collapsed": grade == "proven",
        "children": [nested(p, k, grades, trees) for k in node.get("children", [])],
    }
    return {k: v for k, v in out.items() if v not in (None, [])}


def github(link):
    if "url" in link:
        return {"label": link.get("label") or link["url"], "url": link["url"]}
    return {
        "label": link.get("label") or f"{link['path']}:{link['line']}",
        "url": f"https://github.com/{link['repo']}/blob/{link['sha']}/{link['path']}#L{link['line']}",
    }


def build_html(page):
    template = (HERE / "tree.html").read_text()
    # </script> inside a JSON string would end the script block early.
    data = json.dumps(page, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("{{TITLE}}", page["title"]).replace("{{DATA}}", data)


def self_test():
    good = {
        "root": "a",
        "claims": {
            "a": {"claim": "A", "basis": "x", "children": ["b", "c", "d"], "reviewed": {"by": "t", "date": "d"}},
            "b": {
                "claim": "B",
                "grade": "proven",
                "enforcedBy": "test",
                "evidence": [{"repo": "r", "sha": "s", "path": "p", "line": 1}],
                "source": [{"url": "https://example.com/pricing"}],
            },
            "c": {"claim": "C", "basis": "x", "children": ["e"]},
            "d": {"claim": "D", "ref": "other.json#y"},
            "e": {"claim": "E", "grade": "partial", "enforcedBy": "test", "note": "n"},
        },
    }
    good["claims"]["a"]["reviewed"]["digest"] = digest(good["claims"], "a")
    other = {
        "root": "x",
        "claims": {
            "x": {"claim": "X", "basis": "x", "children": ["y"], "reviewed": {"by": "t", "date": "d"}},
            "y": {"claim": "Y", "grade": "proven", "enforcedBy": "lint", "evidence": [{"repo": "r", "sha": "s", "path": "p", "line": 1}]},
        },
    }
    other["claims"]["x"]["reviewed"]["digest"] = digest(other["claims"], "x")
    bad = {
        "root": "a",
        "claims": {
            "a": {"claim": "A", "children": ["a", "z"], "reviewed": {"by": "t", "date": "d"}},
            "b": {"claim": "B", "grade": "proven", "enforcedBy": "agent", "liveFrom": "soon", "source": [{"repo": "r"}]},
        },
    }
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        for name, data in (("good.json", good), ("other.json", other), ("bad.json", bad)):
            (d / name).write_text(json.dumps(data))
        problems, grades, _ = check(d / "good.json")
        assert not problems, problems
        g = {cid: grades[(d.resolve() / "good.json", cid)] for cid in good["claims"]}
        assert g == {"a": "asserted", "b": "proven", "c": "asserted", "d": "proven", "e": "partial"}, g
        _, out, page = report(d / "good.json")
        assert out.endswith("A, except: C (definition not reviewed); E (partial)."), out
        ref = page["tree"]["children"][2]
        assert (ref["id"], ref["ref"], ref["collapsed"]) == ("y", "other.json#y", True), ref
        assert '"grade": "partial"' in build_html(page)
        assert '"url": "https://example.com/pricing"' in build_html(page)

        good["claims"]["b"].update(claim="B reworded", liveFrom="2999-01-01")
        good["claims"]["e"]["liveFrom"] = "2000-01-01"
        (d / "good.json").write_text(json.dumps(good))
        _, out, _ = report(d / "good.json")
        assert out.endswith(
            "A, except: A (definition changed since review); B reworded (live from 2999-01-01); "
            "C (definition not reviewed); E (partial)."
        ), out
        problems, _, _ = check(d / "bad.json")
        for expected in ("needs 'basis'", "'digest'", "'liveFrom'", "'z' does not exist", "nothing reaches", "not 'agent'", "evidence link", "source link", "cycle"):
            assert any(expected in p for p in problems), (expected, problems)
    print("self-test passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tree", nargs="?", type=pathlib.Path)
    parser.add_argument("--html", type=pathlib.Path, help="also write an interactive tree page here")
    parser.add_argument("--digest", metavar="NODE", help="print the digest to store in NODE's 'reviewed'")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.tree:
        parser.error("give a tree file or --self-test")
    if args.digest:
        return print(digest(json.loads(args.tree.read_text())["claims"], args.digest))
    problems, out, page = report(args.tree)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        sys.exit(1)
    print(out)
    if args.html:
        args.html.write_text(build_html(page))
        print(f"\nWrote {args.html}")


if __name__ == "__main__":
    main()
