---
name: claim
description: Break a product or engineering claim ("we have a best-in-class accounting suite") into a tree of sub-claims, check each leaf against the code and tests, and report the claim qualified by every gap. Use when asked what it would take to make a claim true, whether a claim holds, or to expand or re-check a claim tree.
argument-hint: <claim sentence, or tree file / node id to expand>
---

# Claim

A claim is true when its definition is reviewed and every part of that definition is proven. This skill builds that definition one level at a time and grades what the code can back today. Read `schema.md` for the file format and grades before writing anything.

Trees live in `docs/claims/` of the repo you keep them in, one file per root claim, named for it (`accounting-suite.json`). Edit only tree files: do not change code, commit, or post anywhere.

## 1. Find the node to expand

- Run `check.py` on every file in `docs/claims/` and read the results.
- If the claim is already a node in some tree, expand that node. If the argument names a tree or node, use that.
- Otherwise start a new file whose root is the claim, as an open node.
- In an existing tree with no node named, take the highest open node or unreviewed branch.

## 2. Decompose before reading code

Write 2 to 7 children for the node. Children come from what the claim means, not from what the code does: children taken from the code only describe what already exists and confirm themselves.

- For a comparative claim ("best-in-class"), the basis is what the alternatives offer. Name them.
- Otherwise the basis is the spec, the PRD, or the person's own words.
- Each child is one declarative sentence about one behavior on one surface (backend, web app, API, CLI). A sentence that joins behaviors, tiers, or surfaces is a branch: leave it open for the next level rather than grading it as one leaf.
- Together the children must make the parent true: if every child held, a skeptic would accept the parent.
- A child that some tree in `docs/claims/` already establishes becomes a `ref`, not a copy.

Put the basis in one or two sentences on the node. Then show the person the parent, the children, and the basis, and ask whether the children cover the claim. Revise until they say yes, then set `reviewed` with their name, today's date, and the digest from `check.py <tree>.json --digest <id>`. After that, the wording is fixed: changing the branch's claim or a child's voids the review, and `check.py` shows the branch as changed since review until the person agrees again. When no person is present, leave `reviewed` out: the branch then caps at `asserted`, which is the honest grade for a definition nobody agreed to.

Expand one level per run.

## 3. Grade the leaves

For each new child that one behavior or one rule can settle, find the evidence. Leave a child that needs its own definition as an open node for a later run, including one that turns out to hold for some of its parts and not others.

- Search the code and its tests. Pin each `evidence` link to the commit you read (`git rev-parse HEAD` in that repo).
- `proven` only when you read the assertion or the rule and can link its line. A test that runs the path without asserting the claim is `partial`. So is a guarantee that holds only through a tested function the claim's own code calls.
- A comment, doc, or one-off agent check with nothing that re-runs it is `asserted`.
- When the code deliberately does something other than the claim says, grade it `gap` and put what does hold in the note. Do not reword a child to fit the code: propose the new wording to the person and stamp the review again if they agree.
- When the behavior is in the code but takes effect on a known date (a plan enforcement date, a launch), grade what the code will do and set `liveFrom` to that date.

## 4. Check

```bash
python3 <this skill's directory>/check.py <tree>.json
```

Fix every problem rather than loosening the data. The script refuses a `proven` leaf without mechanical evidence, a branch with more than 7 children, a dangling child or ref, a cycle, a node nothing reaches, and a review without a digest.

## 5. Report

Give the qualified statement exactly as `check.py` prints it, the grade tally, and the next node to expand. To show the tree, add `--html <tree>.html` to the check and publish that page as a private artifact when you can; do not commit it. Name any `asserted` leaf with a real failure mode. For a leaf a reviewer needs to see drawn, point at the `claim-deck` skill.
