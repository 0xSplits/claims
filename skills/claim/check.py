#!/usr/bin/env python3
"""Check a claim tree: validate it, grade every node, print the qualified root claim.

Usage: python3 check.py tree.json [--html page.html] [--include STATUS] [--probe]
       python3 check.py tree.json --stale [REV] [--repo CHECKOUT]
       python3 check.py tree.json --diff REV [--include STATUS]
       python3 check.py tree.json --digest NODE
       python3 check.py --self-test

The grammar and rollup rules are in schema.md, and diagrams are in diagram.md. No dependencies beyond the
standard library. Exit code 1 and a list of problems on invalid input, on a failed probe, on stale evidence, and on
a claim that grades worse than it did at REV.
"""
import argparse
import collections
import copy
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
RANK = ["gap", "open", "asserted", "partial", "proven"]
LEAF_GRADES = {"proven", "partial", "asserted", "gap"}
ENFORCERS = {"test", "lint", "type", "probe", "agent", "review", "comment"}
MECHANICAL = {"test", "lint", "type", "probe"}
# Whether we make the claim. Only 'shipped' counts toward its parent unless --include adds more.
STATUSES = ("shipped", "planned", "proposed", "cut")
PROBE_TIMEOUT = 300
KINDS = ("children", "grade", "ref")
MAX_CHILDREN = 7
NODE_TYPES = {"process", "decision", "terminal", "note"}
NODE_STATUS = {"same", "added", "changed", "removed", "gap", "deferred", "covered", "async"}
EDGE_STATUS = {"same", "added", "removed", "covered", "uncovered", "async", "gap", "deferred"}
BADGES = {"✓", "!", "×"}
MAX_NODES = 12


def weakest(*grades):
    return min(grades, key=RANK.index)


def digest(claims, cid):
    """Fingerprint of a branch's wording, so a reworded child voids the review. A proposal is not part of the definition yet."""
    node = claims[cid]
    kids = [claims.get(k, {}) for k in node["children"]]
    text = [node.get("claim")] + [kid.get("claim") for kid in kids if kid.get("status") != "proposed"]
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


def validate_diagram(diagram, where):
    """Problems in one diagram. An element with 'claims' is lit: the page colors it by their grades."""
    if not isinstance(diagram, dict) or not diagram.get("nodes"):
        return [f"{where}: needs a diagram with nodes"]
    problems = []
    nodes, edges = diagram["nodes"], diagram.get("edges", [])
    ids = [n.get("id") for n in nodes]
    if len(set(ids)) != len(ids):
        problems.append(f"{where}: duplicate node ids")
    if len(nodes) > MAX_NODES:
        problems.append(f"{where}: {len(nodes)} nodes; keep a diagram to {MAX_NODES} or fewer")
    cells = {}
    for n in nodes:
        problems += [f"{where}: node needs '{key}'" for key in ("id", "label", "col", "row") if key not in n]
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
    for e in edges:
        problems += [f"{where}: edge {end} unknown node {e.get(end)}" for end in ("from", "to") if e.get(end) not in ids]
        if e.get("status", "same") not in EDGE_STATUS:
            problems.append(f"{where}: edge {e.get('from')}→{e.get('to')} status must be one of {sorted(EDGE_STATUS)}")
    if not any((el.get("status", "same") != "same" or el.get("claims")) and not el.get("dim") for el in nodes + edges):
        problems.append(f"{where}: nothing in the diagram is lit; bind an element to claims or give it a status other than 'same'")
    for lane in diagram.get("lanes", []):
        if "label" not in lane or len(lane.get("cols", [])) != 2:
            problems.append(f"{where}: lane needs 'label' and 'cols': [first, last]")
    for region in diagram.get("regions", []):
        if "label" not in region or "cols" not in region or "rows" not in region:
            problems.append(f"{where}: region needs 'label', 'cols', and 'rows'")
    return problems


def elements(item):
    diagram = item.get("diagram") or {}
    return diagram.get("nodes", []) + diagram.get("edges", [])


