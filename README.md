# Symphony

Python implementation of the [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md).

## Install
```bash
pip install -e .
export LINEAR_API_KEY="lin_api_xxxx"
python main.py WORKFLOW.md --i-understand-that-this-will-be-running-without-the-usual-guardrails
```

## Files
| File | SPEC | Purpose |
|------|------|---------|
| symphony/models.py | §4 | Domain models |
| symphony/logger.py | §3.1.8 | Structured JSON logging |
| symphony/config.py | §5-6 | Workflow loader + validation |
| symphony/tracker.py | §3.1.3 | Linear GraphQL client |
| symphony/workspace.py | §9 | Workspace manager + hooks |
| symphony/agent.py | §10 | Agent runner (Codex stdio) |
| symphony/orchestrator.py | §7-8 | Poll loop + dispatch + retry |
| symphony/status.py | §3.1.7 | Terminal status surface |
| main.py | — | CLI entry point |
