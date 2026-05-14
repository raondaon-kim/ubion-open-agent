# Copyright (c) 2026 Ubion ax center
"""End-to-end demo runner for the vendored curator port.

Wires together:
  - fixtures/skills/  (5 agent-created skills with .usage.json)
  - hermes_constants shim → agent_home.get_hermes_home
  - tools/__init__.py shim → top-level skill_usage
  - run_agent shim → mock_agent.AIAgent (real Anthropic call)
  - curator.py (vendor copy)

Run as:
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python run_demo.py

The script:
  1. Points UBION_AGENT_HOME at ./fixtures so curator reads our test skills.
  2. Resets .curator_state so should_run_now() returns True.
  3. Calls curator.run_curator_review(synchronous=True, dry_run=True).
  4. Writes the LLM's review output to output/run-<timestamp>.log.
  5. Prints a summary.

dry_run=True means the LLM is asked to REPORT what it would do, but no
skill_manage tool calls would actually be executed (and our mock doesn't
expose tools anyway, so this is just belt-and-suspenders).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Load ANTHROPIC_API_KEY (and anything else) from sandbox-local .env if
# present.  Real Anthropic calls fail without the key, so we look here
# before the OS env so users can keep the key out of their global shell.
try:
    from dotenv import load_dotenv

    load_dotenv(HERE / ".env")
except ImportError:
    # python-dotenv not installed — fine, we'll just rely on the OS env.
    pass

os.environ["UBION_AGENT_HOME"] = str(HERE / "fixtures")
# Make our sandbox importable as a flat package
sys.path.insert(0, str(HERE))

# Configure logging *before* importing curator so its module-level logger
# inherits the right level.
logging.basicConfig(
    level=os.environ.get("DEMO_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)

import curator
import skill_usage


def _reset_state() -> None:
    """Wipe ``.curator_state`` so ``should_run_now()`` returns True on a fresh
    fixtures tree."""
    state_path = HERE / "fixtures" / "skills" / ".curator_state"
    if state_path.exists():
        state_path.unlink()
    # And make sure no `.curator_state` from a previous run lingers under
    # a different relative-path interpretation.


def _summarize_fixtures() -> None:
    names = skill_usage.list_agent_created_skill_names()
    print(f"[demo] agent-created candidates found: {len(names)}")
    for n in names:
        print(f"       - {n}")
    print()


def _record_output(result: dict) -> Path:
    out_dir = HERE / "output"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = out_dir / f"run-{ts}.log"
    log_path.write_text(
        json.dumps(result, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    return log_path


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2

    print(f"[demo] UBION_AGENT_HOME = {os.environ['UBION_AGENT_HOME']}")
    _summarize_fixtures()

    _reset_state()

    print("[demo] invoking curator.run_curator_review(synchronous=True, dry_run=True)")
    print("[demo] (this calls Claude - expect 10-60s and a billable API charge)")
    print()
    result = curator.run_curator_review(synchronous=True, dry_run=True)

    # The return value only carries the synchronous "pre-LLM" portion
    # (auto_transitions, started_at). The LLM pass writes its result to
    # `.curator_state["last_run_summary"]` and a per-run REPORT.md whose
    # path is recorded in `.curator_state["last_report_path"]`. Read both.
    state = curator.load_state()

    combined = {
        "return_value": result,
        "state_after_run": state,
    }
    # `last_report_path` is a DIRECTORY (logs/curator/<timestamp>/) holding
    # both run.json and REPORT.md - see curator.py:_write_run_report.
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
    print()
    print(f"[demo] full result written to {log_path.relative_to(HERE)}")
    print()
    print("[demo] auto_transitions (pure, no LLM):")
    for k, v in result.get("auto_transitions", {}).items():
        print(f"       {k}: {v}")
    print()
    print("[demo] state.last_run_summary:")
    print(f"       {state.get('last_run_summary')}")
    print()
    if report_dir_str:
        print(f"[demo] per-run report directory: {report_dir_str}")
        if report_md_path is not None:
            print(f"[demo]   REPORT.md: {report_md_path}")
        if "run_json" in combined:
            print(f"[demo]   run.json:  {Path(report_dir_str) / 'run.json'}")
        print()
        if "report_md" in combined:
            preview = combined["report_md"]
            print("=" * 72)
            print("REPORT.md (first 3000 chars):")
            print("=" * 72)
            print(preview[:3000])
            if len(preview) > 3000:
                print(f"... ({len(preview) - 3000} more chars in REPORT.md)")
    else:
        print("[demo] no report path recorded - LLM pass may have failed early")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
