# Diagrams

Every map and decision in a claim tree, and every claim in a claim deck, carries one small flowchart on a grid. `check.py` and `claim-deck/build.py` validate it, and `flow.js` draws it.

Keep a diagram to 4 to 9 nodes, 12 at most. Labels are short: two lines of about 24 characters. Something must be lit: bound to claims, or given a status other than `same`. Everything else is context, so leave it `same` or set `dim: true`.

```json
{
  "colW": 215, "rowH": 92, "nodeW": 180, "nodeH": 50,
  "lanes": [{ "label": "Caller A", "cols": [0, 0] }],
  "regions": [{ "label": "one transaction", "cols": [0, 0], "rows": [1, 4], "stroke": "var(--warn)" }],
  "nodes": [{ "id": "a", "label": "line one\nline two", "col": 0, "row": 0, "type": "decision", "status": "added", "dim": false, "badge": "✓" }],
  "edges": [{ "from": "a", "to": "b", "label": "yes ✓", "status": "covered", "dim": false }]
}
```

Node `type`: `process` (default), `decision` (diamond), `terminal` (pill; use for states and endpoints), `note` (dashed, for annotations).

Node `status`: `same` (grey), `added` (teal), `changed` (amber), `removed` (red, faded), `gap` (red), `deferred` (amber), `covered` (green), `async` (purple).

Edge `status`: `same` (grey), `added` (teal), `covered` (green, a test takes this edge), `uncovered` (red dashed, no test takes it), `gap` (red dashed), `deferred` (amber), `async` (dotted purple, a queue or worker hop), `removed` (red dashed).

Node `badge`: `✓` tested, `!` stated risk, `×` known gap.

`lanes` turns the grid into swimlanes: each lane spans a column range and gets a header. `regions` draws a dashed box around a block of cells, for a transaction or a "must agree" pair.

Layout rules the renderer assumes:
- Edges to a lower row leave the bottom of the source and enter the top of the target.
- Edges on the same row run sideways, so do not put a third node between the two.
- Edges to a higher row loop around the right side.
- Two nodes may not share a `(col, row)` cell.

## Binding to claims

In a claim tree, a node or edge may name the claims it stands for:

```json
{ "from": "open", "to": "closed", "label": "close", "claims": ["close-freezes", "close-locks"] }
```

A name is a node id in the same tree, or `other.json#id` for a node in another tree. A bound element ignores its own `status` and takes the color of its weakest claim: proven green, partial amber, asserted dotted purple, gap red, open grey. Bind wherever you can and never color a claim by hand: a bound picture cannot disagree with the tree, and it recolors itself when the leaves are graded again. Use `status` only for things that are not claims, such as an option nobody has taken yet.

Claim decks have no tree, so their diagrams use `status` alone.

## Picking a shape

| The picture is of | Draw |
|---|---|
| A whole feature or branch (a map) | Lifecycle: one `terminal` per state, one edge per action, each bound to the claims about it. Side effects hang below the state they happen in. |
| A list with no lifecycle, such as areas or plan tiers (a map) | Fan-out: the root on the left, one bound node per part |
| A decision between options | The mismatch on the top row, bound to the claims in question. Below it, one `terminal` per option worth drawing, reached by an `added` edge for the recommended one and a `same` edge for the others. |
| A definition to review | The branch as a lifecycle or fan-out with every child bound, so a missing child shows as a step with no claim |
| Two products, or two things that must agree | Two lanes, one rung per claim, each rung bound to its own side's leaf, a `same answer` edge between them |
| Task order | One node per task bound to its leaves, an edge for each "depends on", parallel tasks on the same row |
| An invariant that survives change | Lifecycle: `terminal` states, the preserving transition lit, the mutations as a `note` |
| A predicate or branch | Decision flow: the `decision` node and the lit branch, the other branch `dim` |
| Atomicity or ordering | Swimlanes with a `region` around the transaction and an `async` edge for the queue hop |
| Concurrency | Swimlanes, one per caller, the lock as the first node |
| Reach or inheritance | Fan-out from the changed node; untested consumers get `uncovered` edges |
| A known gap | The wrong transition in `gap` red; the intended one `dim` with `uncovered` |
| Performance | Fan-out of per-row costs; the missing measurement as a `gap` terminal |
