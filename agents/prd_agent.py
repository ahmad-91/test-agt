import os
import datetime
from slugify import slugify
from github import Github
from openai import OpenAI

# ==========================
# Environment Variables
# ==========================
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])
ISSUE_TITLE = os.environ["ISSUE_TITLE"]
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
REPO_FULL_NAME = os.environ["REPO_FULL_NAME"]

# ==========================
# Init Clients
# ==========================
gh = Github(GITHUB_TOKEN)
repo = gh.get_repo(REPO_FULL_NAME)
issue = repo.get_issue(number=ISSUE_NUMBER)

client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================
# Generate PRD via LLM
# ==========================
def generate_prd(title, body):
    prompt = f"""
You are a senior product manager.

Generate a complete Product Requirements Document (PRD)
for the following idea.

Title: {title}

Description:
{body}

Structure:
- Overview
- Goals
- Non-Goals
- Target Users
- User Stories
- Functional Requirements
- Non-Functional Requirements
- Edge Cases
- Open Questions

Be concrete and implementation-ready.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a senior product manager."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4,
    )

    return response.choices[0].message.content


prd_content = generate_prd(ISSUE_TITLE, ISSUE_BODY)

# ==========================
# Prepare File
# ==========================
slug = slugify(ISSUE_TITLE)
date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

file_path = f"docs/prd/{slug}.md"

full_content = f"""# PRD: {ISSUE_TITLE}

Generated from Issue #{ISSUE_NUMBER}
Date: {date_str}

---

{prd_content}
"""

# ==========================
# Create Branch
# ==========================
base_branch = repo.get_branch(repo.default_branch)
branch_name = f"agent/prd-{slug}"

repo.create_git_ref(
    ref=f"refs/heads/{branch_name}",
    sha=base_branch.commit.sha
)

# ==========================
# Create File
# ==========================
repo.create_file(
    path=file_path,
    message=f"Add PRD for: {ISSUE_TITLE}",
    content=full_content,
    branch=branch_name
)

# ==========================
# Create Pull Request
# ==========================
pr = repo.create_pull(
    title=f"[Agent] PRD: {ISSUE_TITLE}",
    body=f"""
This PR was automatically generated from Issue #{ISSUE_NUMBER}.

Please review the PRD.

Closes #{ISSUE_NUMBER}
""",
    head=branch_name,
    base=repo.default_branch
)

# ==========================
# Comment on Issue
# ==========================
issue.create_comment(f"✅ PRD generated and PR opened: {pr.html_url}")

print("PR created successfully:", pr.html_url)