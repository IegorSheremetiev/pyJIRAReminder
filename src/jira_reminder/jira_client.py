# src/jira_reminder/jira_client.py
from __future__ import annotations

from typing import List, Dict

from urllib.parse import quote_plus

import requests

from .logging_setup import log


class JiraClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        projects: list[str],
        issue_types: list[str],
        start_date_field: str | None = None,
        done_jql_override: str | None = None,
    ):
        self.base = base_url.rstrip("/")
        self.email = email
        self.token = api_token
        self.projects = projects or []
        self.issue_types = issue_types or ["Sub-task - HW"]
        self.start_date_field = start_date_field or "customfield_10015"
        self.done_override = (done_jql_override or "").strip()

        self.session = requests.Session()
        self.session.auth = (self.email, self.token)
        self.session.headers.update({"Accept": "application/json"})
        log.debug(f"The JiraClient is intialized for user {self.email}")

    def _cf_key(self) -> str | None:
        if not self.start_date_field:
            return None
        s = self.start_date_field.strip()
        if s.startswith("cf[") and s.endswith("]"):
            return s
        if s.startswith("customfield_"):
            num = s.split("_", 1)[1]
            return f"cf[{num}]"
        return s

    def _base_constraints(self, assignee_email: str) -> str:
        proj = ", ".join(self.projects)
        issuet = ", ".join([f'"{t}"' for t in self.issue_types]) if self.issue_types else ""
        parts = [
            f'project in ({proj})' if self.projects else "",
            f'assignee = "{assignee_email}"',
            f'issuetype in ({issuet})' if issuet else "",
            'statusCategory != Done',
        ]
        return " AND ".join([p for p in parts if p])

    def jql_overdue(self, assignee_email: str) -> str:
        base = self._base_constraints(assignee_email)
        cf = self._cf_key()
        or_parts = ['(duedate < startOfDay() AND duedate is not EMPTY)']
        if cf:
            or_parts.append(f'({cf} < startOfDay() AND {cf} is not EMPTY)')
        return f'{base} AND ({" OR ".join(or_parts)}) ORDER BY duedate ASC, updated DESC'

    def jql_for_day(self, assignee_email: str, day: str) -> str:
        shift = 0 if day == "today" else 1
        base = self._base_constraints(assignee_email)
        cf = self._cf_key()
        target = "startOfDay()" if shift == 0 else "startOfDay('+1d')"
        or_parts = [f'(duedate = {target})']
        if cf:
            or_parts.append(f'({cf} = {target})')
        return f'{base} AND ({" OR ".join(or_parts)}) ORDER BY duedate ASC, updated DESC'

    def jql_closed_today(self, assignee_email: str) -> str:
        if self.done_override:
            return self.done_override
        proj = f' AND project in ({", ".join(self.projects)})' if self.projects else ""
        return f'assignee = "{assignee_email}"{proj} AND status CHANGED TO Done DURING (startOfDay(), now()) ORDER BY resolutiondate DESC'

    def search(self, jql: str, max_results: int = 50) -> List[Dict]:
        url = f"{self.base}/rest/api/3/search/jql"
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "duedate", "issuetype", "assignee", "project", "priority", "status"],
        }
        log.debug("POST %s", url)
        log.debug("JQL: %s", jql)
        try:
            r = self.session.post(url, json=payload, timeout=30)
            log.debug("HTTP %s %s", r.status_code, r.reason)
            r.raise_for_status()
            data = r.json()
        except requests.HTTPError as e:
            if getattr(e, "response", None) is not None and e.response.status_code in (404, 405):
                log.warning("POST /search/jql not accepted, trying GET fallback")
                r = self.session.get(
                    url,
                    params={
                        "jql": jql,
                        "maxResults": max_results,
                        "fields": "summary,duedate,issuetype,assignee,project",
                    },
                    timeout=30,
                )
                log.debug("HTTP %s %s (GET fallback)", r.status_code, r.reason)
                r.raise_for_status()
                data = r.json()
            else:
                body = e.response.text if getattr(e, "response", None) is not None else str(e)
                log.error("JIRA HTTP error: %s\nResponse body:\n%s", e, body)
                raise
        issues = data.get("issues", [])
        parsed: List[Dict] = []
        for it in issues:
            key = it["key"]
            f = it.get("fields", {})
            parsed.append(
                {
                    "key": key,
                    "summary": f.get("summary", "(no summary)"),
                    "duedate": f.get("duedate"),
                    "issuetype": (f.get("issuetype") or {}).get("name"),
                    "project": (f.get("project") or {}).get("key"),
                    "priority": (f.get("priority") or {}).get("name"),
                    "status": (f.get("status") or {}).get("name"),
                }
            )
        return parsed

    def make_issue_url(self, key: str) -> str:
        return f"{self.base}/browse/{key}"

    def make_issues_link(self, jql: str) -> str:
        return f"{self.base}/issues/?jql={quote_plus(jql)}"
