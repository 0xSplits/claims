# Claim tree JSON

One file per root claim, in `docs/claims/`. `check.py` validates it, computes every node's grade, prints the qualified root statement, and with `--html` builds the page. `--stale`, `--probe`, and `--diff`, below, re-check a tree that is already graded.

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
    "scheduled": { "claim": "Exports can run on a schedule", "status": "planned" },
    "large": {
      "claim": "Exports finish for tables of any size",
      "grade": "gap",
      "note": "Tables over 100,000 rows time out. No ticket."
    },
    "pricing": { "claim": "We have best-in-class pricing", "ref": "pricing.json" }
  },
  "maps": [ { ...map } ],
  "decisions": [ { ...decision } ]
}
```

## Nodes

Every node has `claim`: one declarative sentence. Any node may also have `source`: links, shaped like `evidence` links, to where we make the claim to users (a docs page, a button label, CLI help), and `status`, described below. A node is exactly one of:

| Kind | Fields | Meaning |
|---|---|---|
| branch | `children`, `basis`, `reviewed`? | Defined by 1 to 7 child ids. `basis` says where the decomposition came from. |
| leaf | `grade`, `enforcedBy`?, `evidence`?, `probe`?, `note`?, `liveFrom`? | Checked directly against code, or against the running system by a probe. |
| ref | `ref` | Established by another tree: `pricing.json`, or `plans.json#pricing` for a node inside one. Path is relative to this file. |
| open | none of the above | Not expanded or graded yet. |

`reviewed` is `{ "by", "date", "digest" }`, set only when a person (or a reviewer they named) agreed the children cover the claim. `digest` is what `check.py <tree>.json --digest <id>` prints at that moment. It fingerprints the branch's own claim and its children's, in order, so rewording any of them makes the branch read "definition changed since review" until someone agrees again. A `proposed` child is left out of the fingerprint, so writing down an idea does not void the review. Giving it any other status does.

## Status

`status` says whether we make the claim. Any node may set it, and it covers everything under that node. A node without one is `shipped`.

| Status | Meaning | In the rollup |
|---|---|---|
| `shipped` | We make this claim today. | Counts. A `gap` here is a bug or a false claim. |
| `planned` | We have committed to making it. | Does not count. The statement lists it after "Planned:". |
| `proposed` | An idea nobody has agreed to yet. | Does not count, and the statement leaves it out. |
| `cut` | We decided not to make it. `note` says why. | Does not count. The statement lists it after "Cut:". |

- A node that is not `shipped` may be any kind. An idea is usually an open node, and a planned feature is usually a branch or a ref to its own tree.
- A ref that sets no status takes the status of the node it points at. A tree whose root is `planned` therefore stays planned in every tree that refs it.
- The root of the tree being checked is always graded, whatever its status, so `check.py` on a planned tree shows how far the plan has come.
- `check.py <tree>.json --include planned` counts planned claims as if they had shipped. The statement is then what we could say once the plans land. `--include` takes any status and can repeat.

## Leaf grades

- **proven**: a test asserts the claim, a lint or type rule makes breaking it impossible, or a probe checks it against the running system. Needs `enforcedBy` of `test`, `lint`, `type`, or `probe`, and at least one `evidence` link or, for a probe, the `probe` itself.
- **partial**: holds for some cases. `note` names the rest.
- **asserted**: the code reads as correct, and a comment, doc, or one-off agent or human check says so. Nothing re-checks it on change.
- **gap**: does not hold. `note` names the ticket or says "No ticket." A gap needs no `evidence`. When the thing is missing, the note says where you searched.

A claim that something is absent ("we do not sync") has no assertion to link, so it is `asserted`, with a note naming the search that found nothing.

`enforcedBy` is one of `test`, `lint`, `type`, `probe`, `agent`, `review`, `comment`, and a `gap` leaves it out. Only the first four are mechanical, so only they can back `proven`. `agent` means an agent read the code once, `review` means a person did, and `comment` means only a comment or doc says so.

`liveFrom` is a `YYYY-MM-DD` date for a leaf whose behavior is in the code but not in effect yet, such as a plan enforcement date. Before it the leaf counts as a gap, qualified "live from" that date. From it the leaf's own grade applies, with no edit.

`evidence` links are `{ repo, sha, path, line, label? }`, pinned to the commit that was read. A `source` link may instead be `{ url, label? }` for a web page outside any repo we snapshot, such as another company's docs.

## Probes

