### RepoScout 📜 🧠


RepoScout is a agentic AI project for investigating GitHub issues

Given a repository and an issue number, RepoScout reads the issue and uses a set of read only GitHub tools to investigate it

Depending on the problem it can:

- Search the codebase
- Inspect relevant files and commit history
- Look at GitHub Actions runs and failure logs
- Generate an evidence-backed Markdown report

> [!IMPORTANT]
> Supporting repository for testing this tool - [RepoScout Test Repo](https://github.com/neelkumar01/repoScout-testing)

### How it works?

```mermaid
flowchart TD
    A[Repository + Issue Number] --> B[RepoScout Agent]

    B --> C{Choose useful evidence}

    C --> D[Issue & Comments]
    C --> E[Code Search & Files]
    C --> F[Commit History]
    C --> G[GitHub Actions]

    G --> H[Workflow Runs]
    H --> I[Jobs & Failure Logs]

    D --> J[Evidence-backed Investigation]
    E --> J
    F --> J
    I --> J

    J --> K[Structure Result]
    K --> L[Markdown Report]
```

### Why RepoScout?

Understanding a GitHub issue often involves more than reading its description

A developer may need to:

- Find the relevant code
- Understand how that code behaves
- Check whether something recently changed
- Inspect CI failures
- Read workflow logs
- Separate actual evidence from assumptions

RepoScout explores whether an AI agent can handle this initial investigation using tools while keeping the final result grounded in repository evidence

### Available Tools

The agent currently has tools for:

1. Reading an issue
2. Reading issue comments
3. Searching repository code
4. Reading repository files
5. Checking commits that changed a file
6. Inspecting recent GitHub Actions runs
7. Inspecting workflow jobs
8. Extracting useful evidence from job logs

> [!NOTE]
> All repository operations are read only

### Problems I Faced 

- Tool call formatting

The model occasionally generated malformed tool arguments or attempted to use tools that were not available. Tool descriptions and the agent instructions were made more explicit to reduce this behavior

- Structured output and tool calling

Using structured output during the same model interaction as tool calling caused compatibility problems with the model provider

The workflow was therefore separated into two stages:

```text
Agent + GitHub tools
        ↓
Technical investigation
        ↓
LLM without tools
        ↓
Structured result
        ↓
Markdown report
```

This keeps tool based investigation separate from final report formatting

- GitHub search errors

LLM generated search queries are not always valid GitHub code search queries. Search failures are handled so that one bad query does not necessarily end the entire investigation

- Confidence calibration

During testing the agent initially treated a possible performance cause as a confirmed root cause despite having no runtime metrics

The investigation instructions were improved so that code smells are treated as hypotheses rather than proof especially for intermittent and performance related problems

### Limitations:

- Analysis depends on the quality of the issue and available repository evidence
- LLM tool calls can occasionally be malformed
- Large CI logs have to be filtered before analysis

> [!TIP]
> The generated report should therefore be treated as an investigation aid rather than a definitive diagnosis