def bindings(tree):
    """Every claim a map or decision names, as written."""
    for item in tree.get("maps", []) + tree.get("decisions", []):
        yield from item.get("claims", [])
        for el in elements(item):
            yield from el.get("claims", [])


def locate(p, name):
    """A bound name is an id in this tree, or file.json#id for a node in another."""
    file, sep, cid = name.rpartition("#")
    return ((p.parent / file).resolve() if sep else p, cid)


def validate(tree, where):
    claims = tree.get("claims")
    if not isinstance(claims, dict) or tree.get("root") not in claims:
        return [f"{where}: needs 'claims' and a 'root' that names one of them"]
    problems = []
    for cid, node in claims.items():
        at = f"{where}#{cid}"
        if not node.get("claim"):
            problems.append(f"{at}: missing 'claim'")
        if node.get("status", "shipped") not in STATUSES:
            problems.append(f"{at}: status '{node['status']}' is not one of {list(STATUSES)}")
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
                problems.append(f"{at}: proven needs enforcedBy test, lint, type, or probe, not '{by}'")
            probe = node.get("probe")
            runs = isinstance(probe, dict) and isinstance(probe.get("run"), str) and probe["run"].strip()
            if (by == "probe" or probe is not None) and not runs:
                problems.append(f"{at}: enforcedBy probe needs 'probe' with 'run', a command that exits 0 when the claim holds")
            if grade == "proven" and by != "probe" and not evidence:
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

    for kind in ("map", "decision"):
        for i, item in enumerate(tree.get(kind + "s", []), 1):
            at = f"{where} {kind} {i}"
            if not item.get("title"):
                problems.append(f"{at}: missing 'title'")
            if kind == "map":
                problems += validate_diagram(item.get("diagram"), at)
                continue
            if "map" not in item:
                problems += validate_diagram(item.get("diagram"), at)
            elif item["map"] not in [m.get("title") for m in tree.get("maps", [])]:
                problems.append(f"{at}: 'map' must be the title of one of this tree's maps")
            if not item.get("claims"):
                problems.append(f"{at}: needs 'claims', the nodes it is about")
            options = item.get("options", [])
            if len(options) < 2 or not all(o.get("label") for o in options):
                problems.append(f"{at}: needs at least 2 options, each with a 'label', recommended first")
            if not all(pt.get("label") and pt.get("text") for pt in item.get("points", [])):
                problems.append(f"{at}: each point needs 'label' and 'text'")
    return problems


def ref_target(p, ref, trees):
    """The (file, id) a ref points at, or None when it does not resolve."""
    file, _, cid = ref.partition("#")
    ref_path = (p.parent / file).resolve()
    tree = trees.get(ref_path)
    cid = cid or (tree or {}).get("root")
    return (ref_path, cid) if tree and cid in tree["claims"] else None


def status_of(p, cid, trees):
    """A node's own status. A ref that sets none takes its target's."""
    node = trees[p]["claims"][cid]
    target = ref_target(p, node["ref"], trees) if "ref" in node and "status" not in node else None
    return status_of(*target, trees) if target else node.get("status", "shipped")


def check(path, counted=("shipped",), failed=()):
    """Grade the tree at path and every tree it refs. Returns (problems, grades, trees).

    A branch counts only the children whose status is in 'counted'. A leaf in 'failed' (its probe did not
    pass in this run) grades as a gap.
    """
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
            # Grade every child so each has a grade to show, then count the ones we claim.
            kids = [(k, grade(p, k, inner)) for k in node["children"] if k in tree_at(p)["claims"]]
            kids = [g for k, g in kids if status_of(p, k, trees) in counted]
            g = weakest(*kids) if kids else "open"
            if review_state(tree_at(p)["claims"], cid) != "reviewed":
                g = weakest(g, "asserted")
        elif pending(node) or key in failed:
            g = "gap"
        else:
            g = node["grade"] if node.get("grade") in LEAF_GRADES else "open"
        grades[key] = g
        return g

    path = path.resolve()
    tree = tree_at(path)
    if tree is not None:
        grade(path, tree["root"], frozenset())
        for name in dict.fromkeys(bindings(tree)):
            p, cid = locate(path, name)
            target = tree_at(p) if p.exists() else None
            if target is None or cid not in target["claims"]:
                problems.append(f"{path.name}: a map or decision names '{name}', which does not exist")
            else:
                grade(p, cid, frozenset())
    return problems, grades, trees


