---
tracker:
  kind: linear
  project_slug: "your-project-slug"
  api_key: $LINEAR_API_KEY

workspace:
  root: ~/symphony-workspaces

hooks:
  after_create: |
    git clone --depth 1 git@github.com:your-org/your-repo.git .
  before_run: |
    git fetch origin && git reset --hard origin/main

polling:
  interval_ms: 30000

agent:
  max_concurrent_agents: 5
  max_turns: 20

codex:
  command: codex app-server
  approval_policy: never
  thread_sandbox: workspace-write
---

You are working on {{ issue.identifier }}: {{ issue.title }}.

**Description**: {{ issue.description }}

{% if attempt %}Retry attempt: {{ attempt }}{% endif %}

Complete this issue and open a pull request when done.
