---
name: pr-review-merge-prep
description: Final pre-merge sweep on a GitHub PR — rebases on main, re-runs CI if stale, squashes commits to a single conventional-commit message.
---

# pr-review-merge-prep

Run this right before clicking "Merge" on a PR.  Catches the three failure
modes the team has seen most often:

1. PR was approved days ago, main has moved, CI is stale.
2. Commit history is a mess of "fix typo", "address review", etc. that
   would pollute main's log.
3. Commit message doesn't match the team's conventional-commits format.

## Steps

1. `gh pr checks <num>` — abort if any check is missing or stale.
2. `gh pr ready <num> && gh pr edit <num> --add-label ready-for-merge`.
3. Compose a single conventional-commit message from the PR title and
   the bullet list in the PR description.
4. Squash-merge via `gh pr merge <num> --squash --subject "<msg>"`.