def qualifiers(p, cid, grades, trees, counted, failed):
    """(kind, text) pairs under a node: 'except' for what we claim and cannot prove, else the status of a child we do not count."""
    claims = trees[p]["claims"]
    node = claims[cid]
    if "children" not in node:
        if grades[(p, cid)] == "proven":
            return []
        why = f"live from {node['liveFrom']}" if pending(node) else "probe failed" if (p, cid) in failed else grades[(p, cid)]
        return [("except", f"{node['claim']} ({why})")]
    state = review_state(claims, cid)
    out = [] if state == "reviewed" else [("except", f"{node['claim']} (definition {state})")]
    for k in node["children"]:
        status = status_of(p, k, trees)
        if status in counted:
            out += qualifiers(p, k, grades, trees, counted, failed)
        elif status != "proposed":  # nobody agreed to a proposal, so it does not qualify the claim
            out.append((status, claims[k]["claim"]))
    return out


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def repo_root(p):
    """The checkout a tree file is in, or its folder when it is in none."""
    top = git(p.parent, "rev-parse", "--show-toplevel")
    return pathlib.Path(top.stdout.strip()) if top.returncode == 0 else p.parent


def run_probes(trees):
    """Run every probe from its tree's checkout. Returns ({leaf: why it failed}, [gap leaves whose probe now passes])."""
    failed, fixed = {}, []
    for p, tree in trees.items():
        for cid, node in (tree or {}).get("claims", {}).items():
            probe = node.get("probe")
            if not probe:
                continue
            try:
                timeout = probe.get("timeout", PROBE_TIMEOUT)
                code = subprocess.run(probe["run"], shell=True, cwd=repo_root(p), capture_output=True, timeout=timeout).returncode
                why = f"exit {code}"
            except subprocess.TimeoutExpired:
                code, why = 1, "timed out"
            if node.get("grade") == "gap":
                fixed += [f"{p.name}#{cid}"] if code == 0 else []
            elif code:
                failed[(p, cid)] = why
    return failed, fixed


def stale(path, trees, rev, checkouts):
    """Nodes whose pinned evidence or source files differ at rev. Returns (lines, whether any are stale)."""
    repos = {}
    for checkout in checkouts or [repo_root(path)]:
        url = git(checkout, "remote", "get-url", "origin").stdout.strip().removesuffix(".git")
        if url:
            repos["/".join(url.replace(":", "/").split("/")[-2:]).lower()] = checkout
    changed, fresh, unknown, untracked = [], 0, set(), []
    for p, tree in trees.items():
        for cid, node in (tree or {}).get("claims", {}).items():
            name = cid if p == path else f"{p.name}#{cid}"
            links = [l for field in ("evidence", "source") for l in node.get(field, []) if "repo" in l]
            if not links:
                if node.get("grade") in LEAF_GRADES - {"gap"} and "probe" not in node:
                    untracked.append(name)
                continue
            hits = []
            for link in links:
                checkout = repos.get(link["repo"].lower())
                if checkout is None:
                    unknown.add(link["repo"])
                    continue
                # ponytail: any change to the file counts, which over-reports on busy files. Compare the pinned line's hunk if that gets noisy.
                code = git(checkout, "diff", "--quiet", link["sha"], rev, "--", link["path"]).returncode
                if code == 1:
                    hits.append(f"{link['path']} changed since {link['sha'][:7]}")
                elif code:
                    hits.append(f"{link['path']}: cannot compare {link['sha'][:7]} with {rev}")
            if hits:
                changed += [f"  {name}: {hit}" for hit in dict.fromkeys(hits)]
            elif not any(link["repo"] in unknown for link in links):
                fresh += 1
    lines = ["Stale, regrade and pin again:"] + changed if changed else []
    if unknown:
        lines.append(f"Cannot check, no checkout (pass --repo): {', '.join(sorted(unknown))}")
    if untracked:
        lines.append(f"No evidence to track: {', '.join(untracked)}")
    lines.append(f"{fresh} unchanged at {rev}.")
    return lines, bool(changed)


