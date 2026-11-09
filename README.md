# Claims

Agent skills for Claude Code that treat what a product promises as a set of claims, and check each claim against the code and its tests.

| Skill | What it does |
|---|---|
| `claim` | Break a claim into a reviewed tree of sub-claims, grade each leaf against the code, report the gaps |
| `audit-claims` | Collect what the website, docs, and app tell users into claim trees, grade them, rank what is false or mislabeled |
| `plan-claims` | Turn a feature request into a launch claim, a reviewed claim tree, and a plan with one task per gap |
| `investigate-claims` | Map a competitor's claims against their code, then grade the same claims against yours |
| `claim-deck` | Build a one-slide-per-claim review page for a pull request, with evidence grades and diagrams |

Every leaf gets one grade: `proven` (a test, lint, or type rule enforces it), `partial`, `asserted` (only a comment or a one-off check says so), or `gap`. A branch takes its weakest child's grade, and stays capped at `asserted` until a person agrees its children cover it. `claim/schema.md` has the format.

## Install

```bash
git clone https://github.com/0xSplits/claims ~/claims
mkdir -p ~/.claude/skills && for s in ~/claims/*/; do ln -s "${s%/}" ~/.claude/skills/; done
```

The scripts need only Python 3. Check one with `python3 ~/claims/claim/check.py --self-test`.
