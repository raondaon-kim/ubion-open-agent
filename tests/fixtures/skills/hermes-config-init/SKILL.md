---
name: hermes-config-init
description: Initialize a fresh ~/.hermes/config.yaml from scratch when none exists.
---

# hermes-config-init

When a user installs Hermes for the first time and runs the agent without
ever having executed `hermes setup`, the config file is missing.  This
skill writes a minimal config.yaml with the model provider set to
"anthropic" and the model field left blank for the user to fill in.

## Steps

1. Check whether `~/.hermes/config.yaml` exists.  If yes, abort — never
   overwrite an existing config.
2. Create `~/.hermes/` directory if missing (`mkdir -p`).
3. Write the following minimal YAML:

   ```yaml
   model:
     provider: anthropic
     default: ""
   tools:
     enabled: [terminal, file]
   ```

4. Print the path back to the user.