def standing(path, trees, counted):
    """For each node under the root: None when it counts toward the root, else the status that keeps it out."""
    claims, out = trees[path]["claims"], {}

    def walk(cid, why):
        if cid in out:
            return
        out[cid] = why
        for k in claims[cid].get("children", []):
            status = status_of(path, k, trees)
            walk(k, why or (None if status in counted else status))

    walk(trees[path]["root"], None)
    return out


def diff(path, rev, counted):
    """Grade changes since the tree as committed at rev. Returns (lines, whether a claim that counts got worse)."""
    problems, grades, trees = check(path, counted)
    if problems:
        return problems, True
    root = repo_root(path)
    # Every tree this one refs, so the old copy can resolve the same refs.
    folder = pathlib.Path(os.path.commonpath([p.parent for p in trees])).relative_to(root)
    listed = git(root, "ls-tree", "-r", "--name-only", rev, "--", str(folder))
    if listed.returncode:
        return [f"cannot read {rev}: {listed.stderr.strip()}"], True
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d).resolve()
        for name in listed.stdout.splitlines():
            if name.endswith(".json"):
                (d / name).parent.mkdir(parents=True, exist_ok=True)
                (d / name).write_text(git(root, "show", f"{rev}:{name}").stdout)
        old_path = d / path.relative_to(root)
        if not old_path.exists():
            return [f"{path.name} is not in {rev}: every claim is new."], False
        old_problems, old_grades, old_trees = check(old_path, counted)
        if old_problems:
            return [f"{path.name} at {rev} does not pass the check, so there is nothing to compare."], False
        old, new = old_trees[old_path]["claims"], trees[path]["claims"]
        both = [cid for cid in new if cid in old]
        step = {cid: RANK.index(grades[(path, cid)]) - RANK.index(old_grades[(old_path, cid)]) for cid in both}
        statuses = {cid: (status_of(old_path, cid, old_trees), status_of(path, cid, trees)) for cid in both}
        removed = [f"{cid} (was {old_grades[(old_path, cid)]})" for cid in old if cid not in new]
        was = {cid: old_grades[(old_path, cid)] for cid in both}
    out = standing(path, trees, counted)

    def moved(sign):
        """The deepest nodes that moved: a branch is named only when no child of its explains the move."""
        hit = {cid for cid in both if step[cid] * sign > 0}
        return [cid for cid in both if cid in hit and not hit & set(new[cid].get("children", []))]

    lines = []
    for title, cids in (("Regressed", moved(-1)), ("Improved", moved(1))):
        if cids:
            lines.append(f"{title}:")
            lines += [f"  {cid}: {was[cid]} -> {grades[(path, cid)]}" + (f"  [{out[cid]}]" if out[cid] else "") for cid in cids]
    changed = [f"{cid} {a} -> {b}" for cid, (a, b) in statuses.items() if a != b]
    added = [cid for cid in new if cid not in old]
    lines += [f"{title}: {', '.join(items)}" for title, items in (("Status changed", changed), ("New", added), ("Removed", removed)) if items]
    return lines or [f"No grade changed since {rev}."], any(not out[cid] for cid in moved(-1))


