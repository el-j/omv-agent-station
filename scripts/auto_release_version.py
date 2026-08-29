#!/usr/bin/env python3
"""
Auto-detect SemVer release version for OpenMediaVault Agent Station.
Analyzes Git history, debian/control, merged branch names, and PR titles
to determine the next release version (major, minor, or patch).
"""

import argparse
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _resolve_git_executable() -> str:
    """Resolve an absolute git executable path or fail fast."""
    git_exe = shutil.which("git")
    if not git_exe:
        raise OSError("git executable not found")
    return git_exe


def get_latest_git_tag() -> str:
    """Fetch and return the highest existing SemVer tag (e.g. 'v0.1.0')."""
    git_exe = _resolve_git_executable()
    try:
        res = subprocess.run(
            [git_exe, "tag", "-l", "v*"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            check=True
        )  # nosec B603
        tags = [t.strip() for t in res.stdout.splitlines() if t.strip()]
        semver_tags = []
        for t in tags:
            m = re.match(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)$", t)
            if m:
                semver_tags.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), t))
        if semver_tags:
            semver_tags.sort(key=lambda x: (x[0], x[1], x[2]))
            return semver_tags[-1][3]
    except (subprocess.CalledProcessError, OSError):
        # Fall back to the repository baseline when git metadata is unavailable.
        return "v0.0.0"
    return "v0.0.0"


def parse_semver(v_str: str):
    """Parse '0.1.0' or 'v0.1.0' into (major, minor, patch)."""
    m = re.match(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)", v_str.strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return 0, 0, 0


def get_control_file_version() -> str:
    """Read version from debian/control."""
    control_path = ROOT_DIR / "openmediavault-agent-station" / "debian" / "control"
    if control_path.exists():
        for line in control_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Version:"):
                raw = line.split(":", 1)[1].strip()
                m = re.match(r"^v?([0-9]+\.[0-9]+\.[0-9]+)", raw)
                if m:
                    return m.group(1)
    return "0.1.0"


def determine_release_version(
    branch: str = "",
    pr_title: str = "",
    commit_msg: str = "",
    override: str = ""
) -> str:
    if override:
        m = re.match(r"^v?([0-9]+\.[0-9]+\.[0-9]+)", override)
        if m:
            return m.group(1)

    latest_tag = get_latest_git_tag()
    latest_maj, latest_min, latest_pat = parse_semver(latest_tag)
    control_ver = get_control_file_version()
    ctrl_maj, ctrl_min, ctrl_pat = parse_semver(control_ver)

    # 1. If debian/control specifies a version higher than latest tag, prioritize it
    if (ctrl_maj, ctrl_min, ctrl_pat) > (latest_maj, latest_min, latest_pat):
        return f"{ctrl_maj}.{ctrl_min}.{ctrl_pat}"

    # 2. Check for explicit release branch or PR title (e.g. 'release/v1.0.0', 'Release v0.1.0')
    search_text = f"{branch} {pr_title} {commit_msg}"
    rel_match = re.search(r"(?:release/|Release\s+)v?([0-9]+\.[0-9]+\.[0-9]+)", search_text, re.IGNORECASE)
    if rel_match:
        return rel_match.group(1)

    # 3. Breaking / Major bump detection
    if (
        "breaking" in search_text.lower()
        or "[major]" in search_text.lower()
        or branch.startswith("major/")
        or "feat!:" in search_text
        or "fix!:" in search_text
    ):
        return f"{latest_maj + 1}.0.0"

    # 4. Patch bump detection: hotfix/*, fix/*, or PR title starting with fix: / [patch]
    if (
        branch.startswith("hotfix/")
        or branch.startswith("fix/")
        or "[patch]" in search_text.lower()
        or "hotfix" in search_text.lower()
    ):
        return f"{latest_maj}.{latest_min}.{latest_pat + 1}"

    # 5. Default from develop or feature/*: Minor bump
    return f"{latest_maj}.{latest_min + 1}.0"


def main():
    parser = argparse.ArgumentParser(description="Auto-detect next release version")
    parser.add_argument("--branch", default=os.getenv("MERGED_BRANCH", ""))
    parser.add_argument("--pr-title", default=os.getenv("PR_TITLE", ""))
    parser.add_argument("--commit-msg", default=os.getenv("COMMIT_MESSAGE", ""))
    parser.add_argument("--override", default=os.getenv("OVERRIDE_VERSION", ""))
    parser.add_argument("--tag", action="store_true", help="Prefix output with 'v'")
    args = parser.parse_args()

    version = determine_release_version(
        branch=args.branch,
        pr_title=args.pr_title,
        commit_msg=args.commit_msg,
        override=args.override
    )

    if args.tag:
        print(f"v{version}")
    else:
        print(version)


if __name__ == "__main__":
    main()
