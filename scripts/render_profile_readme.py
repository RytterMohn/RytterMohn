#!/usr/bin/env python3
"""Render bilingual GitHub profile README.md from profile-data.json."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "profile-data.json"
README_PATH = ROOT / "README.md"


def _format_stars(stars: int) -> str:
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(stars)


def _format_project_stars(stars: int) -> str:
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    if stars > 0:
        return f"{stars}★"
    return "new"


def _escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _repo_label(repo: str, profile: dict[str, Any]) -> str:
    display = profile.get("repo_display_names", {}).get(repo)
    if display:
        return display
    return repo.split("/")[-1]


def _pr_summary(pr: dict[str, Any], lang: str, profile: dict[str, Any]) -> str:
    key = f"{pr['repo']}#{pr['number']}"
    curated = profile.get("pr_notes", {}).get(key, {})
    note = curated.get(lang) or curated.get("en") or pr.get("title", "")
    return _escape_md_cell(note)


def _categorize_prs(
    prs: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[tuple[dict[str, str], list[dict[str, Any]]]]:
    categories = profile.get("contribution_categories", [])
    repo_to_cat: dict[str, str] = {}
    for cat in categories:
        for repo in cat.get("repos", []):
            repo_to_cat[repo.lower()] = cat["id"]

    grouped: dict[str, list[dict[str, Any]]] = {cat["id"]: [] for cat in categories}
    other: list[dict[str, Any]] = []

    for pr in prs:
        cat_id = repo_to_cat.get(pr["repo"].lower())
        if cat_id is not None:
            grouped[cat_id].append(pr)
        else:
            other.append(pr)

    ordered: list[tuple[dict[str, str], list[dict[str, Any]]]] = []
    for cat in categories:
        if grouped[cat["id"]]:
            ordered.append((cat["title"], grouped[cat["id"]]))
    if other:
        ordered.append(({"en": "Other Open Source", "zh": "其他开源项目"}, other))
    return ordered


def _render_projects_table(profile: dict[str, Any], lang: str) -> list[str]:
    username = profile["username"]
    user_repos = profile.get("snapshot", {}).get("user_repos", {})
    headers = (
        ("Area", "Project", "Stars", "Notes")
        if lang == "en"
        else ("方向", "项目", "Stars", "说明")
    )
    lines = [
        '<table width="100%">',
        "  <thead>",
        "    <tr>",
        f'      <th align="center" width="16%">{headers[0]}</th>',
        f'      <th align="center" width="24%">{headers[1]}</th>',
        f'      <th align="center" width="10%">{headers[2]}</th>',
        f'      <th align="left" width="50%">{headers[3]}</th>',
        "    </tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for project in profile.get("projects", []):
        repo_name = project["repo"]
        meta = user_repos.get(repo_name, {})
        stars = _format_project_stars(int(meta.get("stars", 0)))
        area = html.escape(project["area"][lang]).replace(" ", "&nbsp;")
        notes = html.escape(project["notes"][lang])
        url = f"https://github.com/{username}/{repo_name}"
        lines.extend(
            [
                "    <tr>",
                f'      <td align="center">{area}</td>',
                f'      <td><a href="{url}">{html.escape(repo_name)}</a></td>',
                f'      <td align="center">{stars}</td>',
                f"      <td>{notes}</td>",
                "    </tr>",
            ]
        )
    lines.extend(["  </tbody>", "</table>"])
    return lines


def _render_pr_table(
    prs: list[dict[str, Any]],
    profile: dict[str, Any],
    lang: str,
    *,
    show_status: bool = False,
) -> list[str]:
    upstream_repos = profile.get("snapshot", {}).get("upstream_repos", {})
    if lang == "en":
        cols = "| Project | PR | Summary |" if not show_status else "| Project | PR | Status | Summary |"
        align = "| :---: | :---: | :--- |" if not show_status else "| :---: | :---: | :---: | :--- |"
    else:
        cols = "| 项目 | PR | 修复内容 |" if not show_status else "| 项目 | PR | 状态 | 修复内容 |"
        align = "| :---: | :---: | :--- |" if not show_status else "| :---: | :---: | :---: | :--- |"

    lines = [cols, align]
    for pr in prs:
        repo = pr["repo"]
        stars = int(upstream_repos.get(repo, {}).get("stars", 0))
        label = _repo_label(repo, profile)
        star_suffix = f" ({_format_stars(stars)}★)" if stars > 0 else ""
        repo_link = f"[{label}{star_suffix}](https://github.com/{repo})"
        pr_link = f"[#{pr['number']}]({pr['url']})"
        summary = _pr_summary(pr, lang, profile)
        if show_status:
            status_badge = "Open" if lang == "en" else "审核中"
            lines.append(f"| {repo_link} | {pr_link} | `{status_badge}` | {summary} |")
        else:
            lines.append(f"| {repo_link} | {pr_link} | {summary} |")
    return lines


def _render_section(profile: dict[str, Any], lang: str) -> list[str]:
    snapshot = profile.get("snapshot", {})
    merged_prs: list[dict[str, Any]] = snapshot.get("merged_prs", [])
    open_prs: list[dict[str, Any]] = snapshot.get("open_prs", [])
    user_repos: dict[str, Any] = snapshot.get("user_repos", {})

    badges = " ".join(f"![{b['label']}]({b['url']})" for b in profile.get("badges", []))
    display_name = profile["display_name"]

    merged_repo_names = list(dict.fromkeys(_repo_label(pr["repo"], profile) for pr in merged_prs))
    focus_repo_names = [_repo_label(r, profile) for r in profile.get("focus_repos", [])]

    featured_names = [p["repo"] for p in profile.get("projects", [])[:5]]
    public_count = len([r for r in user_repos if r.lower() != profile["username"].lower()])

    lines: list[str] = []
    if lang == "en":
        lines.append(f"## Hey, I'm {display_name} 👋")
        lines.append("")
        lines.append('<p align="right"><a href="#中文版">切换到中文版 ↓</a></p>')
        lines.append("")
        lines.append(badges)
        lines.append("")
        lines.append(profile["tagline"]["en"])
        lines.append("")
        if merged_repo_names:
            lines.append(
                f"- **{len(merged_prs)} merged upstream PRs** ({', '.join(merged_repo_names)}) "
                f"and **{len(open_prs)} active PRs** under review."
            )
        lines.append(
            f"- Long-term open-source focus: **{', '.join(focus_repo_names)}**."
        )
        lines.append(
            f"- **{public_count} public repositories**, led by {', '.join(featured_names)}."
        )
        lines.append("")
        lines.append("### Projects")
        lines.append("")
        lines.extend(_render_projects_table(profile, "en"))
        lines.append("")
        lines.append("### Open Source Contributions")
        lines.append("")
        if merged_prs:
            for title_map, group_prs in _categorize_prs(merged_prs, profile):
                lines.append(f"#### {title_map['en']}")
                lines.append("")
                lines.extend(_render_pr_table(group_prs, profile, "en"))
                lines.append("")
        if open_prs:
            lines.append("<details open>")
            lines.append(
                f"<summary><strong>Active / Under Review PRs ({len(open_prs)}) — auto-promoted once merged</strong></summary>"
            )
            lines.append("")
            for title_map, group_prs in _categorize_prs(open_prs, profile):
                lines.append(f"#### {title_map['en']}")
                lines.append("")
                lines.extend(_render_pr_table(group_prs, profile, "en", show_status=True))
                lines.append("")
            lines.append("</details>")
            lines.append("")
    else:
        lines.append('<a id="中文版"></a>')
        lines.append("")
        lines.append(f"## 你好，我是 {display_name} 👋")
        lines.append("")
        lines.append(badges)
        lines.append("")
        lines.append(profile["tagline"]["zh"])
        lines.append("")
        if merged_repo_names:
            lines.append(
                f"- 已合并 **{len(merged_prs)} 个上游开源 PR**（{', '.join(merged_repo_names)}），"
                f"另有 **{len(open_prs)} 个 PR** 审核中。"
            )
        lines.append(
            f"- 长期深耕开源方向：**{'、'.join(focus_repo_names)}**。"
        )
        lines.append(
            f"- 共 **{public_count} 个公开自研仓库**，代表项目：{'、'.join(featured_names)}。"
        )
        lines.append("")
        lines.append("### 自研项目")
        lines.append("")
        lines.extend(_render_projects_table(profile, "zh"))
        lines.append("")
        lines.append("### 开源贡献")
        lines.append("")
        if merged_prs:
            for title_map, group_prs in _categorize_prs(merged_prs, profile):
                lines.append(f"#### {title_map['zh']}")
                lines.append("")
                lines.extend(_render_pr_table(group_prs, profile, "zh"))
                lines.append("")
        if open_prs:
            lines.append("<details open>")
            lines.append(
                f"<summary><strong>审核中 / 进行中的 PR（{len(open_prs)} 个，合并后自动升入主表）</strong></summary>"
            )
            lines.append("")
            for title_map, group_prs in _categorize_prs(open_prs, profile):
                lines.append(f"#### {title_map['zh']}")
                lines.append("")
                lines.extend(_render_pr_table(group_prs, profile, "zh", show_status=True))
                lines.append("")
            lines.append("</details>")
            lines.append("")

        contact = profile.get("contact", {})
        lines.append("### 联系方式 / Contact")
        lines.append("")
        if contact.get("github"):
            lines.append(f"- GitHub: [{contact['github']}]({contact['github']})")
        if contact.get("email"):
            lines.append(f"- Email: `{contact['email']}`")
        if contact.get("blog"):
            lines.append(f"- Blog: [{contact['blog']}]({contact['blog']})")
        lines.append("")

    return lines


def main() -> None:
    profile = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    lines = [
        "<!-- AUTO-GENERATED by scripts/render_profile_readme.py. Edit profile-data.json for curated notes. -->",
        "",
    ]
    lines.extend(_render_section(profile, "en"))
    lines.extend(["---", ""])
    lines.extend(_render_section(profile, "zh"))

    updated_at = profile.get("snapshot", {}).get("updated_at")
    if updated_at:
        lines.append(f"<sub>Last synced automatically via GitHub Actions: `{updated_at}`</sub>")
        lines.append("")

    README_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rendered {README_PATH}")


if __name__ == "__main__":
    main()
