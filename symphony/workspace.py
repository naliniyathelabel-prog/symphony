"""Workspace Manager per SPEC.md §9."""
from __future__ import annotations
import asyncio, os, re, shutil, subprocess
from pathlib import Path
from typing import Optional
from .models import Workspace
from .logger import get

log = get("symphony.workspace")
_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")

class WorkspaceError(Exception): pass
class WorkspaceEscapeError(WorkspaceError): pass
class WorkspaceKeyError(WorkspaceError): pass

def _sanitize_key(key: str) -> str:
    if not _KEY_RE.match(key):
        raise WorkspaceKeyError(f"Invalid workspace key: {key!r} — must match [A-Za-z0-9._-]+")
    return key

def _assert_inside(path: Path, root: Path):
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise WorkspaceEscapeError(f"Path {path} escapes workspace root {root}")

class WorkspaceManager:
    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace_path(self, key: str) -> Path:
        _sanitize_key(key)
        p = self.root / key
        _assert_inside(p, self.root)
        return p

    def prepare(self, key: str) -> Workspace:
        p = self.workspace_path(key)
        created = not p.exists()
        p.mkdir(parents=True, exist_ok=True)
        return Workspace(path=str(p), workspace_key=key, created_now=created)

    def remove(self, key: str):
        p = self.workspace_path(key)
        if p.exists():
            shutil.rmtree(p)
            log.info("workspace removed", key=key)

    async def run_hook(self, script: str, workspace_path: str, timeout_ms: int = 60_000,
                       fatal: bool = True) -> Optional[str]:
        if not script: return None
        p = Path(workspace_path).resolve()
        _assert_inside(p, self.root)
        try:
            proc = await asyncio.create_subprocess_shell(
                f"bash -lc {repr(script)}",
                cwd=str(p),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "WORKSPACE_PATH": str(p)},
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms/1000)
            except asyncio.TimeoutError:
                proc.kill()
                msg = f"Hook timed out after {timeout_ms}ms"
                if fatal: raise WorkspaceError(msg)
                log.warning(msg)
                return None
            out = stdout.decode(errors="replace")
            if proc.returncode != 0:
                msg = f"Hook exited {proc.returncode}: {out[:500]}"
                if fatal: raise WorkspaceError(msg)
                log.warning("hook_failed_ignored", returncode=proc.returncode)
                return out
            return out
        except WorkspaceError:
            raise
        except Exception as exc:
            if fatal: raise WorkspaceError(str(exc)) from exc
            log.warning("hook_error_ignored", error=str(exc))
            return None
