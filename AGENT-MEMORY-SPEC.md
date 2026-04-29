# AGENT-MEMORY-SPEC: Git-Backed Persistent Memory for Stateless AI Agents

**Status:** Draft  
**Version:** 0.1.0  
**Date:** 2026-04-29  
**Repo:** naliniyathelabel-prog/symphony  

---

## Abstract

This document specifies a protocol for AI agents operating under constrained
context windows and ephemeral compute environments to maintain persistent,
structured, auditable long-term memory using Git as the storage substrate.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in RFC 2119.

---

## 1. Motivation

An AI agent operating in a stateless sandbox faces three fundamental constraints:

1. **Context window limit** — working memory is finite and wiped between sessions
2. **Sandbox reset** — filesystem state does not persist across conversations
3. **Tool call limit** — a single turn cannot accomplish unbounded work

Without a persistence strategy, the agent rediscovers the same facts, repeats
the same mistakes, and cannot build compounding knowledge over time.

This specification defines a protocol that treats a Git repository as the
agent's **external long-term memory** — persistent, versioned, searchable,
and human-auditable.

---

## 2. Definitions

| Term | Definition |
|------|-----------|
| **TURN** | One complete user↔agent exchange |
| **SESSION** | A single conversation (contains one or more TURNs) |
| **REPO** | The dedicated Git repository serving as long-term memory |
| **SANDBOX** | The ephemeral compute environment (wiped between sessions) |
| **NODE** | One atomic Markdown file under `.memory/nodes/` |
| **INDEX** | The file `.memory/INDEX.md` — the master node directory |
| **GRAPH** | The file `.memory/graph.json` — edges between nodes |
| **QUEUE** | The file `.memory/queue/pending.md` — deferred work |
| **SLICE** | A discrete, independently committable unit of work |

---

## 3. Memory Architecture

```
REPO (.memory/)
├── INDEX.md          ← master index; agent reads this first every session
├── graph.json        ← knowledge graph edges (JSON)
├── nodes/            ← atomic knowledge nodes (one concept per file)
│   ├── 001-*.md
│   ├── 002-*.md
│   └── ...
├── queue/
│   └── pending.md    ← deferred tasks
└── log/              ← append-only session logs (OPTIONAL)
```

### Memory Layers

```
┌─────────────────────────────────────────┐
│  LONG-TERM MEMORY  (.memory/ in REPO)   │  ← persistent, git-versioned
│  Survives: session end, sandbox reset   │
├─────────────────────────────────────────┤
│  SHORT-TERM MEMORY  (conversation)      │  ← context window, fast
│  Survives: within session only          │
├─────────────────────────────────────────┤
│  WORKING MEMORY  (sandbox /root/)       │  ← ephemeral compute
│  Survives: within turn only             │
└─────────────────────────────────────────┘
```

---

## 4. Turn Protocol

### 4.1 TURN START Sequence

An agent MUST execute the following steps at the start of every TURN,
before performing any other work:

1. The agent MUST clone REPO to the local sandbox:
   ```
   git clone https://<token>@github.com/<owner>/<repo>.git
   ```

2. The agent MUST read `.memory/INDEX.md` to orient itself.

3. The agent SHOULD read any NODE files referenced by the user's query
   before formulating a response.

4. The agent MAY search nodes using keyword grep:
   ```
   grep -r "<keyword>" .memory/nodes/
   ```

### 4.2 TURN END Sequence

An agent MUST execute the following steps before returning any response
to the user:

1. The agent MUST write all new findings, decisions, and learnings as
   NODE files (see Section 5).

2. The agent MUST update `.memory/INDEX.md` to reflect new nodes.

3. The agent MUST update `.memory/graph.json` if new edges exist.

4. The agent MUST stage, commit, and push all changes:
   ```
   git add .memory/
   git commit -m "<type>(<scope>): <description>"
   git push
   ```

5. The agent MUST NOT return a response to the user if the push fails,
   unless the failure is a known transient error and a retry is in progress.

### 4.3 Slice Discipline

1. The agent MUST NOT attempt to complete an entire task in a single TURN.

2. The agent MUST decompose work into SLICEs — each SLICE MUST be:
   - Independently committable
   - Verifiable in isolation
   - Documented in a NODE or QUEUE entry

