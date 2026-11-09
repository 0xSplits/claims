# Claim tree JSON

One file per root claim, in `docs/claims/`. `check.py` validates it, computes every node's grade, and prints the qualified root statement.

```json
{
  "root": "exports",
  "claims": {
    "exports": {
      "claim": "Teams can export all of their data",
      "basis": "The two products customers compare us with both export every table as CSV and on a schedule.",
      "children": ["csv", "scheduled", "large", "pricing"],
      "reviewed": { "by": "jane", "date": "2026-11-05", "digest": "9ac34e56b23e" }
    },
    "csv": {
      "claim": "Every table can be downloaded as CSV",
      "grade": "proven",
      "enforcedBy": "test",
      "evidence": [
        { "repo": "acme/app", "sha": "1a2b3c4", "path": "src/export/csv.test.ts", "line": 42, "label": "asserts a CSV per table" }
      ]
    },
    "scheduled": { "claim": "Exports can run on a schedule" },
    "large": {
      "claim": "Exports finish for tables of any size",
      "grade": "gap",
      "note": "Tables over 100,000 rows time out. No ticket."
    },
    "pricing": { "claim": "We have best-in-class pricing", "ref": "pricing.json" }
  }
}
```

## Nodes

Every node has `claim`: one declarative sentence. Any node may also have `source`: links, shaped like `evidence` links, to where we make the claim to users (a docs page, a button label, CLI help). A node is exactly one of:

| Kind | Fields | Meaning |
|---|---|---|
| branch | `children`, `basis`, `reviewed`? | Defined by 1 to 7 child ids. `basis` says where the decomposition came from. |
| leaf | `grade`, `enforcedBy`?, `evidence`?, `note`?, `liveFrom`? | Checked directly against code. |
| ref | `ref` | Established by another tree: `pricing.json`, or `plans.json#pricing` for a node inside one. Path is relative to this file. |
| open | none of the above | Not expanded or graded yet. |

`reviewed` is `{ "by", "date", "digest" }`, set only when a person (or a reviewer they named) agreed the children cover the claim. `digest` is what `check.py <tree>.json --digest <id>` prints at that moment. It fingerprints the branch's own claim and its children's, in order, so rewording any of them makes the branch read "definition changed since review" until someone agrees again.

## Leaf grades

- **proven**: a test asserts the claim, or a lint or type rule makes breaking it impossible. Needs `enforcedBy` of `test`, `lint`, or `type` and at least one `evidence` link.
- **partial**: holds for some cases. `note` names the rest.
- **asserted**: the code reads as correct, and a comment, doc, or one-off agent or human check says so. Nothing re-checks it on change.
- **gap**: does not hold. `note` names the ticket or says "No ticket."

`enforcedBy` is one of `test`, `lint`, `type`, `agent`, `review`, `comment`, and a `gap` leaves it out. Only the first three are mechanical, so only they can back `proven`.

`liveFrom` is a `YYYY-MM-DD` date for a leaf whose behavior is in the code but not in effect yet, such as a plan enforcement date. Before it the leaf counts as a gap, qualified "live from" that date. From it the leaf's own grade applies, with no edit.

`evidence` links are `{ repo, sha, path, line, label? }`, pinned to the commit that was read. A `source` link may instead be `{ url, label? }` for a web page outside any repo we snapshot, such as another company's docs.

## Rollup

Grades rank `proven` > `partial` > `asserted` > `open` > `gap`. A branch takes its weakest child's grade, capped at `asserted` until it is reviewed and its digest matches. A ref takes the grade of the node it points at.

The qualified statement is the root claim plus everything below it that is not proven: each non-proven leaf, open node, and ref, and each branch that is unreviewed or changed since review.
