# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 2 end-to-end smoke test.

Runs the vendored curator (engine.learning.curator) using our new
engine.core.agent.AIAgent — i.e. the Mock AIAgent is gone, the curator
review fork now hits a real Claude API call through engine.llm.anthropic.

Mirrors sandbox/skill-loop-port/run_demo.py but points at the engine
package instead of the sandbox files. If this script's output matches the
Phase 0 sandbox run (clusters identified, REPORT.md generated), Unit 2 is
GREEN per phase-1-todo.md.

Run as:
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python -m engine.run_demo

Requires ANTHROPIC_API_KEY in env or in a `.env` file alongside this
module (loaded if python-dotenv is installed).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

# .env (project-root level) — keeps secrets out of the package itself.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    # Also accept the same .env we used in Phase 0 (sandbox).
    load_dotenv(PROJECT_ROOT / "sandbox" / "skill-loop-port" / ".env")
except ImportError:
    pass

# Point UBION_AGENT_HOME at the test fixtures so curator scans them.
os.environ.setdefault(
    "UBION_AGENT_HOME", str(PROJECT_ROOT / "tests" / "fixtures")
)

logging.basicConfig(
    level=os.environ.get("DEMO_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)

from engine.learning import curator
from engine.skills import usage as skill_usage


def _reset_state() -> None:
    """Delete .curator_state so should_run_now() doesn't matter (we call
    run_curator_review directly anyway, but cleanliness)."""
    state_path = Path(os.environ["UBION_AGENT_HOME"]) / "skills" / ".curator_state"
    if state_path.exists():
        state_path.unlink()


def _summarize_fixtures() -> None:
    names = skill_usage.list_agent_created_skill_names()
    print(f"[demo] agent-created candidates found: {len(names)}")
    for n in names:
        print(f"       - {n}")
    print()


def _record_output(combined: dict) -> Path:
    out_dir = PROJECT_ROOT / "tests" / "output"
    out_dir.mkdir(exist_ok=True, parents=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = out_dir / f"unit2-run-{ts}.log"
    log_path.write_text(
        json.dumps(combined, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    return log_path


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2

    print(f"[demo] UBION_AGENT_HOME = {os.environ['UBION_AGENT_HOME']}")
    print(f"[demo] using engine.core.agent.AIAgent (Mock retired)")
    _summarize_fixtures()
    _reset_state()

    print("[demo] invoking curator.run_curator_review(synchronous=True, dry_run=True)")
    print("[demo] (real Claude API call - expect 10-60s)")
    print()
    result = curator.run_curator_review(synchronous=True, dry_run=True)

    state = curator.load_state()
    combined = {
        "return_value": result,
        "state_after_run": state,
    }
    report_dir_str = state.get("last_report_path")
    report_md_path: Path | None = None
    if report_dir_str:
        report_dir = Path(report_dir_str)
        candidate = report_dir / "REPORT.md"
        if candidate.exists():
            report_md_path = candidate
            combined["report_md"] = candidate.read_text(encoding="utf-8")
        run_json = report_dir / "run.json"
        if run_json.exists():
            combined["run_json"] = json.loads(run_json.read_text(encoding="utf-8"))

    log_path = _record_output(combined)
    print(f"[demo] full result written to {log_path.relative_to(PROJECT_ROOT)}")
    print()
    print("[demo] auto_transitions (pure, no LLM):")
    for k, v in result.get("auto_transitions", {}).items():
        print(f"       {k}: {v}")
    print()
    print("[demo] state.last_run_summary:")
    print(f"       {state.get('last_run_summary')}")
    print()
    if report_md_path is not None:
        preview = combined["report_md"]
        print("=" * 72)
        print(f"REPORT.md (first 3000 chars) - {report_md_path}")
        print("=" * 72)
        print(preview[:3000])
        if len(preview) > 3000:
            print(f"... ({len(preview) - 3000} more chars in REPORT.md)")
    else:
        print("[demo] no REPORT.md - LLM pass may have failed early")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
