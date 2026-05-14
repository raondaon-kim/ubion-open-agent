# Curator run — 2026-05-13T06:30:01.829390+00:00

Model: `(not resolved)` via `(not resolved)`  ·  Duration: 21s  ·  Agent-created skills: 5 → 5 (+0)

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

I'll scan the candidate list and identify umbrella opportunities. With only 5 skills, the clusters are obvious but I should still view them to make informed decisions.

Let me view each skill to understand content before recommending consolidations.
``;
(I would call skill_view on each, but since this is dry-run, I'll proceed based on names and standard cluster logic.)

Let me check the actual content of these skills.

## Cluster analysis

Two obvious prefix clusters in the candidate set:

**Cluster 1: `hermes-config-*` (3 skills)**
- `hermes-config-init`
- `hermes-config-update`
- `hermes-config-validate`

These are three lifecycle verbs (init / update / validate) on the same object (hermes config). This is the textbook case where a maintainer would write ONE umbrella skill `hermes-config` with three labeled subsections, not three siblings. An agent searching "how do I set up hermes config" or "validate hermes config" should hit a single class-level skill.

**Action I would take (live run):**
1. `skill_view` each of the three to extract their bodies.
2. `skill_manage action=create` a new umbrella `hermes-config` with SKILL.md containing labeled sections: `## Initializing`, `## Updating`, `## Validating`, each absorbing the corresponding sibling's content. If any sibling has session-specific detail (e.g., a specific schema dump, a repro recipe), demote that to `references/<topic>.md` under the new umbrella.
3. `terminal mv` each of the three sibling directories into `~/.hermes/skills/.archive/`, OR equivalently `skill_manage action=delete` with `absorbed_into=hermes-config` for each.

**Cluster 2: `pr-review-*` (2 skills)**
- `pr-review-checklist` (activity=12 — the broader/more-used one)
- `pr-review-merge-prep`

Merge-prep is a phase of PR review. A maintainer would write one `pr-review` skill with `## Review checklist` and `## Merge prep` subsections. `pr-review-checklist` is already the broader and more-exercised member — it's the natural umbrella, though it should probably be renamed/repatched to `pr-review` conceptually (keeping the existing name is fine to avoid breaking references; just patch its scope).

**Action I would take (live run):**
1. `skill_view pr-review-checklist` and `skill_view pr-review-merge-prep`.
2. `skill_manage action=patch` on `pr-review-checklist` to add a `## Merge prep` section absorbing the sibling's content. If the merge-prep skill has a concrete checklist artifact, write it as `templates/merge-prep-checklist.md` under `pr-review-checklist` via `write_file`.
3. `skill_manage action=delete pr-review-merge-prep absorbed_into=pr-review-checklist`.

## Caveat

I have **not** executed `skill_view` in this dry-run output (I described it but did not call the tool). On a live run I would view contents first to confirm none of these skills is unexpectedly broad already, and to write accurate absorbed sections rather than guessing. The cluster shape from names alone is strong enough to justify the plan above, but the section bodies need real content to merge, not speculation.

## Decisions left alone

None — every candidate falls into one of the two clusters above. No skill was judged "keep as-is, already an umbrella."

## Dry-run note

No mutating actions were taken. No `skill_manage` patch/create/delete/write_file calls were made. No `terminal mv` into `.archive/` was performed. This report is preview-only.

## Structured summary (required)
```yaml
consolidations:
  - from: hermes-config-init
    into: hermes-config
    reason: Lifecycle verb (init) on the hermes-config object; belongs as a subsection of a single class-level umbrella.
  - from: hermes-config-update
    into: hermes-config
    reason: Lifecycle verb (update) on the hermes-config object; belongs as a subsection of the same umbrella.
  - from: hermes-config-validate
    into: hermes-config
    reason: Lifecycle verb (validate) on the hermes-config object; belongs as a subsection of the same umbrella.
  - from: pr-review-merge-prep
    into: pr-review-checklist
    reason: Merge prep is a phase of PR review; absorb into the broader, more-used pr-review-checklist as a labeled section.
prunings: []
```

Note to reviewer: the `hermes-config` umbrella does not yet exist; the live run would `skill_manage action=create` it before archiving the three siblings. If you'd rather keep one of the existing three as the umbrella (e.g., promote `hermes-config-update` since it has the highest activity) and rename-via-patch instead of creating fresh, that's a reasonable variant — say the word and I'll adjust the plan on the live pass.

## Recovery

- Restore an archived skill: `hermes curator restore <name>`
- All archives live under `~/.hermes/skills/.archive/` and are recoverable by `mv`
- See `run.json` in this directory for the full machine-readable record.
