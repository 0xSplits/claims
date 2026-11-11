# Claims

Agent skills for Claude Code that treat what a product promises as a set of claims, and check each claim against the code and its tests.

| Skill | What it does |
|---|---|
| `claim` | Break a claim into a reviewed tree of sub-claims, grade each leaf against the code, draw it as a page |
| `audit-claims` | Collect what the website, docs, and app tell users into claim trees, grade them, rank what is false or mislabeled |
| `plan-claims` | Turn a feature request into a launch claim, a reviewed claim tree, and a plan with one task per gap |
| `investigate-claims` | Map a competitor's claims against their code, then grade the same claims against yours |
| `claim-deck` | Build a one-slide-per-claim review page for a pull request, with evidence grades and diagrams |

Every leaf gets one grade: `proven` (a test, lint rule, type rule, or probe of the running system enforces it), `partial`, `asserted` (only a comment or a one-off check says so), or `gap`. A branch takes its weakest child's grade, and stays capped at `asserted` until a person agrees its children cover it. `claim/schema.md` has the format.

A tree can hold more than what is true today. Each claim has a status: `shipped`, `planned`, `proposed` (an idea), or `cut`. Only shipped claims count toward the grade, so a gap in one is a bug, and plans and ideas sit in the same tree without turning it red. `check.py --stale` names the claims whose evidence changed since they were graded, `check.py --probe` re-runs the probes, and `check.py --diff <rev>` fails when a shipped claim grades worse than it did at that commit, so an agent or a CI job can keep a tree current without grading all of it again.

Every skill ends in a page you scroll one slide at a time. Each open decision is a slide with a diagram of what it is about and the options, recommended first. Each map draws the claims as one picture, colored by grade. `claim/diagram.md` has the diagram grammar.

## Install

In Claude Code:

```
/plugin install claims --marketplace 0xSplits/claims
```

On Claude Code older than 2.1.275, add the marketplace first:

```
/plugin marketplace add 0xSplits/claims
/plugin install claims@splits
```

The skills then run as `/claims:claim`, `/claims:audit-claims`, and so on. Get updates with `/plugin marketplace update splits`.

For other agents, such as Cursor or Codex: `npx skills add 0xSplits/claims`.

The scripts need only Python 3. Check one with `python3 skills/claim/check.py --self-test`.
