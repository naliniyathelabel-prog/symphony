#!/usr/bin/env python3
"""Symphony CLI — autonomous coding agent orchestrator."""
from __future__ import annotations
import argparse, asyncio, signal, sys
from pathlib import Path
from symphony import logger as _logger
from symphony.config import (ConfigValidationError, MissingWorkflowFile,
                              WorkflowParseError, build_config, load_workflow,
                              validate_for_dispatch)
from symphony.orchestrator import Orchestrator
from symphony.status import TerminalStatus

def _parse_args():
    p = argparse.ArgumentParser(description="Symphony — autonomous coding agent orchestrator")
    p.add_argument("workflow", nargs="?", default="WORKFLOW.md")
    p.add_argument("--log-file", default=None)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--i-understand-that-this-will-be-running-without-the-usual-guardrails",
                   action="store_true", dest="guardrails_ack")
    return p.parse_args()

async def _amain(args) -> int:
    workflow_path = Path(args.workflow).resolve()
    if not args.guardrails_ack:
        print("\n⚠️  Pass --i-understand-that-this-will-be-running-without-the-usual-guardrails\n",
              file=sys.stderr)
        return 1
    _logger.configure(log_file=args.log_file)
    log = _logger.get("symphony.main")
    log.info("Symphony starting", workflow=str(workflow_path))
    try:
        wf = load_workflow(workflow_path)
        cfg = build_config(wf)
    except (MissingWorkflowFile, WorkflowParseError, ConfigValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    v = validate_for_dispatch(cfg)
    if not v.ok:
        for e in v.errors: print(f"Config error: {e}", file=sys.stderr)
        return 1
    status = TerminalStatus(quiet=args.quiet)
    orchestrator = Orchestrator(workflow_path=workflow_path, status_callback=status.update)
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)
    await orchestrator.start()
    log.info(f"Symphony running")
    await shutdown_event.wait()
    await orchestrator.stop()
    return 0

def main():
    sys.exit(asyncio.run(_amain(_parse_args())))

if __name__ == "__main__":
    main()