Some claims no test in the repo can settle: what a deployed service returns, what live data holds, what another system does. A leaf with `enforcedBy: probe` carries `probe`: `{ "run", "timeout"? }`.

- `run` is a shell command that exits 0 when the claim holds. It runs from the root of the checkout the tree file is in. `timeout` is in seconds, 300 when left out.
- A probe only reads. It must not change the thing it checks.
- `check.py <tree>.json --probe` runs every probe in the tree and the trees it refs. A leaf whose probe fails grades as a gap for that run, qualified "probe failed", and the script exits 1.
- A `gap` leaf may carry a probe as its "done when". `--probe` names it once the probe passes, and the leaf is then graded again by hand.
- Probes run only with `--probe`. They are shell commands, so read them before running a tree you did not write.

## Stale evidence

A grade is as old as the commit its links are pinned to. `check.py <tree>.json --stale [REV]` names every node with an `evidence` or `source` file that differs between its pinned commit and `REV` (`HEAD` when left out), and exits 1 when it names any.

- It looks each link's `repo` up by the origin URL of the checkout the tree is in. Pass `--repo <checkout>` once for every other repo the links name. A repo with no checkout is listed as not checked.
- A stale node is not wrong. Grade it again against `REV` and pin its links to that commit, which clears it.
- It also lists the graded leaves with no link to track. Only a full regrade re-checks those.

## Regressions

`check.py <tree>.json --diff REV` grades the tree as it was committed at `REV`, grades it as it is now, and names what changed: the claims that got worse, the ones that got better, each status that changed, and the claims added or removed. It exits 1 when a claim that counts got worse, so it works as a gate on a pull request (`--diff origin/main`).

- Claims are matched by id, so renaming an id reads as one claim removed and one added.
- A branch is named only when none of its children explains the change, such as a definition reworded since review.
- A claim that got worse under a `planned`, `proposed`, or `cut` node is listed with that status and does not fail the run. A status change is listed too, so moving a broken claim out of `shipped` is visible to whoever reviews the change.
- It reads the old copy of the tree and of every tree it refs from git, so the tree has to be in a checkout.

## Rollup

Grades rank `proven` > `partial` > `asserted` > `open` > `gap`. A branch takes the weakest grade among its children that count (by default the `shipped` ones), capped at `asserted` until it is reviewed and its digest matches. A branch with no child that counts is `open`. A ref takes the grade of the node it points at.

The qualified statement is the root claim plus everything below it that counts and is not proven: each non-proven leaf, open node, and ref, and each branch that is unreviewed or changed since review. After that it lists the `planned` and the `cut` children, each by its own claim. The grade tally counts only the leaves that count, and a second line counts the rest by status.

## The page

`check.py <tree>.json --html <page>.html` builds one page per tree, laid out like a claim deck: a cover with the tally, one slide per open decision, one slide per map, and every claim as an outline. `maps` and `decisions` are optional, and the page is where the person reads the tree and answers questions about it. `diagram.md` has the diagram grammar and how an element is bound to claims.

### Maps

A map is the tree, or one branch of it, drawn as a single picture: `{ "title", "caption"?, "diagram" }`. Each state and step in the diagram is bound to the claims about it, and takes the color of the weakest. Selecting one on the page lists its claims, notes, and links.

Between them, a tree's maps should draw every leaf. `check.py` prints how many leaves the maps draw and names the ones left out. Binding a branch draws every leaf under it, so a large tree still fits in one picture.

### Decisions

A decision is one question the person has to answer, as one slide:

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | The question or finding, in one sentence |
| `claims` | yes | The nodes it is about. A name is an id in this tree or `other.json#id`. |
| `band` | no | Short tag for its kind or rank: `False about money`, `Assumption`, `Definition` |
| `points` | no | `[{ "label", "text" }]`, at most 3: the facts needed to decide, such as "We say" and "The code does" |
| `options` | yes | `[{ "label", "detail"? }]`, 2 to 4, your recommendation first. `detail` is what choosing it costs or changes, in one sentence. |
| `diagram` | yes, or `map` | The states the question is about. Draw each option worth drawing as a way out. |
| `map` | instead of `diagram` | The title of one of this tree's maps, when the question is about the whole picture, such as a definition to review |
| `caption` | no | One line under the diagram |

`decisions` holds open questions only. When the person answers one, record the answer where it belongs (a `reviewed` stamp, a leaf's `note`, a reworded claim, a ticket) and delete the decision.
