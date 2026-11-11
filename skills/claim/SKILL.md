---
name: claim
description: Break a product or engineering claim ("we have a best-in-class accounting suite") into a tree of sub-claims, check each leaf against the code and tests, and report the claim qualified by every gap. Use when asked what it would take to make a claim true, whether a claim holds, or to expand or re-check a claim tree.
argument-hint: <claim sentence, or tree file / node id to expand>
---

# Claim

A claim is true when its definition is reviewed and every part of that definition is proven. This skill builds that definition one level at a time and grades what the code can back today. Read `schema.md` for the file format and grades, and `diagram.md` for the diagrams, before writing anything.

Trees live in `docs/claims/` of the repo you keep them in, one file per root claim, named for it (`accounting-suite.json`). Edit only tree files: do not change code, commit, or post anywhere.

## The page is where the person decides

A tree is read as its page, not as text in the reply. `check.py <tree>.json --html <tree>.html` builds it: a cover, one slide per open decision, one slide per map, then every claim.

- Every question you put to the person is a decision in the tree file, with a diagram of what it is about. Do not ask them to read a list in the reply.
- Publish the page as a private artifact when you can (Claude Code: the Artifact tool), and publish the same file again after each change so the link stays the same. Otherwise hand over the file. Do not commit the page.
- When you ask, give the link and each open decision's title and options in one line, so the person can answer in the chat after looking at the picture.
- When they answer, record the answer in the tree and delete the decision.

## 1. Find the node to expand

- Run `check.py` on every file in `docs/claims/` and read the results.
- Run `check.py <tree>.json --stale` on each as well. Grade again every leaf it names, by step 3, and pin its links to the commit you read, before you expand anything.
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
- A child we do not make yet carries a `status`: `planned` when the person has committed to it, `proposed` when it is only an idea. Write an idea the person raises in passing as a `proposed` open node under the branch it belongs to. It needs no review until someone commits to it.

Put the basis in one or two sentences on the node. Then ask the person whether the children cover the claim, as a decision:

- `band` is `Definition`, `title` is "Do these parts cover '<claim>'?", and `claims` is the branch.
- `points` are the claim and the basis. `options` are "They cover it" and "Revise".
- The diagram draws the branch with every child bound to its step: a lifecycle when the children are states and actions, a fan-out otherwise. A step with no child is how a missing child shows. When the tree's map already is that picture, set `map` to its title instead.

Revise until they say yes, then delete the decision and set `reviewed` with their name, today's date, and the digest from `check.py <tree>.json --digest <id>`. After that, the wording is fixed: changing the branch's claim or a child's voids the review, and `check.py` shows the branch as changed since review until the person agrees again. When no person is present, write no decision and leave `reviewed` out: the branch then caps at `asserted`, which is the honest grade for a definition nobody agreed to.

Expand one level per run.

## 3. Grade the leaves

For each new child that one behavior or one rule can settle, find the evidence. Leave a child that needs its own definition as an open node for a later run, including one that turns out to hold for some of its parts and not others.

- Search the code and its tests. Pin each `evidence` link to the commit you read (`git rev-parse HEAD` in that repo).
- `proven` only when you read the assertion or the rule and can link its line. A test that runs the path without asserting the claim is `partial`. So is a guarantee that holds only through a tested function the claim's own code calls.
- A comment, doc, or one-off agent check with nothing that re-runs it is `asserted`.
- When the code deliberately does something other than the claim says, grade it `gap` and put what does hold in the note. Do not reword a child to fit the code: propose the new wording to the person and stamp the review again if they agree.
- When only the running system can settle the claim (a deployed service, live data, another system), write a `probe`: a read-only command that exits 0 when the claim holds. Run it once yourself, then grade the leaf with `enforcedBy: probe`.
- When the behavior is in the code but takes effect on a known date (a plan enforcement date, a launch), grade what the code will do and set `liveFrom` to that date.

## 4. Draw the map

Keep one map in the tree that draws every leaf, and bind each new child into it. Draw it from what the claim means, as the states a user or a record moves through, not from how the code is laid out. Colors come from the grades, so the map needs no edit when a leaf is graded again.

When the tree has more leaves than 12 nodes can hold, bind a whole branch to the step it is about: the step then shows the branch's grade and lists its leaves. Add a second map for a branch only when its own steps matter to a decision.

## 5. Check

```bash
python3 <this skill's directory>/check.py <tree>.json
```

Add `--probe` when the tree has probes. After grading leaves again, run `check.py <tree>.json --diff <the default branch>` and name every regressed claim in the report. Fix every problem rather than loosening the data. The script refuses a `proven` leaf without mechanical evidence, a branch with more than 7 children, a dangling child or ref, a cycle, a node nothing reaches, a review without a digest, a map or decision that names a claim that does not exist, and a diagram with nothing lit. It also names the leaves no map draws.

## 6. Report

Build and publish the page. In the reply give the link, the grade tally, any open decision, and the next node to expand. The qualified statement is on the page's cover: repeat it in the reply, exactly as `check.py` prints it, only when it has three qualifiers or fewer. Name any `asserted` leaf with a real failure mode. For a pull request, where each claim needs its own code path drawn, point at the `claim-deck` skill.
