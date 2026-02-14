import os
import datetime
from slugify import slugify

from openai import OpenAI

from github import Github, Auth
from github.GithubException import GithubException

# ==========================
# Environment Variables
# ==========================
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "").strip()
ISSUE_BODY = os.environ.get("ISSUE_BODY", "").strip()
REPO_FULL_NAME = os.environ["REPO_FULL_NAME"]

# ==========================
# Init Clients
# ==========================
gh = Github(auth=Auth.Token(GITHUB_TOKEN))
repo = gh.get_repo(REPO_FULL_NAME)
issue = repo.get_issue(number=ISSUE_NUMBER)

llm = OpenAI(api_key=OPENAI_API_KEY)

# ==========================
# Helpers
# ==========================
def generate_prd(title: str, body: str) -> str:
    """
    Generate an implementation-ready PRD in Arabic by default (since your project is Arabic),
    but keeps structure clear and engineering-friendly.
    """
    prompt = f"""
اكتب وثيقة PRD كاملة وجاهزة للتنفيذ (Implementation-ready) للفكرة التالية.

العنوان: {title}

وصف الفكرة:
{body}

الهيكل المطلوب (اكتب العناوين نفسها وبنفس الترتيب):
1) نظرة عامة
2) الأهداف
3) خارج النطاق (Non-Goals)
4) المستخدمون المستهدفون
5) قصص المستخدم (User Stories)
6) المتطلبات الوظيفية (Functional Requirements)
7) المتطلبات غير الوظيفية (Non-Functional Requirements) — (سكيل، أداء، توفر، أمان، خصوصية)
8) الحالات الحافة (Edge Cases)
9) الأسئلة المفتوحة
10) معايير القبول (Acceptance Criteria) — نقاط واضحة قابلة للاختبار

ملاحظات:
- خلي المتطلبات دقيقة، قابلة للقياس قدر الإمكان.
- إذا المعلومات ناقصة، افترض افتراضات معقولة واكتبها بوضوح تحت "الأسئلة المفتوحة".
"""
    resp = llm.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "أنت مدير منتج خبير تكتب PRD قابلة للتنفيذ لفريق هندسي."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()


def ensure_branch(repo, branch_name: str, base_sha: str) -> None:
    """
    Create branch if not exists, otherwise reuse it.
    """
    try:
        repo.get_git_ref(f"heads/{branch_name}")
        print(f"[INFO] Branch exists, reusing: {branch_name}")
    except GithubException as e:
        if e.status == 404:
            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)
            print(f"[INFO] Branch created: {branch_name}")
        else:
            raise


def upsert_file(repo, path: str, content: str, message: str, branch: str) -> str:
    """
    Create file if not exists, otherwise update file.
    Returns 'created' or 'updated'.
    """
    try:
        existing = repo.get_contents(path, ref=branch)
        repo.update_file(
            path=path,
            message=message,
            content=content,
            sha=existing.sha,
            branch=branch,
        )
        print(f"[INFO] Updated file: {path}")
        return "updated"
    except GithubException as e:
        if e.status == 404:
            repo.create_file(
                path=path,
                message=message,
                content=content,
                branch=branch,
            )
            print(f"[INFO] Created file: {path}")
            return "created"
        else:
            raise


def find_open_pr_for_branch(repo, branch_name: str):
    """
    If there's an open PR from this branch, return it; else None.
    """
    # head format: "owner:branch"
    head = f"{repo.owner.login}:{branch_name}"
    prs = repo.get_pulls(state="open", head=head)
    return next(iter(prs), None)


# ==========================
# Main
# ==========================
if not ISSUE_TITLE:
    raise ValueError("ISSUE_TITLE is empty. Please provide a title for the issue.")

slug = slugify(ISSUE_TITLE)
date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

# Prefer one branch per issue to make reruns safe and predictable
branch_name = f"agent/prd-{slug}-issue-{ISSUE_NUMBER}"

file_path = f"docs/prd/{slug}-issue-{ISSUE_NUMBER}.md"

prd_text = generate_prd(ISSUE_TITLE, ISSUE_BODY)

full_content = f"""# PRD: {ISSUE_TITLE}

- Generated from: Issue #{ISSUE_NUMBER}
- Date (UTC): {date_str}

---

{prd_text}
"""

# Ensure branch exists (or reuse)
base_branch = repo.get_branch(repo.default_branch)
ensure_branch(repo, branch_name, base_branch.commit.sha)

# Upsert PRD file
result = upsert_file(
    repo=repo,
    path=file_path,
    content=full_content,
    message=f"[Agent] Add/Update PRD for Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}",
    branch=branch_name,
)

# Create PR if not exists
existing_pr = find_open_pr_for_branch(repo, branch_name)
if existing_pr:
    issue.create_comment(
        f"ℹ️ تم تحديث ملف الـ PRD ({result}). يوجد PR مفتوح مسبقًا لهذا الفرع:\n{existing_pr.html_url}"
    )
    print("[INFO] PR already exists:", existing_pr.html_url)
else:
    pr = repo.create_pull(
        title=f"[Agent] PRD (Issue #{ISSUE_NUMBER}): {ISSUE_TITLE}",
        body=(
            f"هذا الـ PR تم توليده تلقائيًا من Issue #{ISSUE_NUMBER}.\n\n"
            f"- PRD file: `{file_path}`\n\n"
            f"يرجى المراجعة.\n\n"
            f"Closes #{ISSUE_NUMBER}"
        ),
        head=branch_name,
        base=repo.default_branch,
    )
    issue.create_comment(f"✅ تم توليد PRD وفتح Pull Request:\n{pr.html_url}")
    print("[INFO] PR created successfully:", pr.html_url)