def report(path, counted=("shipped",), probe=False):
    """Returns (problems, text, page, failed probes)."""
    path = path.resolve()
    problems, grades, trees = check(path, counted)
    failed, fixed = run_probes(trees) if probe and not problems else ({}, [])
    if failed:
        problems, grades, trees = check(path, counted, failed)
    if problems:
        return problems, None, None, failed
    tree = trees[path]
    claims = tree["claims"]

    def render(cid, depth):
        node = claims[cid]
        ref = f"  -> {node['ref']}" if "ref" in node else ""
        status = status_of(path, cid, trees)
        tag = f"  [{status}]" if status != "shipped" else ""
        line = f"{'  ' * depth}{grades[(path, cid)]:<9} {cid}: {node['claim']}{ref}{tag}"
        return [line] + [l for k in node.get("children", []) for l in render(k, depth + 1)]

    # Leaves that count toward the root, and how many sit under a child that does not count.
    out = {cid: why for cid, why in standing(path, trees, counted).items() if "children" not in claims[cid]}
    live = [cid for cid, why in out.items() if not why]
    skipped = collections.Counter(why for why in out.values() if why)
    root = claims[tree["root"]]["claim"]
    qs = list(dict.fromkeys(qualifiers(path, tree["root"], grades, trees, counted, failed)))
    excepts = [text for kind, text in qs if kind == "except"]
    statement = f"{root}, except: {'; '.join(excepts)}." if excepts else f"{root}."
    for status in STATUSES:
        texts = [text for kind, text in qs if kind == status]
        if texts:
            statement += f" {status.title()}: {'; '.join(texts)}."
    tally = collections.Counter(grades[(path, cid)] for cid in live)
    counts = ", ".join(f"{tally[g]} {g}" for g in reversed(RANK) if tally[g])
    lines = [f"Grades: {counts}"]
    if skipped:
        lines.append("Not counted: " + ", ".join(f"{skipped[s]} {s}" for s in STATUSES if skipped[s]))
    if status_of(path, tree["root"], trees) != "shipped":
        lines.append(f"Status: {status_of(path, tree['root'], trees)}")
    lines += [f"Probe failed ({why}): {p.name}#{cid}: {trees[p]['claims'][cid]['probe']['run']}" for (p, cid), why in failed.items()]
    if fixed:
        lines.append(f"Probe passes on a gap, grade it again: {', '.join(fixed)}")
    maps, decisions = tree.get("maps", []), tree.get("decisions", [])
    if maps:
        drawn = set()

        def cover(cid):
            drawn.add(cid)
            for k in claims[cid].get("children", []):
                cover(k)

        for name in (n for m in maps for el in elements(m) for n in el.get("claims", [])):
            p, cid = locate(path, name)
            if p == path:
                cover(cid)
        leaves = [cid for cid, node in claims.items() if "children" not in node]
        missing = [cid for cid in leaves if cid not in drawn]
        lines.append(f"Maps draw {len(leaves) - len(missing)} of {len(leaves)} leaves." + (f" Not drawn: {', '.join(missing)}" if missing else ""))
    if decisions:
        lines.append(f"Open decisions: {len(decisions)}")
    # A decision may show one of the maps instead of carrying its own diagram.
    by_title = {m["title"]: {"diagram": m["diagram"]} for m in maps}
    page = {
        "title": f"{path.stem.replace('-', ' ').title()} Claims",
        "root": root,
        "statement": statement,
        "tally": {g: tally[g] for g in reversed(RANK) if tally[g]},
        "decisions": [bound({**d, **by_title.get(d.get("map"), {}), "title": d["title"]}, path, grades, trees) for d in decisions],
        "maps": [bound(m, path, grades, trees) for m in maps],
        "tree": nested(path, tree["root"], grades, trees),
    }
    return [], "\n".join(render(tree["root"], 0) + [""] + lines + ["", statement]), page, failed


def bound(item, path, grades, trees):
    """A map or decision with each named claim filled in, and each drawn element graded by its weakest claim."""

    def cards(names):
        out = []
        for key in (locate(path, n) for n in names):
            node = trees[key[0]]["claims"][key[1]]
            card = {
                "id": key[1],
                "claim": node["claim"],
                "grade": grades[key],
                "note": node.get("note"),
                "source": [github(link) for link in node.get("source", [])],
                "evidence": [github(link) for link in node.get("evidence", [])],
            }
            out.append({k: v for k, v in card.items() if v not in (None, [])})
        return out

    item = copy.deepcopy(item)
    if "claims" in item:
        item["claims"] = cards(item["claims"])
    for el in elements(item):
        if el.get("claims"):
            el["claims"] = cards(el["claims"])
            el["grade"] = weakest(*[c["grade"] for c in el["claims"]])
    return item


