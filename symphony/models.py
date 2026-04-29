"""Symphony domain models per SPEC.md §4."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

@dataclass
class BlockerRef:
    id: Optional[str] = None
    identifier: Optional[str] = None
    state: Optional[str] = None

@dataclass
class Issue:
    id: str
    identifier: str
    title: str
    state: str
    description: Optional[str] = None
    priority: Optional[int] = None
    branch_name: Optional[str] = None
    url: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    blocked_by: List[BlockerRef] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class RunStatus(str, Enum):
    PREPARING_WORKSPACE  = "PreparingWorkspace"
    BUILDING_PROMPT      = "BuildingPrompt"
    LAUNCHING_AGENT      = "LaunchingAgentProcess"
    INITIALIZING_SESSION = "InitializingSession"
    STREAMING_TURN       = "StreamingTurn"
    FINISHING            = "Finishing"
    SUCCEEDED            = "Succeeded"
    FAILED               = "Failed"
    TIMED_OUT            = "TimedOut"
    STALLED              = "Stalled"
    CANCELED             = "CanceledByReconciliation"

@dataclass
class Workspace:
    path: str
    workspace_key: str
    created_now: bool = False

@dataclass
class LiveSession:
    session_id: str
    thread_id: str
    turn_id: str
    codex_app_server_pid: Optional[str] = None
    last_codex_event: Optional[str] = None
    last_codex_timestamp: Optional[datetime] = None
    last_codex_message: Any = None
    codex_input_tokens: int = 0
    codex_output_tokens: int = 0
    codex_total_tokens: int = 0
    turn_count: int = 0

@dataclass
class RetryEntry:
    issue_id: str
    identifier: str
    attempt: int
    due_at_ms: int
    error: Optional[str] = None
    timer_handle: Optional[asyncio.TimerHandle] = None

@dataclass
class RunningEntry:
    issue: Issue
    attempt: Optional[int]
    started_at: datetime
    workspace_path: str
    live_session: Optional[LiveSession] = None
    task: Optional[asyncio.Task] = None

@dataclass
class CodexTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    runtime_seconds: float = 0.0

@dataclass
class OrchestratorState:
    poll_interval_ms: int = 30_000
    max_concurrent_agents: int = 10
    running: Dict[str, RunningEntry] = field(default_factory=dict)
    claimed: Set[str] = field(default_factory=set)
    retry_attempts: Dict[str, RetryEntry] = field(default_factory=dict)
    completed: Set[str] = field(default_factory=set)
    codex_totals: CodexTotals = field(default_factory=CodexTotals)
    codex_rate_limits: Dict[str, Any] = field(default_factory=dict)
