"""Agent Runner per SPEC.md §10."""
from __future__ import annotations
import asyncio, json, os, subprocess, uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, Optional
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError
from .models import Issue, LiveSession, RunStatus
from .logger import get

log = get("symphony.agent")
MAX_LINE_BYTES = 10 * 1024 * 1024

def render_prompt(template_str: str, context: Dict[str, Any]) -> str:
    try:
        env = Environment(undefined=StrictUndefined, autoescape=False)
        tmpl = env.from_string(template_str)
    except TemplateSyntaxError as e:
        raise ValueError(f"template_parse_error: {e}") from e
    try:
        return tmpl.render(**context)
    except UndefinedError as e:
        raise ValueError(f"template_render_error: {e}") from e

class AgentRunner:
    def __init__(self, codex_command: str, workspace_path: str,
                 approval_policy: Optional[str]=None,
                 thread_sandbox: Optional[str]=None,
                 turn_timeout_ms: int=3_600_000,
                 read_timeout_ms: int=5_000,
                 stall_timeout_ms: int=300_000,
                 max_turns: int=20,
                 on_event: Optional[Callable]=None):
        self.command = codex_command
        self.workspace_path = workspace_path
        self.approval_policy = approval_policy
        self.thread_sandbox = thread_sandbox
        self.turn_timeout_ms = turn_timeout_ms
        self.read_timeout_ms = read_timeout_ms
        self.stall_timeout_ms = stall_timeout_ms
        self.max_turns = max_turns
        self.on_event = on_event or (lambda e: None)

    async def run(self, prompt: str, issue: Issue, attempt: Optional[int]=None) -> bool:
        session = LiveSession(
            session_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4()),
            turn_id=str(uuid.uuid4()),
        )
        cmd_parts = self.command.split()
        env = {**os.environ, "WORKSPACE_PATH": self.workspace_path}
        if self.approval_policy: env["CODEX_APPROVAL_POLICY"] = self.approval_policy
        if self.thread_sandbox: env["CODEX_THREAD_SANDBOX"] = self.thread_sandbox
        await self._emit("session_started", {"session_id": session.session_id,
                                              "issue_id": issue.id, "attempt": attempt})
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                cwd=self.workspace_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except Exception as e:
            await self._emit("agent_error", {"error": str(e)})
            return False

        session.codex_app_server_pid = str(proc.pid)
        init_msg = json.dumps({"type":"session_init","thread_id":session.thread_id,
                               "session_id":session.session_id}) + "\n"
        proc.stdin.write(init_msg.encode())
        await proc.stdin.drain()

        for turn_num in range(1, self.max_turns + 1):
            session.turn_id = str(uuid.uuid4())
            session.turn_count = turn_num
            turn_msg = json.dumps({"type":"turn","turn_id":session.turn_id,
                                   "content":prompt if turn_num==1 else "__continue__"}) + "\n"
            proc.stdin.write(turn_msg.encode())
            await proc.stdin.drain()
            await self._emit("turn_started", {"turn": turn_num, "turn_id": session.turn_id})
            done = await self._stream_turn(proc, session, turn_num)
            if done == "success":
                await self._emit("session_completed", {"session_id": session.session_id,
                                                        "turns": turn_num})
                proc.stdin.close()
                return True
            elif done == "continue":
                continue
            else:
                proc.kill()
                return False

        proc.kill()
        await self._emit("max_turns_reached", {"max_turns": self.max_turns})
        return False

    async def _stream_turn(self, proc, session: LiveSession, turn_num: int) -> str:
        last_event_time = asyncio.get_event_loop().time()
        while True:
            try:
                line = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=self.read_timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                if asyncio.get_event_loop().time() - last_event_time > self.stall_timeout_ms/1000:
                    await self._emit("stall_detected", {"turn": turn_num})
                    return "stall"
                continue
            if not line:
                return "eof"
            if len(line) > MAX_LINE_BYTES:
                await self._emit("line_too_large", {"bytes": len(line)})
                continue
            try:
                event = json.loads(line.decode(errors="replace"))
            except json.JSONDecodeError:
                continue
            last_event_time = asyncio.get_event_loop().time()
            session.last_codex_event = event.get("type")
            session.last_codex_timestamp = datetime.now(timezone.utc)
            session.last_codex_message = event
            await self._emit("codex_event", {"event": event, "turn": turn_num})
            t = event.get("type","")
            if t == "turn_complete":
                await self._emit("turn_completed", {"turn": turn_num})
                if event.get("done"): return "success"
                return "continue"
            elif t == "approval_request":
                await self._emit("approval_auto_approved", {"turn": turn_num})
                ack = json.dumps({"type":"approval_response","approved":True,
                                  "id":event.get("id")}) + "\n"
                proc.stdin.write(ack.encode())
                await proc.stdin.drain()
            elif t == "user_input_required":
                await self._emit("user_input_required", {"turn": turn_num})
                return "failed"
            elif t == "unsupported_tool_call":
                await self._emit("unsupported_tool_call", {"tool": event.get("tool"), "turn": turn_num})
            elif t == "usage":
                session.codex_input_tokens += event.get("input_tokens",0)
                session.codex_output_tokens += event.get("output_tokens",0)
                session.codex_total_tokens += event.get("total_tokens",0)
            elif t == "linear_graphql":
                result = {"error": "linear_graphql tool not configured"}
                ack = json.dumps({"type":"tool_result","id":event.get("id"),"result":result}) + "\n"
                proc.stdin.write(ack.encode())
                await proc.stdin.drain()

    async def _emit(self, event_type: str, data: Dict):
        payload = {"type": event_type, "ts": datetime.now(timezone.utc).isoformat(), **data}
        log.debug("agent_event", **payload)
        try:
            self.on_event(payload)
        except Exception:
            pass
