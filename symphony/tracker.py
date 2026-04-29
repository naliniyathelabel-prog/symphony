"""Linear GraphQL tracker client per SPEC.md §3.1.3."""
from __future__ import annotations
import json, urllib.request, urllib.error
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from .models import BlockerRef, Issue
from .logger import get

log = get("symphony.tracker")

GQL_ISSUES = """
query Issues($filter: IssueFilter, $after: String) {
  issues(filter: $filter, first: 50, after: $after, orderBy: updatedAt) {
    nodes {
      id identifier title description state { name }
      priority branchName url
      labels { nodes { name } }
      relations(filter: {type: {eq: "blocks"}}) {
        nodes { relatedIssue { id identifier state { name } } }
      }
      createdAt updatedAt
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

class LinearClient:
    def __init__(self, api_key: str, endpoint: str = "https://api.linear.app/graphql"):
        self.api_key = api_key
        self.endpoint = endpoint

    def _gql(self, query: str, variables: Dict[str, Any] = None) -> Dict:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "symphony/0.1",
            }
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            return data.get("data", {})
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e

    def _norm(self, node: Dict) -> Issue:
        state = (node.get("state") or {}).get("name","")
        labels = [l["name"].lower() for l in (node.get("labels") or {}).get("nodes",[])]
        blockers = []
        for rel in (node.get("relations") or {}).get("nodes",[]):
            ri = rel.get("relatedIssue") or {}
            if ri:
                blockers.append(BlockerRef(
                    id=ri.get("id"),
                    identifier=ri.get("identifier"),
                    state=(ri.get("state") or {}).get("name")
                ))
        def _dt(s): 
            try: return datetime.fromisoformat(s.replace("Z","+00:00")) if s else None
            except: return None
        return Issue(
            id=node["id"], identifier=node["identifier"], title=node["title"],
            state=state, description=node.get("description"),
            priority=node.get("priority"), branch_name=node.get("branchName"),
            url=node.get("url"), labels=labels, blocked_by=blockers,
            created_at=_dt(node.get("createdAt")), updated_at=_dt(node.get("updatedAt")),
        )

    def fetch_active_issues(self, project_slug: str, active_states: List[str]) -> List[Issue]:
        issues, cursor = [], None
        while True:
            variables = {
                "filter": {"project": {"slugId": {"eq": project_slug}},
                           "state": {"name": {"in": active_states}}},
                "after": cursor
            }
            data = self._gql(GQL_ISSUES, variables)
            nodes = data.get("issues",{}).get("nodes",[])
            pi = data.get("issues",{}).get("pageInfo",{})
            issues.extend(self._norm(n) for n in nodes)
            if not pi.get("hasNextPage"): break
            cursor = pi.get("endCursor")
        return issues

    def fetch_issues_by_ids(self, ids: List[str]) -> List[Issue]:
        if not ids: return []
        q = "query($filter:IssueFilter){issues(filter:$filter,first:100){nodes{id identifier title state{name}}}}"
        data = self._gql(q, {"filter": {"id": {"in": ids}}})
        return [self._norm(n) for n in data.get("issues",{}).get("nodes",[])]

    def fetch_terminal_issues(self, project_slug: str, terminal_states: List[str]) -> List[Issue]:
        variables = {
            "filter": {"project": {"slugId": {"eq": project_slug}},
                       "state": {"name": {"in": terminal_states}}}
        }
        data = self._gql(GQL_ISSUES, variables)
        return [self._norm(n) for n in data.get("issues",{}).get("nodes",[])]

    def execute_graphql(self, operation: str, variables: Dict = None) -> Dict:
        import re
        ops = re.findall(r"\b(query|mutation|subscription)\b", operation, re.IGNORECASE)
        if len(ops) > 1:
            raise ValueError("linear_graphql tool: only one operation per call allowed")
        return self._gql(operation, variables)
