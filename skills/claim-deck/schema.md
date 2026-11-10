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
| `diagram` | yes | See `../claim/diagram.md` |

### Grades

- **proven**: an automated test asserts the claim directly, against a real database when the claim is about SQL. Needs a `proofLink`.
- **partial**: tested for some cases or one side of a mirror; `risk` names the untested side.
- **asserted**: the code reads as correct and a comment or the PR body says so, but no test asserts the claim itself. `proof` starts with `None`, or names the adjacent test and what it does not assert.
- **gap**: the author says it does not hold yet and the code confirms it. `proof` starts with `None`, or names the test that deliberately stops short; `risk` names the ticket or says there is none.
- **deviation**: the spec says one thing, the code does another on purpose. `title` is the spec's sentence; `enforced` is what shipped and the inferred reason; `risk` says whether the PR body states the reason.

## Diagram

The grammar, the layout rules, and the table for picking a shape are in `../claim/diagram.md`. A deck has no claim tree, so its diagrams are colored with `status`, not bound to claims. The claim's path is lit (any status but `same`); everything else is `same` or `dim: true`.
