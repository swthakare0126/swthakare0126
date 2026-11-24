"""Automated GitHub profile README updater and validator.

Fetches public profile metrics, featured repositories, recent public activity,
and contribution-snake availability via the GitHub REST API, then updates
delimited sections in README.md without external dependencies.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = ("snake", "stats", "repos", "activity")

SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def github_get(
    path: str,
    token: str | None = None,
    allow_404: bool = False,
) -> Any:
    """Perform a GET request against the GitHub REST API."""
    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "swthakare0126-profile-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {exc.code} for {path}: {body}") from exc


def replace_section(content: str, section: str, body: str) -> str:
    """Replace content between START_SECTION and END_SECTION markers."""
    start_marker = f"<!-- START_SECTION:{section} -->"
    end_marker = f"<!-- END_SECTION:{section} -->"
    pattern = re.compile(
        rf"({re.escape(start_marker)}\r?\n)(.*?)(\r?\n{re.escape(end_marker)})",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise ValueError(f"Missing markers for section '{section}' in README.")
    return pattern.sub(lambda m: f"{m.group(1)}{body}{m.group(3)}", content, count=1)


def validate_readme_markers(content: str) -> list[str]:
    """Return a list of missing or malformed section errors."""
    errors: list[str] = []
    for section in REQUIRED_SECTIONS:
        start_marker = f"<!-- START_SECTION:{section} -->"
        end_marker = f"<!-- END_SECTION:{section} -->"
        pattern = re.compile(
            rf"{re.escape(start_marker)}\r?\n.*?\r?\n{re.escape(end_marker)}",
            re.DOTALL,
        )
        if not pattern.search(content):
            errors.append(f"Missing or malformed markers for section '{section}'.")
    return errors


def scan_for_secrets(paths: list[Path]) -> list[str]:
    """Scan tracked markdown/workflow/script files for accidental credentials."""
    findings: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"Potential secret match ({pattern.pattern}) in {path}")
    return findings


def build_snake_section(repo_full_name: str, has_output_branch: bool) -> str:
    """Return HTML picture block when the snake output branch exists."""
    if not has_output_branch:
        return (
            "<!-- Contribution snake will appear here automatically once the "
            "'Generate Contribution Snake' workflow has created the 'output' branch. -->"
        )
    base = f"https://raw.githubusercontent.com/{repo_full_name}/output"
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{base}/github-contribution-grid-snake-dark.svg" />\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{base}/github-contribution-grid-snake.svg" />\n'
        f'  <img alt="GitHub contribution snake" src="{base}/github-contribution-grid-snake.svg" />\n'
        "</picture>"
    )


def compute_metrics(
    user: dict[str, Any],
    repos: list[dict[str, Any]],
) -> tuple[int, int, int, str]:
    """Compute public repos, total stars, followers, and top languages."""
    owned_sources = [r for r in repos if not r.get("fork", False)]
    public_repos = int(user.get("public_repos", 0))
    total_stars = sum(int(r.get("stargazers_count", 0)) for r in owned_sources)
    followers = int(user.get("followers", 0))
    lang_counts = Counter(
        r["language"] for r in owned_sources if r.get("language")
    )
    top_langs = (
        ", ".join(lang for lang, _ in lang_counts.most_common(5))
        or "Terraform • HCL • PowerShell • Python"
    )
    return public_repos, total_stars, followers, top_langs


def build_stats_section(
    user: dict[str, Any],
    repos: list[dict[str, Any]],
    synced_at: datetime,
) -> str:
    """Build the markdown table summarizing GitHub profile metrics."""
    public_repos, total_stars, followers, top_langs = compute_metrics(user, repos)

    rows = [
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| Public Repositories | **{public_repos}** |",
        f"| Total Stars Earned | **{total_stars}** |",
        f"| Followers | **{followers}** |",
        f"| Top Languages | {top_langs} |",
        f"| Last Auto-Synced (UTC) | `{synced_at.strftime('%Y-%m-%d %H:%M UTC')}` |",
    ]
    return "\n".join(rows)


def build_live_metrics_svg(
    username: str,
    user: dict[str, Any],
    repos: list[dict[str, Any]],
    synced_at: datetime,
) -> str:
    """Render an animated SVG telemetry card for GitHub profile metrics."""
    public_repos, total_stars, followers, top_langs = compute_metrics(user, repos)
    safe_user = html.escape(username)
    safe_langs = html.escape(top_langs[:48] + ("..." if len(top_langs) > 48 else ""))
    synced_label = html.escape(synced_at.strftime("%Y-%m-%d %H:%M UTC"))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 180" width="100%" role="img" aria-label="Live GitHub Telemetry Metrics for {safe_user}">
  <defs>
    <linearGradient id="mBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070B14" />
      <stop offset="100%" stop-color="#0F172A" />
    </linearGradient>
    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0078D4" />
      <stop offset="50%" stop-color="#38BDF8" />
      <stop offset="100%" stop-color="#8B5CF6" />
    </linearGradient>
    <style>
      .hdr {{ font: 700 12px 'Cascadia Code', Consolas, monospace; fill: #38BDF8; letter-spacing: 1px; }}
      .lbl {{ font: 600 12px 'Segoe UI', Roboto, Arial, sans-serif; fill: #94A3B8; }}
      .val {{ font: 800 28px 'Segoe UI', Roboto, Arial, sans-serif; fill: #F8FAFC; }}
      .sub {{ font: 600 13px 'Cascadia Code', Consolas, monospace; fill: #E2E8F0; }}
      .pulse {{ animation: ledPulse 1.8s ease-in-out infinite; }}
      .sweep {{ animation: sweepBar 3.6s ease-in-out infinite; }}
      @keyframes ledPulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.25; }} }}
      @keyframes sweepBar {{ 0% {{ width: 40px; }} 50% {{ width: 174px; }} 100% {{ width: 40px; }} }}
    </style>
  </defs>

  <rect x="2" y="2" width="1196" height="176" rx="14" fill="url(#mBg)" stroke="#1E3A8A" stroke-width="1.5" />
  <circle class="pulse" cx="28" cy="26" r="5" fill="#22C55E" />
  <text x="42" y="30" class="hdr">GITHUB LIVE TELEMETRY • @{safe_user} • SYNCED {synced_label}</text>

  <g transform="translate(26, 52)">
    <rect x="0" y="0" width="210" height="102" rx="10" fill="#0B1324" stroke="#1E293B" stroke-width="1.2" />
    <text x="18" y="28" class="lbl">PUBLIC REPOSITORIES</text>
    <text x="18" y="68" class="val">{public_repos}</text>
    <rect x="18" y="84" width="174" height="4" rx="2" fill="#1E293B" />
    <rect class="sweep" x="18" y="84" width="120" height="4" rx="2" fill="url(#barGrad)" />
  </g>

  <g transform="translate(254, 52)">
    <rect x="0" y="0" width="210" height="102" rx="10" fill="#0B1324" stroke="#1E293B" stroke-width="1.2" />
    <text x="18" y="28" class="lbl">TOTAL STARS EARNED</text>
    <text x="18" y="68" class="val">{total_stars}</text>
    <rect x="18" y="84" width="174" height="4" rx="2" fill="#1E293B" />
    <rect x="18" y="84" width="130" height="4" rx="2" fill="#F59E0B" />
  </g>

  <g transform="translate(482, 52)">
    <rect x="0" y="0" width="210" height="102" rx="10" fill="#0B1324" stroke="#1E293B" stroke-width="1.2" />
    <text x="18" y="28" class="lbl">FOLLOWERS</text>
    <text x="18" y="68" class="val">{followers}</text>
    <rect x="18" y="84" width="174" height="4" rx="2" fill="#1E293B" />
    <rect x="18" y="84" width="145" height="4" rx="2" fill="#22C55E" />
  </g>

  <g transform="translate(710, 52)">
    <rect x="0" y="0" width="464" height="102" rx="10" fill="#0B1324" stroke="#1E293B" stroke-width="1.2" />
    <text x="18" y="28" class="lbl">TOP LANGUAGES &amp; STACK</text>
    <text x="18" y="64" class="sub">{safe_langs}</text>
    <text x="18" y="88" class="lbl" fill="#38BDF8">10+ Years Experience • Azure CAF • Terraform • DevSecOps</text>
  </g>
</svg>
"""


