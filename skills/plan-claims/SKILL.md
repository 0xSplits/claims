---
name: plan-claims
description: Turn a feature request, however vague, into an executable plan by working out the claim we want to make at launch. Breaks that claim into a reviewed claim tree, grades every leaf against today's code, settles open assumptions with the person, and turns each remaining gap into a task whose "done when" is the test that would prove it. Use when asked to plan a feature from claims, scope a vague request, or turn a claim tree into work.
argument-hint: <feature request, or a tree in docs/claims to continue planning>
---

# Plan claims

A feature is done when we can say what it does and prove it. This skill starts from that statement and works down to tasks. Proven leaves are work that already exists. Gaps are the plan.

Read `../claim/SKILL.md` and `../claim/schema.md` first. Their tree format, grades, and review rules apply here unchanged. `check.py` below is `python3 ../claim/check.py`, relative to this skill's directory. Write only the tree and the plan doc. Do not change code, and do not create tickets without the person's yes.

## 1. Write the launch claim

Restate the request as the one sentence we would put on the website or in the docs when it ships ("Workspaces can close an accounting period and lock it from edits"). Show it to the person and settle the wording before anything else. Every later step hangs off it.

The tree goes in `docs/claims/<feature>.json`. If the argument names an existing tree, continue from its open nodes.

## 2. Decompose to leaves

Break the claim down by `claim` step 2, with the same review gate and digest. Unlike `claim`, keep going in this session until every leaf is one behavior on one surface. Ask about one level at a time.

- The basis is the request, any spec or PRD it names, and the alternatives when the claim is comparative.
- Reuse what other trees establish through a `ref`.
- When the tree passes about 30 leaves, the feature is more than one plan. Suggest splitting the root and plan one part.

## 3. Grade against today's code

Grade every leaf by `claim` step 3, against a snapshot of each repo's default branch (`git archive origin/<branch>`). Pin links to that SHA.

- `proven`: already exists. The plan reuses it and does not touch it.
- `partial` or `asserted`: exists in part. The task finishes it or adds the missing test.
- `gap`: to build.

## 4. Settle assumptions

List every decision the request, spec, and code leave open: numbers and limits, who may do it, which plans and surfaces, what happens on failure, how it interacts with existing features. Ask the person at most 4 at a time, each with your recommended answer first. Each answer does one of three things:

- **Keep:** the leaf stays in scope. Put the decision in its `note`.
- **Cut:** the leaf stays as a `gap` whose note starts "Out of scope:" with the reason. It then shows in the qualified statement, which becomes the honest launch claim ("…, except: period reopening").
- **Reword:** change the claim, then stamp the parent's review again.

Repeat until no leaf rests on a guess.

## 5. Write the plan

Run `check.py` on the tree. Then write `docs/plans/<YYYY-MM-DD>-feat-<feature>-plan.md`, with front matter `title`, `type: feat`, `status: active`, `date`, and `tickets` (empty until tickets exist), and these sections:

1. **Launch claim:** the qualified statement once every task is done, which names only the cut leaves.
2. **Decisions:** each settled assumption in one line, with who decided it.
3. **Already true:** the proven leaves the work builds on, with evidence links.
4. **Tasks:** one per in-scope leaf that is not proven. Merge leaves that would change the same files into one task. Each task gives:
   - its leaf ids
   - what to build, in two or three sentences
   - "Done when": the test, lint, or type rule that would grade the leaf `proven`
   - what it depends on
5. **Order:** the tasks in dependency order. Mark the ones that can run in parallel.

Publish the tree page (`check.py <tree>.json --html`) as a private artifact. Report:

- the launch claim
- the counts of tasks, cut leaves, and leaves already proven
- the first task to start

## 6. Tickets (on the person's yes)

Create one ticket per task in the team's tracker, unassigned. Each ticket gets:

- the leaf ids and the tree path
- the "Done when" line
- a link to the plan doc

Write the ticket ids into the plan's `tickets` field. To track progress, grade the tree again with `claim` after merges: the plan is finished when every in-scope leaf is `proven`.
