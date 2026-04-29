"""Orchestrator per SPEC.md §7-8."""
from __future__ import annotations
import asyncio, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from .config import ServiceConfig, build_config, load_workflow, validate_for_dispatch
from .logger import get
from .models import OrchestratorState, RetryEntry, RunningEntry
from .tracker import LinearClient
from .workspace import WorkspaceManager
from .agent import AgentRunner, render_prompt

log = get("symphony.orchestrator")

class Orchestrator:
    def __init__(self, workflow_path: Path, status_callback: Optional[Callable]=None):
        self.workflow_path = workflow_path
        self.status_cb = status_callback or (lambda s: None)
        self._cfg: Optional[ServiceConfig] = None
        self._last_cfg_mtime: float = 0
        self._state = OrchestratorState()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._reload_task: Optional[asyncio.Task] = None

    async def start(self):
        self._cfg = build_config(load_workflow(self.workflow_path))
        self._last_cfg_mtime = self.workflow_path.stat().st_mtime
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._reload_task = asyncio.create_task(self._reload_loop())

    async def stop(self):
        self._running = False
        for t in [self._poll_task, self._reload_task]:
            if t: t.cancel()
        for entry in list(self._state.running.values()):
            if entry.task: entry.task.cancel()

    async def _reload_loop(self):
        while self._running:
            await asyncio.sleep(5)
            try:
                mtime = self.workflow_path.stat().st_mtime
                if mtime != self._last_cfg_mtime:
                    new_cfg = build_config(load_workflow(self.workflow_path))
                    v = validate_for_dispatch(new_cfg)
                    if v.ok:
                        self._cfg = new_cfg
                        self._last_cfg_mtime = mtime
                        log.info("workflow_reloaded")
                    else:
                        log.warning("workflow_reload_invalid", errors=v.errors)
            except Exception as e:
                log.warning("workflow_reload_error", error=str(e))

    async def _poll_loop(self):
        await self._startup_cleanup()
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                log.error("poll_error", error=str(e))
            interval = (self._cfg.polling.interval_ms if self._cfg else 30_000) / 1000
            await asyncio.sleep(interval)

    async def _startup_cleanup(self):
        cfg = self._cfg
        if not cfg: return
        try:
            client = LinearClient(cfg.tracker.api_key, cfg.tracker.endpoint)
            terminal = client.fetch_terminal_issues(cfg.tracker.project_slug, cfg.tracker.terminal_states)
            wm = WorkspaceManager(cfg.workspace.root)
            for issue in terminal:
                key = issue.identifier.lower().replace("/","-")
                try:
                    if cfg.hooks.before_remove:
                        ws = wm.prepare(key)
                        await wm.run_hook(cfg.hooks.before_remove, ws.path,
                                          cfg.hooks.timeout_ms, fatal=False)
                    wm.remove(key)
                except Exception as e:
                    log.warning("startup_cleanup_error", issue=issue.identifier, error=str(e))
        except Exception as e:
            log.warning("startup_cleanup_failed", error=str(e))

    async def _tick(self):
        cfg = self._cfg
        if not cfg: return
        await self._reconcile(cfg)
        issues = LinearClient(cfg.tracker.api_key, cfg.tracker.endpoint)            .fetch_active_issues(cfg.tracker.project_slug, cfg.tracker.active_states)
        issues.sort(key=lambda i: (i.priority or 999, i.created_at or datetime.min.replace(tzinfo=timezone.utc)))
        self.status_cb({"running": len(self._state.running),
                        "retry_queue": len(self._state.retry_attempts),
                        "issues": len(issues)})
        for issue in issues:
            if not self._eligible(issue, cfg): continue
            self._state.claimed.add(issue.id)
            attempt = None
            if issue.id in self._state.retry_attempts:
                attempt = self._state.retry_attempts[issue.id].attempt
                del self._state.retry_attempts[issue.id]
            task = asyncio.create_task(self._run_worker(issue, attempt, cfg))
            self._state.running[issue.id] = RunningEntry(
                issue=issue, attempt=attempt,
                started_at=datetime.now(timezone.utc),
                workspace_path="",
                task=task,
            )

    def _eligible(self, issue, cfg: ServiceConfig) -> bool:
        if issue.id in self._state.running: return False
        if issue.id in self._state.completed: return False
        if issue.id in self._state.claimed:
            if issue.id not in self._state.retry_attempts: return False
            entry = self._state.retry_attempts[issue.id]
            if int(time.time() * 1000) < entry.due_at_ms: return False
        slots = cfg.agent.max_concurrent_agents - len(self._state.running)
        if slots <= 0: return False
        state_lower = issue.state.lower()
        per_state = cfg.agent.max_concurrent_agents_by_state.get(state_lower)
        if per_state is not None:
            count = sum(1 for e in self._state.running.values()
                        if e.issue.state.lower() == state_lower)
            if count >= per_state: return False
        if state_lower == "todo":
            for blocker in issue.blocked_by:
                if blocker.state and blocker.state.lower() not in                    [s.lower() for s in cfg.tracker.terminal_states]:
                    return False
        return True

    async def _run_worker(self, issue, attempt, cfg: ServiceConfig):
        wm = WorkspaceManager(cfg.workspace.root)
        key = issue.identifier.lower().replace("/","-")
        try:
            ws = wm.prepare(key)
            self._state.running[issue.id].workspace_path = ws.path
            if ws.created_now and cfg.hooks.after_create:
                await wm.run_hook(cfg.hooks.after_create, ws.path, cfg.hooks.timeout_ms)
            if cfg.hooks.before_run:
                await wm.run_hook(cfg.hooks.before_run, ws.path, cfg.hooks.timeout_ms)
            ctx = {"issue": issue, "attempt": attempt}
            prompt = render_prompt(cfg.workflow_dir.read_text() if False else
                                   load_workflow(self.workflow_path).prompt_template, ctx)
            runner = AgentRunner(
                codex_command=cfg.codex.command,
                workspace_path=ws.path,
                approval_policy=cfg.codex.approval_policy,
                thread_sandbox=cfg.codex.thread_sandbox,
                turn_timeout_ms=cfg.codex.turn_timeout_ms,
                read_timeout_ms=cfg.codex.read_timeout_ms,
                stall_timeout_ms=cfg.codex.stall_timeout_ms,
                max_turns=cfg.agent.max_turns,
            )
            success = await runner.run(prompt, issue, attempt)
            if cfg.hooks.after_run:
                await wm.run_hook(cfg.hooks.after_run, ws.path, cfg.hooks.timeout_ms, fatal=False)
            if success:
                self._state.completed.add(issue.id)
                log.info("issue_succeeded", issue=issue.identifier)
            else:
                self._schedule_retry(issue, attempt, cfg, "agent_failed")
        except Exception as e:
            log.error("worker_error", issue=issue.identifier, error=str(e))
            self._schedule_retry(issue, attempt, cfg, str(e))
        finally:
            self._state.running.pop(issue.id, None)

    def _schedule_retry(self, issue, attempt, cfg: ServiceConfig, error: str):
        att = (attempt or 0) + 1
        delay = min(10_000 * (2 ** (att - 1)), cfg.agent.max_retry_backoff_ms)
        due = int(time.time() * 1000) + delay
        self._state.retry_attempts[issue.id] = RetryEntry(
            issue_id=issue.id, identifier=issue.identifier,
            attempt=att, due_at_ms=due, error=error
        )
        log.info("retry_scheduled", issue=issue.identifier, attempt=att, delay_ms=delay)

    async def _reconcile(self, cfg: ServiceConfig):
        now_ms = int(time.time() * 1000)
        stall_ms = cfg.codex.stall_timeout_ms
        for iid, entry in list(self._state.running.items()):
            elapsed = (datetime.now(timezone.utc) - entry.started_at).total_seconds() * 1000
            if elapsed > stall_ms * 2:
                log.warning("reconcile_stall", issue=entry.issue.identifier)
                if entry.task: entry.task.cancel()
                self._state.running.pop(iid, None)
                self._schedule_retry(entry.issue, entry.attempt, cfg, "stall_reconcile")
        if not self._state.running: return
        try:
            client = LinearClient(cfg.tracker.api_key, cfg.tracker.endpoint)
            fresh = client.fetch_issues_by_ids(list(self._state.running.keys()))
            fresh_map = {i.id: i for i in fresh}
            for iid, entry in list(self._state.running.items()):
                fi = fresh_map.get(iid)
                if fi and fi.state.lower() in [s.lower() for s in cfg.tracker.terminal_states]:
                    log.info("reconcile_cancel", issue=entry.issue.identifier, state=fi.state)
                    if entry.task: entry.task.cancel()
                    self._state.running.pop(iid, None)
                    self._state.completed.add(iid)
        except Exception as e:
            log.warning("reconcile_error", error=str(e))
