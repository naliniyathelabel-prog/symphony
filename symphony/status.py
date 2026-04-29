"""Terminal status surface per SPEC.md §3.1.7."""
from __future__ import annotations
import sys, time
from typing import Any, Dict, Optional

RESET='\033[0m'; BOLD='\033[1m'; GREEN='\033[32m'; CYAN='\033[36m'; YELLOW='\033[33m'

class TerminalStatus:
    def __init__(self, quiet: bool=False, min_interval_s: float=2.0):
        self.quiet = quiet
        self.min_interval = min_interval_s
        self._last_render = 0.0
        self._state: Dict[str, Any] = {}
        self._start = time.time()

    def update(self, state: Dict[str, Any]):
        self._state.update(state)
        now = time.time()
        if not self.quiet and now - self._last_render >= self.min_interval:
            self._render()
            self._last_render = now

    def _render(self):
        s = self._state
        elapsed = int(time.time() - self._start)
        h, rem = divmod(elapsed, 3600); m, sec = divmod(rem, 60)
        uptime = f"{h:02d}:{m:02d}:{sec:02d}"
        running = s.get("running", 0)
        retry = s.get("retry_queue", 0)
        issues = s.get("issues", 0)
        line = (f"\r{BOLD}Symphony{RESET} {uptime} | "
                f"{GREEN}running:{running}{RESET} | "
                f"{YELLOW}retry:{retry}{RESET} | "
                f"{CYAN}issues:{issues}{RESET}   ")
        sys.stderr.write(line)
        sys.stderr.flush()
