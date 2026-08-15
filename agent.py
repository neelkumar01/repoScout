import json
from typing import Literal

from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_groq import ChatGroq


class Evidence(BaseModel):
    source_type: str
    source: str
    finding: str
    url: str | None = None


class InvestigationResult(BaseModel):
    issue_summary: str
    likely_root_cause: str
    confidence: Literal["high", "medium", "low"]
    explanation: str
    evidence: list[Evidence]
    suggested_next_steps: list[str]
    limitations: list[str]


def build_tools(github):

    @tool
    def get_issue(issue_number: int) -> str:
        """Read a GitHub issue including title, body, labels, author, and URL."""
        return json.dumps(
            github.get_issue(issue_number),
            indent=2,
        )

    @tool
    def get_issue_comments(issue_number: int) -> str:
        """Read comments from a GitHub issue for additional context."""
        return json.dumps(
            github.get_issue_comments(issue_number),
            indent=2,
        )

    @tool
    def search_code(query: str) -> str:
        """Search repository code for a keyword, symbol, function, or error message."""
        return json.dumps(
            github.search_code(query),
            indent=2,
        )

    @tool
    def read_file(
        path: str,
        ref: str | None = None,
    ) -> str:
        """Read one repository file, optionally at a branch, tag, or commit."""
        return json.dumps(
            github.read_file(path, ref),
            indent=2,
        )

    @tool
    def get_file_commits(path: str) -> str:
        """Inspect recent commits that changed a repository file."""
        return json.dumps(
            github.get_file_commits(path),
            indent=2,
        )

    @tool
    def get_workflow_runs(limit: int = 10) -> str:
        """List recent completed GitHub Actions workflow runs."""
        return json.dumps(
            github.get_workflow_runs(limit=limit),
            indent=2,
        )

    @tool
    def get_workflow_jobs(run_id: int) -> str:
        """Inspect jobs and step results for a GitHub Actions workflow run."""
        return json.dumps(
            github.get_workflow_jobs(run_id),
            indent=2,
        )

    @tool
    def get_job_log(job_id: int) -> str:
        """Read filtered failure evidence from a GitHub Actions job log."""
        return json.dumps(
            github.get_job_log(job_id),
            indent=2,
        )

    return [
        get_issue,
        get_issue_comments,
        search_code,
        read_file,
        get_file_commits,
        get_workflow_runs,
        get_workflow_jobs,
        get_job_log,
    ]


SYSTEM_PROMPT = """
You are RepoScout, a senior software engineer investigating GitHub issues.

You may ONLY use these tools:

- get_issue
- get_issue_comments
- search_code
- read_file
- get_file_commits
- get_workflow_runs
- get_workflow_jobs
- get_job_log

Never invent or call any other tool.
There is no list_files, repo_browser, shell, filesystem,
browser, terminal, or generic repository browsing tool.

If you need to find a file:
1. use search_code with a relevant keyword or symbol
2. then use read_file on a returned path
3. Prefer the shortest investigation path that can answer the issue.
4. Do not inspect commit history unless:
   - the issue mentions regression, "used to work", or recent changes, or
   - current code alone cannot explain the behavior.
5. Do not inspect GitHub Actions unless:
   - the issue mentions CI, tests, builds, workflows, or environment differences, or
   - runtime/CI evidence is necessary to confirm the hypothesis.
6. If an issue explicitly says something "used to work", "recently broke", or otherwise suggests a regression, inspect the commit history of the relevant file before concluding when possible.

Use the available read-only GitHub tools to investigate the issue.

Rules:

1. Start by reading the issue.
2. Use only tools relevant to the issue.
3. Do not call every tool automatically.
4. Search code before trying to read an unknown file.
5. Inspect commit history only when a regression or recent change is relevant.
6. Inspect GitHub Actions only when CI evidence is relevant.
7. Never invent repository facts, files, commits, logs, or tools.
8. Separate evidence from inference.
9. Stop when enough evidence is available.
10. If evidence is insufficient, say so clearly.
11. Give practical next steps.
12. Finish with a normal technical investigation, not JSON.
13. Whenever a tool result contains a GitHub URL, preserve that URL in the final evidence. Do not replace it with null unless no URL exists.

Confidence rules:

- High confidence requires direct evidence that clearly explains
  the reported behavior.

- Medium confidence means evidence supports the hypothesis,
  but an important part is still unverified.

- Low confidence means the available evidence is insufficient
  to establish a root cause.

- Finding a suspicious bug or code smell does not prove that it
  caused the reported issue.

- For performance, intermittent, reliability, or environment-specific
  problems, do not claim causation without supporting runtime evidence,
  logs, metrics, profiling data, CI evidence, or a clear reproduction.

- When evidence is insufficient, explicitly say that the root cause
  cannot yet be determined and recommend what evidence should be
  collected next.
"""

def structure_investigation(
    model_name,
    investigation_text,
):
    model = ChatGroq(
        model=model_name,
        temperature=0,
        max_retries=2,
    )

    prompt = f"""
Convert the investigation below into valid JSON.

Return ONLY JSON.

Required structure:

{{
  "issue_summary": "string",
  "likely_root_cause": "string",
  "confidence": "high | medium | low",
  "explanation": "string",
  "evidence": [
    {{
      "source_type": "string",
      "source": "string",
      "finding": "string",
      "url": null
    }}
  ],
  "suggested_next_steps": [
    "step 1",
    "step 2"
  ],
  "limitations": [
    "limitation 1"
  ]
}}

Important:
- suggested_next_steps MUST be a JSON array of strings.
- limitations MUST be a JSON array of strings.
- evidence MUST be a JSON array.
- Do not add new facts.
- Preserve uncertainty.
- Return no markdown and no explanation outside the JSON.
- Preserve every source URL present in the investigation.
- Use null only when no source URL was available.

Investigation:

{investigation_text}
"""

    response = model.invoke(prompt)

    content = response.content.strip()

    if content.startswith("```"):
        content = content.strip("`")

        if content.startswith("json"):
            content = content[4:].strip()

    data = json.loads(content)

    return InvestigationResult.model_validate(data)

def investigate_issue(
    github,
    repo,
    issue_number,
    model_name,
    max_steps=10,
):
    tools = build_tools(github)

    model = ChatGroq(
        model=model_name,
        temperature=0,
        max_retries=2,
    )

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )

    task = f"""
Investigate GitHub issue #{issue_number}
in repository {repo}.

Begin with get_issue.

Use ONLY the registered RepoScout tools.
Do not invent tools or tool namespaces.

Gather the minimum evidence necessary and produce
an evidence-backed technical investigation.
"""

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": task,
                }
            ]
        },
        config={
            "recursion_limit": max_steps * 3
        },
    )

    final_message = result["messages"][-1]
    investigation_text = final_message.content

    if isinstance(investigation_text, list):
        investigation_text = "\n".join(
            part.get("text", "")
            if isinstance(part, dict)
            else str(part)
            for part in investigation_text
        )

    return structure_investigation(
        model_name=model_name,
        investigation_text=investigation_text,
    )