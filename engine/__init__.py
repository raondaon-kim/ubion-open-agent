# Copyright (c) 2026 Ubion ax center
"""Self-Evolving Agent Platform — engine package.

This is the production engine that grew out of the Phase 0 sandbox
(`sandbox/skill-loop-port/`).  It contains:

  - learning/   skill curator + memory curator (Vendor copies from Hermes)
  - skills/     skill loading + usage telemetry
  - core/       agent loop, prompt builder, trajectory
  - storage/    agent home directory, file layout
  - llm/        provider adapters (Anthropic etc.)
  - tools/      whitelisted tool implementations (terminal, file ops)
  - server/     OpenAI-compatible HTTP server

License attribution for adapted Hermes code lives in `engine/NOTICE.md`.
"""
