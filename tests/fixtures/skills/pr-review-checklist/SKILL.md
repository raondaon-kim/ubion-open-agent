---
name: pr-review-checklist
description: Walk a GitHub pull request through a fixed review checklist (CI green, tests added, docs touched, breaking changes flagged).
---

# pr-review-checklist

Given a PR number, fetch it via `gh pr view <num> --json` and verify each
item in the standard team checklist.  Returns a markdown report.

## Checklist items

1. CI status is green (all required checks passed).
2. At least one test file is modified in the diff.
3. If a public API surface changed, the corresponding docs file is also
   in the diff.
4. The PR description has a "Breaking changes" section if any
   user-visible behavior changed.
5. Linked issue (if any) is in the right project board.

## Output

```
PR #123 — pr-review-checklist
  ✓ CI green
  ✓ tests added
  ✗ docs missing for new flag --foo
  ...
```
