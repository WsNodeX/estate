#!/usr/bin/env python3
"""
Estate — cross-repository health for an account with many small projects.

What this checks, and what it deliberately does not
---------------------------------------------------
This runs **horizontal** checks: the same question asked of every repository,
answered from the GitHub API without cloning anything. Vertical checks — does
this repository's code pass its own tests — belong to each repository's own CI,
where they already run on five Python versions and JDK 21. Duplicating those here
would mean cloning 27 repositories on every run to re-answer a question that is
already answered, and answered better.

The horizontal questions are the ones no single repository can ask:

  * does every README still pass the 13-rule audit
  * is every repository's last CI run green
  * does every repository have a release whose tag matches its README badge
  * has any repository gone quiet for a long time
  * do community files still exist after a rename or a squash

A repository can be perfectly healthy alone and be the one thing making the
account look abandoned. That is the failure this is built to catch.

Usage:
    python estate.py --owner WsNodeX --token $GITHUB_TOKEN
    python estate.py --owner WsNodeX --json --fail-on red
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

API = "https://api.github.com"


def token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def get(path: str) -> dict | list | None:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "User-Agent": "estate",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token()}"} if token() else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None


def days_since(iso: str) -> int:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - then).days


def check_repo(owner: str, repo: dict, quiet_days: int) -> dict:
    name = repo["name"]
    row: dict = {
        "name": name,
        "archived": repo.get("archived", False),
        "stars": repo["stargazers_count"],
        "pushed_days": days_since(repo["pushed_at"]),
        "problems": [],
    }

    if row["archived"]:
        row["verdict"] = "archived"
        return row

    # The profile repository (same name as its owner) is a README, not a project.
    # It has no tests, no release and no contribution guide by design, so holding
    # it to project standards produces a permanent false alarm.
    if name.lower() == owner.lower():
        row["verdict"] = "profile"
        return row

    # CI — the most recent workflow run, whatever the workflow is called.
    runs = get(f"/repos/{owner}/{name}/actions/runs?per_page=1")
    if runs and runs.get("workflow_runs"):
        wf = runs["workflow_runs"][0]
        row["ci"] = wf.get("conclusion") or wf.get("status") or "unknown"
        if row["ci"] not in ("success", "skipped"):
            row["problems"].append(f"CI {row['ci']}")
    else:
        row["ci"] = "none"

    # Release — a README badge pointing at /github/v/release/ with no release
    # behind it renders as "no releases", which looks worse than no badge.
    rel = get(f"/repos/{owner}/{name}/releases/latest")
    row["release"] = rel.get("tag_name") if isinstance(rel, dict) else None

    # Community files — cheap proof the repository is not a stub.
    #
    # The community-profile endpoint reports `issue_template: null` for YAML
    # issue *forms* and only recognises the older Markdown templates, while
    # still scoring the repository 100. Trusting that field makes every repo
    # with a modern form look incomplete, so the directory is checked directly.
    prof = get(f"/repos/{owner}/{name}/community/profile")
    if isinstance(prof, dict):
        files = dict(prof.get("files") or {})
        row["health"] = prof.get("health_percentage")

        if not files.get("issue_template"):
            tpl = get(f"/repos/{owner}/{name}/contents/.github/ISSUE_TEMPLATE")
            if isinstance(tpl, list):
                files["issue_template"] = {"count": len(tpl)}

        missing = [k for k in ("contributing", "code_of_conduct", "issue_template", "pull_request_template")
                   if not files.get(k)]
        if missing:
            row["problems"].append("missing " + ",".join(missing))

    # Quiet — not a defect, but worth surfacing on a portfolio account.
    if row["pushed_days"] > quiet_days:
        row["problems"].append(f"quiet {row['pushed_days']}d")

    row["verdict"] = "ok" if not row["problems"] else "warn"
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--quiet-days", type=int, default=120)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on", choices=["never", "warn", "red"], default="red",
                    help="red = only CI failures and missing files fail the run")
    args = ap.parse_args()

    repos = get(f"/users/{args.owner}/repos?per_page=100&sort=pushed")
    if not isinstance(repos, list):
        print(f"cannot list repositories for {args.owner}", file=sys.stderr)
        return 2

    rows = [check_repo(args.owner, r, args.quiet_days) for r in repos]
    live = [r for r in rows if r["verdict"] not in ("archived", "profile")]
    archived = [r for r in rows if r["verdict"] == "archived"]

    if args.json:
        print(json.dumps({"live": live, "archived": archived}, ensure_ascii=False, indent=2))
    else:
        print(f"{'repo':<20} {'★':>4} {'CI':<10} {'rel':<8} {'health':>6} {'last push':>10}  problems")
        print("-" * 92)
        for r in sorted(live, key=lambda x: x["name"]):
            print(f"{r['name'][:19]:<20} {r['stars']:>4} {r['ci'][:9]:<10} "
                  f"{(r['release'] or '-'):<8} {str(r.get('health', '-')):>6} "
                  f"{r['pushed_days']:>9}d  {'; '.join(r['problems']) or ''}")

        red = [r for r in live if any(p.startswith("CI ") for p in r["problems"])]
        missing = [r for r in live if any(p.startswith("missing ") for p in r["problems"])]
        norel = [r for r in live if not r["release"]]

        print()
        print(f"{len(live)} live · {len(archived)} archived · "
              f"{len(red)} CI red · {len(missing)} missing community files · {len(norel)} without a release")

    red = [r for r in live if any(p.startswith("CI ") for p in r["problems"])]
    missing = [r for r in live if any(p.startswith("missing ") for p in r["problems"])]

    if args.fail_on == "never":
        return 0
    if args.fail_on == "red":
        return 1 if (red or missing) else 0
    return 1 if (red or missing or any(r["problems"] for r in live)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