def build_repos_section(
    repos: list[dict[str, Any]],
    profile_repo_full_name: str,
    limit: int = 6,
) -> str:
    """Build a markdown table of top/recently updated owned repositories."""
    candidates = [
        r
        for r in repos
        if not r.get("fork", False)
        and not r.get("archived", False)
        and r.get("full_name", "").lower() != profile_repo_full_name.lower()
    ]
    if not candidates:
        return (
            "_Public repositories outside this profile repo will appear here "
            "automatically as they are published._"
        )

    candidates.sort(
        key=lambda r: (
            int(r.get("stargazers_count", 0)),
            r.get("pushed_at") or r.get("updated_at") or "",
        ),
        reverse=True,
    )
    selected = candidates[:limit]

    lines = [
        "| Repository | Description | Language | Stars | Updated |",
        "| :--- | :--- | :--- | :-: | :--- |",
    ]
    for repo in selected:
        name = repo["name"]
        url = repo["html_url"]
        desc = (repo.get("description") or "No description provided.").replace("|", "\\|").strip()
        if len(desc) > 90:
            desc = f"{desc[:87]}..."
        lang = repo.get("language") or "—"
        stars = int(repo.get("stargazers_count", 0))
        updated = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]
        lines.append(f"| [{name}]({url}) | {desc} | `{lang}` | ⭐ {stars} | `{updated}` |")
    return "\n".join(lines)


