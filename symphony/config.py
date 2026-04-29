"""Workflow Loader + Config Layer per SPEC.md §5-6."""
from __future__ import annotations
import os, re, tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from .logger import get

log = get("symphony.config")

class WorkflowError(Exception): kind = "workflow_error"
class MissingWorkflowFile(WorkflowError): kind = "missing_workflow_file"
class WorkflowParseError(WorkflowError): kind = "workflow_parse_error"
class WorkflowFrontMatterNotAMap(WorkflowError): kind = "workflow_front_matter_not_a_map"
class ConfigValidationError(WorkflowError): kind = "config_validation_error"

@dataclass
class WorkflowDefinition:
    config: Dict[str, Any]
    prompt_template: str
    source_path: Path

@dataclass
class TrackerConfig:
    kind: str = ""
    endpoint: str = "https://api.linear.app/graphql"
    api_key: str = ""
    project_slug: str = ""
    active_states: List[str] = field(default_factory=lambda: ["Todo","In Progress"])
    terminal_states: List[str] = field(default_factory=lambda: ["Closed","Cancelled","Canceled","Duplicate","Done"])

@dataclass
class PollingConfig:
    interval_ms: int = 30_000

@dataclass
class WorkspaceConfig:
    root: str = ""

@dataclass
class HooksConfig:
    after_create: Optional[str] = None
    before_run: Optional[str] = None
    after_run: Optional[str] = None
    before_remove: Optional[str] = None
    timeout_ms: int = 60_000

@dataclass
class AgentConfig:
    max_concurrent_agents: int = 10
    max_turns: int = 20
    max_retry_backoff_ms: int = 300_000
    max_concurrent_agents_by_state: Dict[str, int] = field(default_factory=dict)

@dataclass
class CodexConfig:
    command: str = "codex app-server"
    approval_policy: Optional[str] = None
    thread_sandbox: Optional[str] = None
    turn_sandbox_policy: Optional[str] = None
    turn_timeout_ms: int = 3_600_000
    read_timeout_ms: int = 5_000
    stall_timeout_ms: int = 300_000

@dataclass
class ServiceConfig:
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    workflow_dir: Path = field(default_factory=Path.cwd)

def load_workflow(path: Path) -> WorkflowDefinition:
    if not path.exists():
        raise MissingWorkflowFile(f"Workflow file not found: {path}")
    text = path.read_text(encoding="utf-8")
    config: Dict[str, Any] = {}
    prompt_body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                parsed = yaml.safe_load(parts[1])
            except yaml.YAMLError as exc:
                raise WorkflowParseError(f"YAML front matter parse error: {exc}") from exc
            if parsed is not None and not isinstance(parsed, dict):
                raise WorkflowFrontMatterNotAMap("Front matter must be a map")
            config = parsed or {}
            prompt_body = parts[2]
    return WorkflowDefinition(config=config, prompt_template=prompt_body.strip(), source_path=path)

def _resolve_env(value):
    if not isinstance(value, str): return str(value) if value is not None else ""
    if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", value.strip()):
        return os.environ.get(value.strip()[1:], "")
    return value

def _expand_path(value, workflow_dir):
    if not value: return ""
    if re.match(r"^\$[A-Za-z_]", value): value = _resolve_env(value)
    p = Path(os.path.expanduser(value))
    if not p.is_absolute(): p = workflow_dir / p
    return str(p.resolve())

def build_config(wf: WorkflowDefinition) -> ServiceConfig:
    raw, wf_dir = wf.config, wf.source_path.parent
    tr_raw = raw.get("tracker", {}) or {}
    tr = TrackerConfig(
        kind=str(tr_raw.get("kind","")).strip(),
        endpoint=str(tr_raw.get("endpoint","https://api.linear.app/graphql") or "https://api.linear.app/graphql"),
        api_key=_resolve_env(tr_raw.get("api_key","$LINEAR_API_KEY")),
        project_slug=str(tr_raw.get("project_slug","") or ""),
        active_states=[str(s) for s in (tr_raw.get("active_states") or ["Todo","In Progress"])],
        terminal_states=[str(s) for s in (tr_raw.get("terminal_states") or ["Closed","Cancelled","Canceled","Duplicate","Done"])],
    )
    po_raw = raw.get("polling", {}) or {}
    ws_raw = raw.get("workspace", {}) or {}
    hk_raw = raw.get("hooks", {}) or {}
    ag_raw = raw.get("agent", {}) or {}
    cx_raw = raw.get("codex", {}) or {}
    ws_root = ws_raw.get("root","")
    return ServiceConfig(
        tracker=tr,
        polling=PollingConfig(interval_ms=int(po_raw.get("interval_ms",30_000))),
        workspace=WorkspaceConfig(root=_expand_path(ws_root, wf_dir) if ws_root else str(Path(tempfile.gettempdir())/"symphony_workspaces")),
        hooks=HooksConfig(
            after_create=hk_raw.get("after_create") or None,
            before_run=hk_raw.get("before_run") or None,
            after_run=hk_raw.get("after_run") or None,
            before_remove=hk_raw.get("before_remove") or None,
            timeout_ms=int(hk_raw.get("timeout_ms",60_000)),
        ),
        agent=AgentConfig(
            max_concurrent_agents=int(ag_raw.get("max_concurrent_agents",10)),
            max_turns=int(ag_raw.get("max_turns",20)),
            max_retry_backoff_ms=int(ag_raw.get("max_retry_backoff_ms",300_000)),
            max_concurrent_agents_by_state={
                str(k).lower(): int(v) for k,v in
                (ag_raw.get("max_concurrent_agents_by_state") or {}).items() if v and int(v)>0
            },
        ),
        codex=CodexConfig(
            command=str(cx_raw.get("command","codex app-server") or "codex app-server"),
            approval_policy=cx_raw.get("approval_policy") or None,
            thread_sandbox=cx_raw.get("thread_sandbox") or None,
            turn_sandbox_policy=cx_raw.get("turn_sandbox_policy") or None,
            turn_timeout_ms=int(cx_raw.get("turn_timeout_ms",3_600_000)),
            read_timeout_ms=int(cx_raw.get("read_timeout_ms",5_000)),
            stall_timeout_ms=int(cx_raw.get("stall_timeout_ms",300_000)),
        ),
        workflow_dir=wf_dir,
    )

class ValidationResult:
    def __init__(self): self.ok=True; self.errors=[]
    def fail(self, msg): self.ok=False; self.errors.append(msg)

def validate_for_dispatch(cfg: ServiceConfig) -> ValidationResult:
    v = ValidationResult()
    if not cfg.tracker.kind: v.fail("tracker.kind is missing")
    elif cfg.tracker.kind != "linear": v.fail(f"tracker.kind '{cfg.tracker.kind}' unsupported")
    if not cfg.tracker.api_key: v.fail("tracker.api_key is missing after $VAR resolution")
    if cfg.tracker.kind=="linear" and not cfg.tracker.project_slug: v.fail("tracker.project_slug required")
    if not cfg.codex.command: v.fail("codex.command is missing")
    return v
