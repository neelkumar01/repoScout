import argparse
import os
import sys

from dotenv import load_dotenv

from github_tools import GitHubClient
from agent import investigate_issue
from report import generate_report


load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Agentic GitHub issue investigator"
        )
    )

    parser.add_argument(
        "repo",
        help="GitHub repository: owner/repo",
    )

    parser.add_argument(
        "issue",
        type=int,
        help="GitHub issue number",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    github_token = os.getenv(
        "GITHUB_TOKEN"
    )

    groq_api_key = os.getenv(
        "GROQ_API_KEY"
    )

    model = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    )

    max_steps = int(
        os.getenv(
            "MAX_AGENT_STEPS",
            "10",
        )
    )

    if not github_token:
        sys.exit(
            "Missing GITHUB_TOKEN in .env"
        )

    if not groq_api_key:
        sys.exit(
            "Missing GROQ_API_KEY in .env"
        )

    github = GitHubClient(
        repo=args.repo,
        token=github_token,
    )

    print()
    print("RepoScout")
    print("---------")
    print(
        f"Repository : {args.repo}"
    )
    print(
        f"Issue      : #{args.issue}"
    )
    print()
    print(
        "Starting agentic investigation..."
    )

    try:
        result = investigate_issue(
            github=github,
            repo=args.repo,
            issue_number=args.issue,
            model_name=model,
            max_steps=max_steps,
        )

    except Exception as error:

        print()
        print(
            f"Investigation failed: {error}"
        )

        return

    print(
        "Investigation complete."
    )

    report = generate_report(
        repo=args.repo,
        issue_number=args.issue,
        result=result,
    )

    print()
    print(
        f"Confidence : {result.confidence}"
    )

    print(
        f"Root cause : "
        f"{result.likely_root_cause}"
    )

    print()
    print(
        f"Report saved: {report}"
    )


if __name__ == "__main__":
    main()