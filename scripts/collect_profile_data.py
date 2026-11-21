#!/usr/bin/env python3
"""Collect live GitHub repository stars and upstream PR data into profile-data.json."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "profile-data.json"
API_BASE = "https://api.github.com"


def _resolve_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _api_get(path_or_url: str, token: str | None) -> Any:
    url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RytterMohn-profile-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search_prs(query: str, token: str | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        params = urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": 100, "page": page}
        )
        data = _api_get(f"/search/issues?{params}", token)
        batch = data.get("items", [])
        if not batch:
            break
        for item in batch:
            repo_url = item.get("repository_url", "")
            repo_full_name = repo_url.split("/repos/", 1)[-1] if "/repos/" in repo_url else ""
            if not repo_full_name:
                continue
            pr_info = item.get("pull_request") or {}
            items.append(
                {
                    "repo": repo_full_name,
                    "number": int(item["number"]),
                    "title": item.get("title", "").strip(),
                    "url": item.get("html_url", ""),
                    "state": item.get("state", ""),
                    "merged_at": pr_info.get("merged_at"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                }
            )
        if len(batch) < 100:
            break
        page += 1
    return items


def _fetch_user_repos(username: str, token: str | None) -> dict[str, dict[str, Any]]:
    repos: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        batch = _api_get(f"/users/{username}/repos?type=owner&per_page=100&page={page}", token)
        if not batch:
            break
        for repo in batch:
            if repo.get("fork") or repo.get("private"):
                continue
            repos[repo["name"]] = {
                "stars": int(repo.get("stargazers_count", 0)),
                "language": repo.get("language") or "",
                "description": (repo.get("description") or "").strip(),
                "url": repo.get("html_url", ""),
            }
        if len(batch) < 100:
            break
        page += 1
    return repos


def _fetch_repo_metadata(repo_full_name: str, token: str | None) -> dict[str, Any]:
    data = _api_get(f"/repos/{repo_full_name}", token)
    return {
        "stars": int(data.get("stargazers_count", 0)),
        "url": data.get("html_url", f"https://github.com/{repo_full_name}"),
        "description": (data.get("description") or "").strip(),
    }


def main() -> None:
    profile = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    username = profile["username"]
    token = _resolve_token()

    user_repos = _fetch_user_repos(username, token)
    merged_prs = _search_prs(f"author:{username} is:pr is:merged -user:{username}", token)
    open_prs = _search_prs(f"author:{username} is:pr is:open -user:{username}", token)

    upstream_names: set[str] = set(profile.get("focus_repos", []))
    for pr in [*merged_prs, *open_prs]:
        upstream_names.add(pr["repo"])

    existing_upstream = profile.get("snapshot", {}).get("upstream_repos", {})
    upstream_repos: dict[str, dict[str, Any]] = {}
    for repo_name in sorted(upstream_names):
        try:
            upstream_repos[repo_name] = _fetch_repo_metadata(repo_name, token)
        except urllib.error.URLError:
            if repo_name in existing_upstream:
                upstream_repos[repo_name] = existing_upstream[repo_name]

    def _pr_sort_key(pr: dict[str, Any]) -> tuple[int, str, int]:
        stars = upstream_repos.get(pr["repo"], {}).get("stars", 0)
        return (-stars, pr["repo"].lower(), -pr["number"])

    merged_prs.sort(key=_pr_sort_key)
    open_prs.sort(key=_pr_sort_key)

    new_payload = {
        "user_repos": dict(sorted(user_repos.items(), key=lambda kv: (-kv[1]["stars"], kv[0].lower()))),
        "upstream_repos": upstream_repos,
        "merged_prs": merged_prs,
        "open_prs": open_prs,
    }
    old_snapshot = profile.get("snapshot", {})
    old_payload = {
        "user_repos": old_snapshot.get("user_repos", {}),
        "upstream_repos": old_snapshot.get("upstream_repos", {}),
        "merged_prs": old_snapshot.get("merged_prs", []),
        "open_prs": old_snapshot.get("open_prs", []),
    }
    updated_at = (
        old_snapshot.get("updated_at", "")
        if new_payload == old_payload and old_snapshot.get("updated_at")
        else dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    profile["snapshot"] = {"updated_at": updated_at, **new_payload}

    DATA_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Collected {len(user_repos)} user repos, {len(merged_prs)} merged PRs, "
        f"{len(open_prs)} open PRs across {len(upstream_repos)} upstream repos."
    )


if __name__ == "__main__":
    main()
