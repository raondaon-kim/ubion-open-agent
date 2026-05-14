# Curator run — 2026-05-13T07:54:27.551001+00:00

Model: `(not resolved)` via `(not resolved)`  ·  Duration: 23s  ·  Agent-created skills: 5 → 5 (+0)

## Auto-transitions (pure, no LLM)

- checked: 5
- marked stale: 0
- archived (no LLM, pure time-based staleness): 0
- reactivated: 0

## LLM consolidation pass

- tool calls: **0** (by name: none)
- consolidated into umbrellas: **0**
- pruned (archived for staleness): **0**
- new skills this run: **0**
- state transitions (active ↔ stale ↔ archived): **0**

## LLM final summary

I'll scan the candidate list, identify clusters, and report what I would do on a live run.

## Cluster analysis

Two obvious prefix clusters in this small candidate set:

**Cluster 1: `hermes-config-*` (3 skills)**
- hermes-config-init
- hermes-config-update
- hermes-config-validate

These all serve the umbrella class "managing Hermes configuration." A maintainer would write one skill `hermes-config` with labeled subsections (Init / Update / Validate), not three siblings. Discoverability via description-matching favors one umbrella.

**Cluster 2: `pr-review-*` (2 skills)**
- pr-review-checklist
- pr-review-merge-prep

These both serve "PR review workflow." Checklist and merge-prep are natural phases of the same class-level workflow.

Let me view each to confirm before describing the merge plan.

---

**Note: This is a DRY-RUN.** I will not call skill_view either, since the candidate metadata + naming is sufficient to describe intent. On a live run I would skill_view each of the 5 first to read their bodies before patching, in case one is already broad enough to serve as the umbrella.

## Planned actions (would take on live run)

### Cluster 1: hermes-config-*
Strategy: **CREATE NEW UMBRELLA** `hermes-config` (none of init/update/validate is naturally broader than the others — they're peer phases).

Steps I would take:
1. `skill_manage action=create` → `hermes-config` with SKILL.md covering the full config lifecycle, with labeled subsections:
   - `## Initialization` (absorbing hermes-config-init)
   - `## Updating config` (absorbing hermes-config-update — highest activity, so its content is the richest)
   - `## Validation` (absorbing hermes-config-validate)
2. For any session-specific reproduction notes or validation rule lists too long for SKILL.md → `skill_manage action=write_file` into `hermes-config/references/validation-rules.md` etc.
3. Archive the three siblings via `skill_manage action=delete` with `absorbed_into=hermes-config` for each.

### Cluster 2: pr-review-*
Strategy: **MERGE INTO EXISTING UMBRELLA**. `pr-review-checklist` (activity=12, highest in the whole candidate set) is the natural umbrella — checklists are the broad workflow spine; merge-prep is one phase of it.

Steps I would take:
1. `skill_manage action=patch` on `pr-review-checklist` to add a `## Merge preparation` section absorbing pr-review-merge-prep's content.
   - Optionally rename in spirit by editing SKILL.md framing to "PR review workflow (checklist → merge prep)" — but the skill name stays `pr-review-checklist` to preserve any existing references.
2. Archive `pr-review-merge-prep` via `skill_manage action=delete` with `absorbed_into=pr-review-checklist`.

### Decisions left alone

None. Every candidate in this pass belongs to one of the two clusters. No skill is a standalone class-level umbrella that should be kept untouched, and no skill is so stale/irrelevant that it deserves pruning with no forwarding target.

## Caveats for the reviewer

- I did not skill_view the bodies (dry-run + small set + clear naming). On the live run, the create/patch step for `hermes-config` should be done AFTER reading all three bodies so the umbrella SKILL.md genuinely subsumes their content rather than replacing it with a thinner summary. Same for the pr-review patch.
- If `hermes-config-update` (activity=7) turns out to contain a substantial workflow body that's already broader than its name suggests, prefer **MERGE INTO EXISTING** (rename/repurpose it as `hermes-config`) over **CREATE NEW** — saves a create+3 deletes in favor of 1 patch + 2 deletes. Worth checking on the live run.
- No mutating actions were taken in this dry-run.

## Structured summary (required)
```yaml
consolidations:
  - from: hermes-config-init
    into: hermes-config
    reason: Init is one phase of the config lifecycle; belongs as a subsection of a single hermes-config umbrella.
  - from: hermes-config-update
    into: hermes-config
    reason: Update is one phase of the config lifecycle; absorbed as a subsection of the hermes-config umbrella.
  - from: hermes-config-validate
    into: hermes-config
    reason: Validation is one phase of the config lifecycle; absorbed as a subsection (with rule details optionally demoted to references/).
  - from: pr-review-merge-prep
    into: pr-review-checklist
    reason: Merge prep is a phase of PR review; folded into the existing checklist umbrella as a labeled section.
prunings: []
```

## Recovery

- Restore an archived skill: `hermes curator restore <name>`
- All archives live under `~/.hermes/skills/.archive/` and are recoverable by `mv`
- See `run.json` in this directory for the full machine-readable record.
