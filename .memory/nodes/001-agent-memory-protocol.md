---
id: "001"
title: "Agent Memory Protocol"
tags: [architecture, memory, git, persistent]
created: "2026-04-29"
updated: "2026-04-29"
---

# Agent Memory Protocol

## Core Insight
Git = long-term memory. Conversation = short-term (context window). Sandbox = disposable compute.

## The Protocol (RFC 2119 draft)

### Definitions
- TURN: one user↔agent exchange
- REPO: the dedicated GitHub repo as single source of truth
- NODE: one atomic markdown file in `.memory/nodes/`
- CONTEXT WINDOW: the agent's working short-term memory (limited)

### Rules
- Agent MUST clone REPO at the start of every TURN
- Agent MUST commit and push before responding to user
- Agent MUST save new findings as atomic NODE files
- Agent SHOULD update INDEX.md after adding nodes
- Agent MUST work slice-by-slice (never attempt full task in one tool-call chain)
- Agent MUST NOT rely on conversation history alone for facts — git is authoritative
- Agent SHOULD read INDEX.md first to orient itself in a new session
- Agent MAY use `grep` on nodes/ for keyword retrieval
- Agent SHOULD write queue/pending.md for deferred work

## What this solves
- Context window wipe between sessions → git persists
- Sandbox reset → clone restores everything
- No zip/upload/download → token + repo = state
- Tool call limits → slice-by-slice with push between turns

## Gaps identified (suggestions)
1. No semantic search — nodes are grep-only (future: embed + store vectors in nodes)
2. No conflict resolution — single-agent assumed (future: branch-per-agent + merge)
3. No token refresh strategy — PAT can expire (future: store refresh logic in AGENTS.md)
4. No memory pruning — unbounded growth (future: archive/ subdir + relevance score in frontmatter)
5. No structured task DAG — queue is flat (future: queue/pending.json with deps)