3. The agent SHOULD commit one SLICE per TURN when tool-call limits apply.

---

## 5. Node Specification

### 5.1 Node File Format

Every NODE MUST be an atomic Markdown file with YAML frontmatter:

```markdown
---
id: "<zero-padded-integer>"
title: "<human-readable title>"
tags: [tag1, tag2, tag3]
created: "<ISO-8601 date>"
updated: "<ISO-8601 date>"
---

# <title>

<content>
```

### 5.2 Node Naming

Node filenames MUST follow the pattern:
```
<id>-<slug>.md
```
Where `<slug>` is lowercase, hyphen-separated, and derived from the title.

Example: `001-agent-memory-protocol.md`

### 5.3 Node Atomicity

1. Each NODE MUST represent exactly one concept, decision, or finding.

2. A NODE MUST NOT be deleted. If a finding is superseded, the agent MUST
   create a new NODE and reference the old one via `supersedes: "<id>"` in
   frontmatter.

3. A NODE SHOULD be small enough to be read within one context window load.
   If a node exceeds ~500 lines, the agent SHOULD split it.

### 5.4 Node ID Allocation

1. Node IDs MUST be sequentially allocated integers, zero-padded to 3 digits.

2. The agent MUST read the current highest ID from INDEX.md before creating
   a new NODE, to avoid collisions in concurrent scenarios.

---

## 6. Index Specification

### 6.1 INDEX.md Format

The INDEX MUST contain:

1. A table of all nodes with columns: `ID | Topic | Tags | Updated`
2. A "How to use" section for agent orientation
3. A reference to `graph.json` and `queue/pending.md`

### 6.2 Index Updates

The agent MUST update INDEX.md in the same commit as any new NODE creation.

---

## 7. Graph Specification

`graph.json` MUST conform to this schema:

```json
{
  "nodes": ["001", "002"],
  "edges": [
    {
      "from": "001",
      "to": "002",
      "rel": "depends_on | uses | instance_of | related | supersedes",
      "label": "<human-readable description>"
    }
  ]
}
```

Allowed `rel` values:
- `depends_on` — node A requires understanding of node B
- `uses` — node A references or applies node B
- `instance_of` — node A is a specific case of node B
- `related` — loose topical relationship
- `supersedes` — node A replaces node B

---

## 8. Queue Specification

`queue/pending.md` MUST use this format:

```markdown
## <Priority Level>
- [ ] <task description> [node:<id>]
- [x] <completed task> [node:<id>]
```

Priority levels: `High Priority`, `Medium Priority`, `Low Priority`.

The agent MUST mark tasks complete (`[x]`) in the same commit that
produces the work, not in a separate cleanup commit.

---

## 9. Commit Message Convention

All commits to `.memory/` MUST follow Conventional Commits format:

```
<type>(<scope>): <description>
```

| Type | When to use |
|------|-------------|
| `feat` | New node or graph edge |
| `fix` | Correction to an existing node |
| `chore` | Index/queue housekeeping |
| `docs` | README or spec updates |
| `archive` | Moving nodes to archive/ |

---

## 10. Security Considerations

1. TOKEN values MUST NOT be stored in any NODE file.

2. NODE files referencing tokens MUST use a placeholder:
   `<token>` or `<redacted>`.

3. The REPO MAY be private. If public, the agent MUST ensure no secrets,
   credentials, or PII appear in any NODE.

---

## 11. Known Limitations & Future Work

| Limitation | Severity | Proposed Resolution |
|------------|----------|-------------------|
| Grep-only search | Medium | Embed nodes; store vectors in frontmatter |
| Single-agent assumed | Medium | Branch-per-agent + merge strategy |
| Token expiry = silent failure | High | Health-check node + refresh doc |
| Unbounded repo growth | Low | `archive/` dir + relevance score in frontmatter |
| Flat task queue | Low | `queue/pending.json` with DAG dependency edges |

---

## 12. Reference Implementation

```
naliniyathelabel-prog/symphony/.memory/
```

This repository serves as the reference implementation of this specification
as of version 0.1.0.

---

*End of AGENT-MEMORY-SPEC v0.1.0*
