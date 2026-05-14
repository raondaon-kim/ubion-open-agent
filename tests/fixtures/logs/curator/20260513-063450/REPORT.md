# Curator run — 2026-05-13T06:34:50.893947+00:00

Model: `(not resolved)` via `(not resolved)`  ·  Duration: 22s  ·  Agent-created skills: 5 → 5 (+0)

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

I'll scan the candidate list, identify clusters, and produce a dry-run report describing what I *would* do on a live pass.

## Cluster scan

Five agent-created skills, two obvious prefix clusters:

**Cluster A: `hermes-config-*` (3 skills)**
- `hermes-config-init`
- `hermes-config-update`
- `hermes-config-validate`

These are three lifecycle verbs (init / update / validate) over the same object: Hermes config. A human maintainer would absolutely write this as ONE skill called something like `hermes-config` with three labeled subsections (Initializing, Updating, Validating), not three siblings an agent has to disambiguate by trigger. Classic umbrella candidate.

**Cluster B: `pr-review-*` (2 skills)**
- `pr-review-checklist`
- `pr-review-merge-prep`

Two phases of the same PR review workflow. Checklist runs during review; merge-prep runs at the tail end. Same class (reviewing a PR), different stages. Would belong as two labeled subsections under a single `pr-review` umbrella.

## What I would do on a live run

Before patching, I would `skill_view` each of the five skills to read their full SKILL.md content so the umbrellas preserve every concrete instruction. Assuming the content is roughly what the names imply:

### Action A1: Create umbrella `hermes-config`
- `skill_manage action=create name=hermes-config` with a SKILL.md whose body has three labeled sections — `## Initializing a new config`, `## Updating an existing config`, `## Validating config` — populated from the three siblings' bodies. Description would cover the full lifecycle so search hits regardless of which verb the agent is thinking about.
- If any sibling has session-specific reproduction notes or example configs too detailed for the umbrella body, demote those to `references/<topic>.md` or `templates/<name>` under `hermes-config/` via `skill_manage action=write_file`.

### Action A2: Archive the three siblings
- `skill_manage action=delete name=hermes-config-init absorbed_into=hermes-config`
- `skill_manage action=delete name=hermes-config-update absorbed_into=hermes-config`
- `skill_manage action=delete name=hermes-config-validate absorbed_into=hermes-config`

### Action B1: Promote `pr-review-checklist` to umbrella `pr-review`
`pr-review-checklist` has the higher activity (12) and the broader-sounding name; it's the natural umbrella host. I would:
- `skill_manage action=patch name=pr-review-checklist` to (a) rename conceptually by adding a `## Merge prep` section absorbing `pr-review-merge-prep`'s content, and (b) broaden the description to cover both review and merge-prep phases.
- Then `terminal mv ~/.hermes/skills/pr-review-checklist ~/.hermes/skills/pr-review` to rename the directory to the class-level name — OR, if rename-via-mv isn't safe with the skill index, leave the name as `pr-review-checklist` and just broaden description + body. I'd lean toward the rename for discoverability; flagging the choice for the reviewer.

### Action B2: Archive the sibling
- `skill_manage action=delete name=pr-review-merge-prep absorbed_into=pr-review` (or `absorbed_into=pr-review-checklist` if the rename is skipped)

## Decisions left alone

None. Every agent-created skill in the candidate list falls into one of the two clusters above. No skill is already a class-level umbrella that should be left untouched, and no skill is truly stale (all have recent activity within the last ~6 weeks).

## Total impact

- 2 umbrellas (1 created, 1 promoted via patch)
- 4 archives, all consolidations, zero prunings

Note: this is a small candidate set (5 skills). The instructions warn that fewer than 10 archives suggests stopping too early, but that bar assumes a typical hundreds-of-skills landscape. Here the entire agent-created surface is 5 skills and I'm consolidating 4 of them. There is no remaining cluster to process.

## Dry-run compliance

No mutating tool calls were issued. No `skill_manage` patch/create/delete/write_file/remove_file. No `terminal mv` into `.archive/` or anywhere under `~/.hermes/skills/`. Skill library is unchanged.

## Structured summary (required)
```yaml
consolidations:
  - from: hermes-config-init
    into: hermes-config
    reason: Init is one lifecycle phase of Hermes config; belongs as a labeled subsection under a single config umbrella.
  - from: hermes-config-update
    into: hermes-config
    reason: Update is one lifecycle phase of Hermes config; belongs as a labeled subsection under a single config umbrella.
  - from: hermes-config-validate
    into: hermes-config
    reason: Validation is one lifecycle phase of Hermes config; belongs as a labeled subsection under a single config umbrella.
  - from: pr-review-merge-prep
    into: pr-review-checklist
    reason: Merge prep is the tail phase of the PR review workflow already covered by pr-review-checklist; one umbrella with a Merge prep subsection beats two siblings.
prunings: []
```

## Recovery

- Restore an archived skill: `hermes curator restore <name>`
- All archives live under `~/.hermes/skills/.archive/` and are recoverable by `mv`
- See `run.json` in this directory for the full machine-readable record.