def format_event(event: dict[str, Any]) -> str | None:
    """Format a GitHub public event into a concise markdown bullet."""
    etype = event.get("type", "")
    repo_name = (event.get("repo") or {}).get("name", "")
    repo_link = f"[{repo_name}](https://github.com/{repo_name})"
    date_str = (event.get("created_at") or "")[:10]
    payload = event.get("payload") or {}

    if etype == "PushEvent":
        commits = len(payload.get("commits") or [])
        branch = (payload.get("ref") or "").replace("refs/heads/", "") or "main"
        noun = "commit" if commits == 1 else "commits"
        label = f"Pushed {commits} {noun} to `{branch}` in" if commits else f"Pushed updates to `{branch}` in"
        return f"- `{date_str}` — {label} {repo_link}"
    if etype == "PullRequestEvent":
        action = payload.get("action", "updated")
        pr = payload.get("pull_request") or {}
        number = pr.get("number")
        pr_url = pr.get("html_url")
        pr_ref = f"[#{number}]({pr_url})" if number and pr_url else "PR"
        return f"- `{date_str}` — {action.capitalize()} pull request {pr_ref} in {repo_link}"
    if etype == "IssuesEvent":
        action = payload.get("action", "updated")
        issue = payload.get("issue") or {}
        number = issue.get("number")
        issue_url = issue.get("html_url")
        issue_ref = f"[#{number}]({issue_url})" if number and issue_url else "issue"
        return f"- `{date_str}` — {action.capitalize()} issue {issue_ref} in {repo_link}"
    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "repository")
        ref = payload.get("ref")
        detail = f"`{ref}` ({ref_type})" if ref else ref_type
        return f"- `{date_str}` — Created {detail} in {repo_link}"
    if etype == "ReleaseEvent":
        release = payload.get("release") or {}
        tag = release.get("tag_name", "release")
        return f"- `{date_str}` — Published release `{tag}` in {repo_link}"
    if etype == "WatchEvent":
        return f"- `{date_str}` — Starred {repo_link}"
    if etype == "ForkEvent":
        return f"- `{date_str}` — Forked {repo_link}"
    return None


