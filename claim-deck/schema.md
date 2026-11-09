# Claim deck JSON

One file per PR. `build.py` validates it and produces the page.

```json
{
  "title": "Scheduled Exports Claim Deck",
  "repo": "acme/app",
  "pr": 128,
  "sha": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
  "ticket": "APP-42",
  "headline": "optional one-sentence cover headline",
  "intro": "optional cover paragraph",
  "claims": [ { ...claim } ]
}
```

`sha` is the PR head commit every link is pinned to. Links are rendered as `https://github.com/<repo>/blob/<sha>/<path>#L<line>`.

## Claim

| Field | Required | Meaning |
|---|---|---|
| `grade` | yes | `proven`, `partial`, `asserted`, `gap`, or `deviation` (definitions below) |
| `title` | yes | The claim as one declarative sentence. For `deviation`, state what the spec says. |
| `area` | no | Short tag shown in the kicker: `feed · P&L`, `routes`, `APP-43` |
| `enforced` | yes | What in the code makes it true. For `gap`, where it fails. For `deviation`, what the code does instead and why. |
| `code` | no | A short verbatim snippet, at most ~6 lines |
| `links` | no | `[{ "path", "line", "endLine"?, "label"? }]` into the code |
| `proof` | yes* | The test and the assertion, with what it sets up and what it checks. Start with `None` when there is no test. |
| `proofLinks` | for `proven` | Links into the test file |
| `risk` | no | What is not covered, or the ticket this is handed to |
| `caption` | no | One line under the diagram |
| `diagram` | yes | See below |

### Grades

- **proven**: an automated test asserts the claim directly, against a real database when the claim is about SQL. Needs a `proofLink`.
- **partial**: tested for some cases or one side of a mirror; `risk` names the untested side.
- **asserted**: the code reads as correct and a comment or the PR body says so, but no test asserts the claim itself. `proof` starts with `None`, or names the adjacent test and what it does not assert.
- **gap**: the author says it does not hold yet and the code confirms it. `proof` starts with `None`, or names the test that deliberately stops short; `risk` names the ticket or says there is none.
- **deviation**: the spec says one thing, the code does another on purpose. `title` is the spec's sentence; `enforced` is what shipped and the inferred reason; `risk` says whether the PR body states the reason.

## Diagram

A small flowchart on a grid. Keep it to 4 to 9 nodes, 12 at most. The claim's path is lit (any status but `same`); everything else is `same` or `dim: true`.

```json
{
  "colW": 215, "rowH": 84, "nodeW": 180, "nodeH": 50,
  "lanes": [{ "label": "Caller A", "cols": [0, 0] }],
  "regions": [{ "label": "one transaction", "cols": [0, 0], "rows": [1, 4], "stroke": "var(--warn)" }],
  "nodes": [{ "id": "a", "label": "line one\nline two", "col": 0, "row": 0, "type": "decision", "status": "added", "dim": false, "badge": "✓" }],
  "edges": [{ "from": "a", "to": "b", "label": "yes ✓", "status": "covered", "dim": false }]
}
```

Node `type`: `process` (default), `decision` (diamond), `terminal` (pill; use for states and endpoints), `note` (dashed, for annotations).

Node `status`: `same` (grey), `added` (teal), `changed` (amber), `removed` (red, faded), `gap` (red), `deferred` (amber).

Edge `status`: `same` (grey), `added` (teal), `covered` (green, a test takes this edge), `uncovered` (red dashed, no test takes it), `gap` (red dashed), `deferred` (amber), `async` (dotted purple, a queue or worker hop), `removed` (red dashed).

Node `badge`: `✓` tested, `!` stated risk, `×` known gap.

`lanes` turns the grid into swimlanes: each lane spans a column range and gets a header. `regions` draws a dashed box around a block of cells, for a transaction or a "must agree" pair.

Layout rules the renderer assumes:
- Edges to a lower row leave the bottom of the source and enter the top of the target.
- Edges on the same row run sideways.
- Edges to a higher row loop around the right side.
- Two nodes may not share a `(col, row)` cell.

### Picking a shape

| Claim is about | Draw |
|---|---|
| An invariant that survives change | Lifecycle: `terminal` states, the preserving transition lit, the mutations as a `note` |
| A predicate or branch | Decision flow: the `decision` node and the lit branch, the other branch `dim` |
| Two things that must agree | Two ladders side by side, the new rung lit in both, a `same answer` edge between them |
| Atomicity or ordering | Swimlanes with a `region` around the transaction and an `async` edge for the queue hop |
| Concurrency | Swimlanes, one per caller, the lock as the first node |
| Reach or inheritance | Fan-out from the changed node; untested consumers get `uncovered` edges |
| A known gap | The wrong transition in `gap` red; the intended one `dim` with `uncovered` |
| Performance | Fan-out of per-row costs; the missing measurement as a `gap` terminal |
