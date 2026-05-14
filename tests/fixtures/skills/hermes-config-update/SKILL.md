---
name: hermes-config-update
description: Patch a specific key inside an existing ~/.hermes/config.yaml without rewriting unrelated sections.
---

# hermes-config-update

Updates a single dotted key in `~/.hermes/config.yaml` in place.  Preserves
comments and key ordering using ruamel.yaml.  Used when the user wants to
change one setting (model, provider, a tool flag) without re-running the
full setup wizard.

## Steps

1. Load `~/.hermes/config.yaml` with `ruamel.yaml.YAML(typ="rt")`.
2. Walk the dotted-path argument (e.g. `model.default`) and set the value.
3. Write back atomically (write to `.tmp` then `os.replace`).

## Caveats

- Will NOT create the file — see `hermes-config-init` for that case.
- Will NOT validate the value against a schema — see
  `hermes-config-validate` for that case.