def build_activity_section(events: list[dict[str, Any]], limit: int = 5) -> str:
    """Build a markdown bullet list of recent public GitHub events."""
    items: list[str] = []
    for event in events:
        formatted = format_event(event)
        if formatted:
            items.append(formatted)
        if len(items) >= limit:
            break

    if not items:
        return "_No recent public GitHub activity found._"
    return "\n".join(items)


def update_readme(
    readme_path: Path,
    username: str,
    repo_full_name: str,
    token: str | None,
    dry_run: bool = False,
) -> bool:
    """Fetch live GitHub data and update README.md sections. Return True if changed."""
    original = readme_path.read_text(encoding="utf-8")
    errors = validate_readme_markers(original)
    if errors:
        raise ValueError("; ".join(errors))

    user = github_get(f"/users/{username}", token=token)
    repos = github_get(
        f"/users/{username}/repos?sort=updated&per_page=100&type=owner",
        token=token,
    )
    events = github_get(
        f"/users/{username}/events/public?per_page=30",
        token=token,
    )
    output_branch = github_get(
        f"/repos/{repo_full_name}/branches/output",
        token=token,
        allow_404=True,
    )

    now_utc = datetime.now(timezone.utc)
    updated = replace_section(
        original,
        "snake",
        build_snake_section(repo_full_name, output_branch is not None),
    )
    updated = replace_section(
        updated,
        "stats",
        build_stats_section(user, repos, now_utc),
    )
    updated = replace_section(
        updated,
        "repos",
        build_repos_section(repos, repo_full_name),
    )
    updated = replace_section(
        updated,
        "activity",
        build_activity_section(events),
    )

    metrics_svg_path = readme_path.resolve().parent / "assets" / "live-metrics.svg"
    new_metrics_svg = build_live_metrics_svg(username, user, repos, now_utc)
    old_metrics_svg = (
        metrics_svg_path.read_text(encoding="utf-8")
        if metrics_svg_path.exists()
        else ""
    )

    readme_changed = updated != original
    svg_changed = new_metrics_svg != old_metrics_svg

    if not readme_changed and not svg_changed:
        print("README.md and live-metrics.svg are already up to date.")
        return False

    if dry_run:
        print("Dry-run: profile artifacts would be updated.")
        return True

    if readme_changed:
        readme_path.write_text(updated, encoding="utf-8", newline="\n")
    if svg_changed:
        metrics_svg_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_svg_path.write_text(new_metrics_svg, encoding="utf-8", newline="\n")
    print("Profile README.md and live-metrics.svg updated successfully.")
    return True


def run_check(readme_path: Path) -> int:
    """Run CI hygiene checks on README markers and repository files."""
    content = readme_path.read_text(encoding="utf-8")
    errors = validate_readme_markers(content)

    repo_root = readme_path.resolve().parent
    candidate_files = [readme_path]
    github_dir = repo_root / ".github"
    if github_dir.exists():
        candidate_files.extend(
            p
            for p in github_dir.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    errors.extend(scan_for_secrets(candidate_files))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print("Profile CI check passed: all markers valid and no secrets detected.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update or validate GitHub profile README.")
    parser.add_argument("--readme", default="README.md", help="Path to README.md")
    parser.add_argument(
        "--username",
        default=os.environ.get("GITHUB_REPOSITORY_OWNER", "swthakare0126"),
        help="GitHub username",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Full repository name (owner/repo)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write README.md")
    parser.add_argument("--check", action="store_true", help="Validate markers and secrets only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    readme_path = Path(args.readme)
    if args.check:
        return run_check(readme_path)

    repo_full_name = args.repo or f"{args.username}/{args.username}"
    token = os.environ.get("GITHUB_TOKEN") or None
    update_readme(
        readme_path=readme_path,
        username=args.username,
        repo_full_name=repo_full_name,
        token=token,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
