# Curator run — 2026-05-13T06:23:49.517255+00:00

Model: `(not resolved)` via `(not resolved)`  ·  Duration: 5s  ·  Agent-created skills: 5 → 5 (+0)

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

I'll scan the candidate list and identify umbrella opportunities. Let me read each skill to make informed consolidation decisions.

I see two obvious prefix clusters:
- **hermes-config-*** (3 skills: init, update, validate)
- **pr-review-*** (2 skills: checklist, merge-prep)

Let me view each to assess content overlap and umbrella structure.
{"name": "skill_view", "arguments": {"name": "hermes-config-init"}}

## Recovery

- Restore an archived skill: `hermes curator restore <name>`
- All archives live under `~/.hermes/skills/.archive/` and are recoverable by `mv`
- See `run.json` in this directory for the full machine-readable record.
