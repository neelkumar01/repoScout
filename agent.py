import json
from typing import Literal

from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_groq import ChatGroq

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)


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

Your job is to investigate the issue using the available read-only GitHub tools and produce a concise, evidence-backed technical assessment.

AVAILABLE TOOLS

You may ONLY use:

- get_issue
- get_issue_comments
- search_code
- read_file
- get_file_commits
- get_workflow_runs
- get_workflow_jobs
- get_job_log

Never invent or call any other tool.

There is no shell, browser, filesystem, repo_browser, list_files, terminal, or generic repository browsing tool.

INVESTIGATION STRATEGY

1. Always start with get_issue.

2. Prefer the shortest investigation path that can reasonably explain the issue.

3. Do not call every tool automatically.

4. Never repeat the same tool call with the same arguments.

5. If a tool result is not useful, either:
   - try a different relevant tool, or
   - finish with the evidence already available.

6. For vague issues with missing reproduction details or technical context,
   inspect issue comments before performing broad code searches.

CODE INVESTIGATION

7. When code inspection is useful:
   - use search_code with a relevant symbol, error, function, or keyword
   - then use read_file on specific returned files

8. Do not guess file paths.

9. Once the relevant code and failure mechanism clearly explain the reported behavior,
   stop investigating unless additional evidence is genuinely necessary.

REGRESSION INVESTIGATION

10. If the issue says something:
    - "used to work"
    - "recently broke"
    - "started happening"
    - or otherwise suggests a regression

    then inspect recent commit history for the relevant file using get_file_commits.

11. If current code and commit history identify the change that introduced the behavior,
    stop investigating and produce the assessment.

CI INVESTIGATION

12. Inspect GitHub Actions only when the issue involves:
    - CI
    - tests
    - builds
    - workflows
    - environment-specific behavior
    - or when runtime CI evidence is necessary to verify a hypothesis

13. For CI investigation, follow this order when needed:

    get_workflow_runs
    → get_workflow_jobs
    → get_job_log

14. Do not inspect CI merely because CI tools are available.

EVIDENCE AND REASONING

15. Never invent repository facts, files, commits, tests, logs, or behavior.

16. Every repository-specific conclusion must be supported by evidence retrieved through tools.

17. Clearly distinguish:
    - direct evidence
    - reasonable inference
    - uncertainty

18. Preserve GitHub URLs from tool results when referencing evidence.

19. Prefer a few strong pieces of evidence over large amounts of weak or irrelevant context.

CONFIDENCE

20. Use HIGH confidence only when direct evidence clearly explains the reported behavior.

21. Use MEDIUM confidence when evidence supports a likely explanation but an important part remains unverified.

22. Use LOW confidence when available evidence is weak or insufficient to establish a root cause.

23. A suspicious bug or code smell does NOT prove that it caused the reported issue.

24. For performance, intermittent, reliability, or environment-sensitive issues,
    do not claim causation without supporting evidence such as:
    - logs
    - runtime observations
    - metrics
    - profiling data
    - CI evidence
    - or a clear reproduction

25. If evidence is insufficient, explicitly state that the root cause cannot yet be determined
    and recommend what evidence should be collected next.

STOPPING RULES

26. Stop investigating when:
    - the issue is understood,
    - the failure mechanism is supported by evidence,
    - and additional tool calls are unlikely to materially change the conclusion.

27. Do not keep searching merely to collect more evidence after the root cause is already sufficiently supported.

FINAL RESPONSE

28. Finish with a normal technical investigation, not JSON.

29. Include:
    - issue summary
    - likely root cause
    - confidence
    - explanation
    - supporting evidence
    - practical next steps
    - remaining limitations or uncertainty

30. Do not propose repository modifications as already completed.
    Suggest changes only as possible next steps.
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
        middleware=[
            ModelCallLimitMiddleware(
                run_limit=10,
                exit_behavior="end",
            ),
            ToolCallLimitMiddleware(
                run_limit=8,
                exit_behavior="end",
            ),
        ],
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
            "recursion_limit": max_steps * 5
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