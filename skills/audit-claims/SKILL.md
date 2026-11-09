---
name: audit-claims
description: Audit what a product tells users (website, docs, app labels and messages, CLI help, API docs) against what the code does. Collects every claim we make into claim trees, grades each against the code, and ranks the false, missing, mislabeled, and untested ones. Use when asked to audit claims, check whether the site or docs are true, find mislabeled UI, or validate a marketing claim such as "we have a world-class accounting service".
argument-hint: [claim sentence | product area | nothing for a full sweep]
---

# Audit claims

Every sentence we show users is a claim: a docs page, a pricing row, a button label, a toast. This skill collects those claims into the claim trees of the `claim` skill, grades them against the code, and reports where we say something the code does not back.

Read `../claim/SKILL.md` and `../claim/schema.md` first. Their tree format, grades, and review rules apply here unchanged. `check.py` below is `python3 ../claim/check.py`, relative to this skill's directory. Edit only tree files and the report: do not change copy or code, open tickets, or post anywhere.

## Modes

- **A claim** (`we have a world-class accounting service`): one tree with that claim as its root.
- **An area** (`accounting`, `the pricing page`): one tree for everything we say about that area.
- **Nothing**: a sweep. One tree per product area, taken from the top-level sections of the docs plus pricing and plans. Show the person the area list and ask which to run when there are more than 8.

## 1. Snapshot the repos

Grade against each repo's default branch, not the local checkout, which may be on a feature branch. For each repo that holds a surface in step 2:

```bash
git -C <repo> fetch -q origin
sha=$(git -C <repo> rev-parse origin/<default branch>)
git -C <repo> archive "$sha" | tar -x -C <scratch>/<repo>
```

Pin every `source` and `evidence` link to that `sha`.

## 2. Collect the claims

Read these places:

| Surface | Where claims live |
|---|---|
| Marketing site | pricing, product pages, feature cards, heroes |
| Docs | every page |
| App | headings, button and menu labels, tooltips, empty states, confirm dialogs, toasts, emails |
| CLI | command help text, and MCP tool descriptions when the CLI serves them |
| API | public API docs: route and schema field descriptions |

Find the repo and folder that hold each surface before you start, and list them in each tree's `basis`.

What counts:

- A statement of what the product does, guarantees, costs, or supports: fees, limits, chains, plans, security, custody, tax.
- A label for an action: a button says what it will do. "Export to Xero" claims that clicking it exports to Xero.
- A number or list that appears in more than one place. Record every place it appears.

Skip navigation, legal pages, and brand copy with nothing testable ("the future of onchain finance"), unless the mode names it. In claim mode, a comparative word like "world-class" is decomposed as `claim` does: from what the alternatives offer, named in `basis`.

Write each claim as one declarative sentence about one behavior on one surface, and attach a `source` link to every place we say it. When two places say different things (the docs say $5, the app says $1), keep both as separate leaves with their own sources. That is a finding in itself.

## 3. Build the trees

Files go in `docs/claims/audit/`, one per area or claim, plus an `index.json` whose root refs each tree, so the whole audit draws as one page.

- **Area tree:** root "Everything we tell users about <area> is true". The children group claims by feature, at most 7 per branch: nest a feature into sub-branches when it has more. The `basis` names the surfaces read.
- **Claim tree:** root is the claim. The children cover what the claim needs, from the basis, plus every promise our own surfaces make about it.
- Reuse a tree in `docs/claims/` through a `ref` when it already covers a feature.

Review: show the person each tree's claims as a list grouped by branch, with sources, and ask whether anything is missing or misread. On their yes, stamp `reviewed` with the digest, as `claim` describes. With no person present, leave trees unreviewed: they cap at `asserted`, which is honest for a harvest nobody checked.

## 4. Grade

Grade leaves by `claim` step 3, against the snapshots. Use one subagent per tree, and at most 8 at once. Brief each one with:

- the tree path and the snapshot paths and SHAs
- the instruction to read `../claim/SKILL.md` and `schema.md` first
- the instruction to edit only its own tree file

Check each subagent's tree yourself before you trust it. Then run `check.py` on every tree and on `index.json`.

## 5. Report

Rank findings worst first. In each band, give the claim, where we say it, what the code does, and the cheaper fix: change the copy, or change the code.

1. **False about money, custody, security, tax, or compliance.** A user could lose funds, file wrong, or trust a guarantee we don't keep.
2. **Advertised but missing.** The feature, export, chain, or integration does not exist.
3. **Mislabeled or contradictory.** A label does something other than it says, or two surfaces disagree.
4. **True but unbacked.** `asserted` or `partial` leaves with a real failure mode. Name the failure.

Publish the `index.json` tree page with `check.py index.json --html` as a private artifact, and put the ranked findings in the reply. Offer tickets in the team's tracker for bands 1 and 2. Create them only on the person's yes, and leave them unassigned.
