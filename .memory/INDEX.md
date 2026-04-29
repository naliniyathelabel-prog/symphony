# Agent Memory Index
> Long-term memory for Symphony agent. Git is the persistence layer.
> Atomic nodes in `nodes/`. Each node = one concept. Edges in `graph.json`.

## How to use (for future-me)
1. On TURN START: `git clone` → read `INDEX.md` + relevant nodes
2. On TURN END: write findings → update graph → `git commit && git push`
3. Search: `grep -r "<keyword>" .memory/nodes/`
4. Never delete nodes — append or create new ones

## Node Index
| ID | Topic | Tags | Updated |
|----|-------|------|---------|
| 001 | agent-memory-protocol | architecture,memory,git | 2026-04-29 |
| 002 | symphony-spec-status | symphony,spec,implementation | 2026-04-29 |
| 003 | sandbox-constraints | sandbox,limits,patterns | 2026-04-29 |
| 004 | github-token-scope | auth,github,token | 2026-04-29 |

## Graph
See `graph.json` for edges between nodes.

## Queue
See `queue/pending.md` for outstanding tasks.
