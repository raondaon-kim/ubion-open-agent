---
name: hermes-config-validate
description: Check ~/.hermes/config.yaml against the expected schema and report missing or malformed fields.
---

# hermes-config-validate

Loads `~/.hermes/config.yaml` and validates that the required top-level
sections exist (`model`, `tools`) and that the provider value is in the
known set.

## Steps

1. Load the file.  If missing, report and exit (point user at
   `hermes-config-init`).
2. Check `model.provider` is one of {anthropic, openai, openrouter, local}.
3. Check `model.default` is a non-empty string (warning, not error).
4. Check `tools.enabled` is a list of known toolset names.

## Output

Prints either `config.yaml: OK` or a bulleted list of issues found.
