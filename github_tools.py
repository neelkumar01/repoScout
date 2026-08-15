import base64
import re
import requests

class GitHubClient:
    def __init__(self, repo, token):
        self.repo = repo
        self.api = "https://api.github.com"

        self.session = requests.Session()

        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _get(self, endpoint, **params):
        url = f"{self.api}{endpoint}"

        response = self.session.get(
            url,
            params=params,
            timeout=30,
        )

        response.raise_for_status()
        return response

    def get_issue(self, issue_number):
        response = self._get(
            f"/repos/{self.repo}/issues/{issue_number}"
        )

        issue = response.json()

        return {
            "number": issue["number"],
            "title": issue["title"],
            "body": (issue.get("body") or "")[:8000],
            "state": issue["state"],
            "author": issue["user"]["login"],
            "labels": [
                label["name"]
                for label in issue.get("labels", [])
            ],
            "created_at": issue["created_at"],
            "url": issue["html_url"],
        }

    def get_issue_comments(
        self,
        issue_number,
        limit=15,
    ):
        response = self._get(
            f"/repos/{self.repo}/issues/"
            f"{issue_number}/comments",
            per_page=min(limit, 30),
        )

        comments = response.json()

        return [
            {
                "author": comment["user"]["login"],
                "body": (
                    comment.get("body") or ""
                )[:4000],
                "created_at": comment["created_at"],
                "url": comment["html_url"],
            }
            for comment in comments[:limit]
        ]

    def search_code(
        self,
        query,
        limit=8,
    ):
        query = query.strip()

        if not query:
            return []

        try:
            response = self._get(
                "/search/code",
                q=f'"{query}" repo:{self.repo}',
                per_page=min(limit, 20),
            )

        except requests.HTTPError as error:
            if error.response.status_code == 422:
                return {
                    "error": (
                        f"GitHub code search could not process "
                        f"the query: {query}"
                    )
                }

            raise

        items = response.json().get(
            "items",
            [],
        )

        return [
            {
                "name": item["name"],
                "path": item["path"],
                "url": item["html_url"],
            }
            for item in items[:limit]
        ]

    def read_file(
        self,
        path,
        ref=None,
    ):
        params = {}

        if ref:
            params["ref"] = ref

        response = self._get(
            f"/repos/{self.repo}/contents/{path}",
            **params,
        )

        data = response.json()

        if isinstance(data, list):
            return {
                "error": "Path is a directory, not a file."
            }

        if data.get("encoding") != "base64":
            return {
                "error": "File content is not available as text."
            }

        raw = base64.b64decode(
            data["content"]
        )

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "error": "File is not UTF-8 text."
            }

        text = text[:12000]

        return {
            "path": path,
            "ref": ref or "default branch",
            "content": text,
            "url": data["html_url"],
        }

    def get_file_commits(
        self,
        path,
        limit=8,
    ):
        response = self._get(
            f"/repos/{self.repo}/commits",
            path=path,
            per_page=min(limit, 20),
        )

        commits = response.json()

        results = []

        for commit in commits[:limit]:
            info = commit["commit"]

            results.append({
                "sha": commit["sha"],
                "message": (
                    info["message"].splitlines()[0]
                ),
                "author": (
                    info.get("author", {})
                    .get("name", "unknown")
                ),
                "date": (
                    info.get("author", {})
                    .get("date")
                ),
                "url": commit["html_url"],
            })

        return results

    def get_workflow_runs(
        self,
        limit=10,
    ):
        response = self._get(
            f"/repos/{self.repo}/actions/runs",
            status="completed",
            per_page=min(limit, 30),
        )

        runs = response.json().get(
            "workflow_runs",
            [],
        )

        return [
            {
                "run_id": run["id"],
                "name": run["name"],
                "event": run["event"],
                "branch": run["head_branch"],
                "sha": run["head_sha"],
                "conclusion": run["conclusion"],
                "created_at": run["created_at"],
                "url": run["html_url"],
            }
            for run in runs[:limit]
        ]

    def get_workflow_jobs(
        self,
        run_id,
    ):
        response = self._get(
            f"/repos/{self.repo}/actions/"
            f"runs/{run_id}/jobs",
            per_page=100,
        )

        jobs = response.json().get(
            "jobs",
            [],
        )

        results = []

        for job in jobs:

            steps = [
                {
                    "name": step["name"],
                    "conclusion": step.get(
                        "conclusion"
                    ),
                }
                for step in job.get(
                    "steps",
                    []
                )
            ]

            results.append({
                "job_id": job["id"],
                "name": job["name"],
                "conclusion": job["conclusion"],
                "steps": steps,
                "url": job["html_url"],
            })

        return results

    def get_job_log(
        self,
        job_id,
    ):

        response = self._get(
            f"/repos/{self.repo}/actions/"
            f"jobs/{job_id}/logs"
        )

        text = response.text

        return {
            "job_id": job_id,
            "evidence": extract_log_evidence(text),
        }


def extract_log_evidence(
    log_text,
    max_chars=12000,
):

    lines = log_text.splitlines()

    keywords = re.compile(
        r"fail|failed|failure|error|exception|"
        r"panic|timeout|timed out|fatal|traceback|"
        r"assertion",
        re.IGNORECASE,
    )

    selected = set()

    for index, line in enumerate(lines):

        if not keywords.search(line):
            continue

        start = max(
            0,
            index - 2,
        )

        end = min(
            len(lines),
            index + 4,
        )

        for position in range(
            start,
            end,
        ):
            selected.add(position)

    if selected:

        evidence = "\n".join(
            lines[index]
            for index in sorted(selected)
        )

    else:
        evidence = "\n".join(
            lines[-100:]
        )

    return evidence[-max_chars:]