def nested(p, cid, grades, trees):
    """The node and everything below it, refs inlined, in the shape page.html outlines."""
    node = trees[p]["claims"][cid]
    status = status_of(p, cid, trees)
    if "ref" in node:
        return {**nested(*ref_target(p, node["ref"], trees), grades, trees), "ref": node["ref"], "status": status}
    grade = grades[(p, cid)]
    out = {
        "id": cid,
        "name": node["claim"],
        "grade": grade,
        "status": status,
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
    template = (HERE / "page.html").read_text()
    # </script> inside a JSON string would end the script block early.
    data = json.dumps(page, ensure_ascii=False).replace("</", "<\\/")
    parts = {"TITLE": page["title"], "CSS": (HERE / "flow.css").read_text(), "JS": (HERE / "flow.js").read_text(), "DATA": data}
    for key, value in parts.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def self_test():
    good = {
        "root": "a",
        "claims": {
            "a": {"claim": "A", "basis": "x", "children": ["b", "c", "d", "f", "g", "h"], "reviewed": {"by": "t", "date": "d"}},
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
            "f": {"claim": "F", "status": "planned"},
            "g": {"claim": "G", "status": "proposed"},
            "h": {"claim": "H", "status": "cut", "grade": "gap", "note": "n"},
        },
    }
    good["claims"]["a"]["reviewed"]["digest"] = digest(good["claims"], "a")
    box = {"label": "N", "col": 0, "row": 0}
    good["maps"] = [{
        "title": "M",
        "diagram": {
            "nodes": [{**box, "id": "n", "claims": ["b", "e"]}, {**box, "id": "o", "col": 1, "claims": ["other.json#y"]}],
            "edges": [{"from": "n", "to": "o"}],
        },
    }]
    good["decisions"] = [{
        "title": "D",
        "claims": ["e"],
        "options": [{"label": "x"}, {"label": "y"}],
        "diagram": {"nodes": [{**box, "id": "n", "status": "gap"}]},
    }, {"title": "D2", "claims": ["a"], "options": [{"label": "x"}, {"label": "y"}], "map": "M"}]
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
            "a": {"claim": "A", "status": "maybe", "children": ["a", "z"], "reviewed": {"by": "t", "date": "d"}},
            "b": {"claim": "B", "grade": "proven", "enforcedBy": "agent", "liveFrom": "soon", "source": [{"repo": "r"}]},
            "c": {"claim": "C", "grade": "proven", "enforcedBy": "probe"},
        },
        "maps": [{"diagram": {"nodes": [{"id": "n", "label": "N", "col": 0, "row": 0, "claims": ["nope"]}], "edges": [{"from": "n", "to": "q"}]}}],
        "decisions": [{"title": "D", "diagram": {"nodes": [{"id": "n", "label": "N", "col": 0, "row": 0}]}}, {"title": "E", "map": "nope"}],
    }
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        for name, data in (("good.json", good), ("other.json", other), ("bad.json", bad)):
            (d / name).write_text(json.dumps(data))
        problems, grades, _ = check(d / "good.json")
        assert not problems, problems
        g = {cid: grades[(d.resolve() / "good.json", cid)] for cid in good["claims"]}
        assert digest(good["claims"], "a") == digest({**good["claims"], "g": {"claim": "G reworded", "status": "proposed"}}, "a")
        want = {"a": "asserted", "b": "proven", "c": "asserted", "d": "proven", "e": "partial", "f": "open", "g": "open", "h": "gap"}
        assert g == want, g
        _, out, page, _ = report(d / "good.json")
        assert out.endswith("A, except: C (definition not reviewed); E (partial). Planned: F. Cut: H."), out
        assert "Grades: 2 proven, 1 partial\nNot counted: 1 planned, 1 proposed, 1 cut" in out, out
        assert "Maps draw 2 of 6 leaves. Not drawn: d, f, g, h" in out and "Open decisions: 2" in out, out
        assert page["tree"]["children"][3]["status"] == "planned", page["tree"]
        _, out, _, _ = report(d / "good.json", ("shipped", "planned"))
        assert out.endswith("A, except: C (definition not reviewed); E (partial); F (open). Cut: H."), out
        drawn = page["maps"][0]["diagram"]["nodes"]
        assert [n["grade"] for n in drawn] == ["partial", "proven"], drawn
        assert page["decisions"][0]["claims"][0]["grade"] == "partial"
        assert page["decisions"][1]["diagram"]["nodes"][1]["grade"] == "proven", page["decisions"][1]
        ref = page["tree"]["children"][2]
        assert (ref["id"], ref["ref"], ref["collapsed"]) == ("y", "other.json#y", True), ref
        assert '"grade": "partial"' in build_html(page)
        assert '"url": "https://example.com/pricing"' in build_html(page)

        good["claims"]["b"].update(claim="B reworded", liveFrom="2999-01-01")
        good["claims"]["e"]["liveFrom"] = "2000-01-01"
        (d / "good.json").write_text(json.dumps(good))
        _, out, _, _ = report(d / "good.json")
        assert out.endswith(
            "A, except: A (definition changed since review); B reworded (live from 2999-01-01); "
            "C (definition not reviewed); E (partial). Planned: F. Cut: H."
        ), out
        problems, _, _ = check(d / "bad.json")
        expected_problems = (
            "needs 'basis'", "'digest'", "'liveFrom'", "'z' does not exist", "nothing reaches", "not 'agent'", "evidence link",
            "source link", "cycle", "status 'maybe'", "needs 'probe' with 'run'", "map 1: missing 'title'", "edge to unknown node q", "'nope', which does not exist",
            "nothing in the diagram is lit", "decision 1: needs 'claims'", "at least 2 options", "decision 2: 'map' must be",
        )
        for expected in expected_problems:
            assert any(expected in p for p in problems), (expected, problems)

        probed = {
            "root": "a",
            "claims": {
                "a": {"claim": "A", "basis": "x", "children": ["b", "c", "e"]},
                "b": {"claim": "B", "grade": "proven", "enforcedBy": "probe", "probe": {"run": "exit 0"}},
                "c": {"claim": "C", "grade": "proven", "enforcedBy": "probe", "probe": {"run": "exit 3"}},
                "e": {"claim": "E", "grade": "gap", "note": "n", "probe": {"run": "exit 0"}},
            },
        }
        (d / "probed.json").write_text(json.dumps(probed))
        _, out, _, failed = report(d / "probed.json")
        assert not failed and "proven    c: C" in out, out
        _, out, _, failed = report(d / "probed.json", probe=True)
        assert list(failed.values()) == ["exit 3"] and "gap       c: C" in out and "C (probe failed)" in out, out
        assert "Probe failed (exit 3): probed.json#c: exit 3" in out and "grade it again: probed.json#e" in out, out

        if shutil.which("git"):
            repo = d / "repo"
            repo.mkdir()
            commit = ("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qam", "c")
            git(repo, "init", "-q")
            git(repo, "remote", "add", "origin", "git@example.com:Acme/App.git")
            for name in ("kept.txt", "edited.txt"):
                (repo / name).write_text("one\n")
            git(repo, "add", ".")
            git(repo, *commit)
            sha = git(repo, "rev-parse", "HEAD").stdout.strip()
            (repo / "edited.txt").write_text("two\n")
            git(repo, *commit)
            link = {"repo": "acme/app", "sha": sha, "line": 1}
            pinned = {
                "root": "a",
                "claims": {
                    "a": {"claim": "A", "basis": "x", "children": ["b", "c", "e", "f"]},
                    "b": {"claim": "B", "grade": "proven", "enforcedBy": "test", "evidence": [{**link, "path": "kept.txt"}]},
                    "c": {"claim": "C", "grade": "proven", "enforcedBy": "test", "evidence": [{**link, "path": "edited.txt"}]},
                    "e": {"claim": "E", "grade": "asserted", "enforcedBy": "agent"},
                    "f": {"claim": "F", "grade": "proven", "enforcedBy": "test", "evidence": [{**link, "repo": "acme/other", "path": "x"}]},
                },
            }
            (repo / "pinned.json").write_text(json.dumps(pinned))
            _, _, trees = check((repo / "pinned.json").resolve())
            lines, any_stale = stale((repo / "pinned.json").resolve(), trees, "HEAD", [])
            want = [
                "Stale, regrade and pin again:", f"  c: edited.txt changed since {sha[:7]}",
                "Cannot check, no checkout (pass --repo): acme/other", "No evidence to track: e", "1 unchanged at HEAD.",
            ]
            assert any_stale and lines == want, lines
            git(repo, "add", ".")
            git(repo, *commit)
            claims = pinned["claims"]
            claims["a"]["children"] = ["b", "c", "e", "g"]
            claims["c"] = {"claim": "C", "grade": "gap", "note": "n"}
            claims["e"] = {"claim": "E", "grade": "partial", "enforcedBy": "agent", "note": "n"}
            claims["g"] = {"claim": "G", "status": "proposed"}
            del claims["f"]
            same = diff((repo / "pinned.json").resolve(), "HEAD", ("shipped",))
            assert same == (["No grade changed since HEAD."], False), same
            (repo / "pinned.json").write_text(json.dumps(pinned))
            lines, worse = diff((repo / "pinned.json").resolve(), "HEAD", ("shipped",))
            want_diff = ["Regressed:", "  c: proven -> gap", "Improved:", "  e: asserted -> partial", "New: g", "Removed: f (was proven)"]
            assert worse and lines == want_diff, lines
            claims["c"]["status"] = "planned"
            (repo / "pinned.json").write_text(json.dumps(pinned))
            lines, worse = diff((repo / "pinned.json").resolve(), "HEAD", ("shipped",))
            assert not worse and lines[:2] == ["Regressed:", "  c: proven -> gap  [planned]"], lines
            assert "Status changed: c shipped -> planned" in lines, lines
            assert stale((repo / "pinned.json").resolve(), trees, sha, [repo]) == (want[2:4] + [f"2 unchanged at {sha}."], False)
    print("self-test passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tree", nargs="?", type=pathlib.Path)
    parser.add_argument("--html", type=pathlib.Path, help="also write an interactive tree page here")
    parser.add_argument("--digest", metavar="NODE", help="print the digest to store in NODE's 'reviewed'")
    parser.add_argument("--include", action="append", default=[], choices=STATUSES[1:], help="also count claims with this status, as if they had shipped")
    parser.add_argument("--probe", action="store_true", help="run every probe; a leaf whose probe fails grades as a gap")
    parser.add_argument("--stale", nargs="?", const="HEAD", metavar="REV", help="name the nodes whose evidence files changed between their pinned commit and REV (default HEAD)")
    parser.add_argument("--diff", metavar="REV", help="name the claims whose grade changed since the tree committed at REV; exit 1 when one that counts got worse")
    parser.add_argument("--repo", action="append", default=[], type=pathlib.Path, help="a checkout to look evidence up in for --stale (default: the one the tree is in)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.tree:
        parser.error("give a tree file or --self-test")
    if args.digest:
        return print(digest(json.loads(args.tree.read_text())["claims"], args.digest))
    if args.stale:
        problems, _, trees = check(args.tree.resolve())
        lines, any_stale = stale(args.tree.resolve(), trees, args.stale, args.repo)
        print("\n".join(problems + lines))
        sys.exit(1 if problems or any_stale else 0)
    if args.diff:
        lines, worse = diff(args.tree.resolve(), args.diff, ("shipped", *args.include))
        print("\n".join(lines))
        sys.exit(1 if worse else 0)
    problems, out, page, failed = report(args.tree, ("shipped", *args.include), args.probe)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        sys.exit(1)
    print(out)
    if args.html:
        args.html.write_text(build_html(page))
        print(f"\nWrote {args.html}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
