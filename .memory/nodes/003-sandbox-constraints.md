---
id: "003"
title: "Sandbox Constraints & Patterns"
tags: [sandbox, limits, patterns, file-sharing]
created: "2026-04-29"
updated: "2026-04-29"
---

# Sandbox Constraints & Patterns

## Known Constraints
- Files written by execute_code land at /root/ not /home/user/
- share_files tool looks in /home/user/ — must copy: shutil.copy("/root/x", "/home/user/x")
- No localStorage/sessionStorage (sandboxed iframe)
- No OAuth — only static tokens
- Sandbox wiped between conversations
- Max 3 tool calls per response before must reply
- Internet access: YES (http/https outbound works)
- GitHub API: reachable ✅
- Google APIs: reachable ✅ (but needs credentials)

## Verified Working Patterns
- git clone with token in URL: https://<token>@github.com/user/repo.git ✅
- GitHub API via urllib (no extra libs needed) ✅
- zip + shutil.copy + share_files ✅

## Connectors Note
Perplexity Computer connectors (GitHub, GDrive, GSheets) are for Computer product only.
Standard assistant chat does NOT get connector access via list_files.
