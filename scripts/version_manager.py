#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "backend" / "app" / "__init__.py"
VERSION_RE = re.compile(r'(__version__\s*=\s*")([^"]+)(")')
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?$")


def current_version() -> str:
    if not VERSION_FILE.is_file():
        sys.exit(f"Error: version file not found at {VERSION_FILE}")
    match = VERSION_RE.search(VERSION_FILE.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"Error: could not find __version__ in {VERSION_FILE}")
    return match.group(2)


def parse_version(version: str) -> tuple[int, int, int, str | None]:
    match = SEMVER_RE.match(version)
    if not match:
        raise ValueError(f"Invalid semantic version: '{version}'. Must match X.Y.Z or X.Y.Z-suffix")
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), suffix


def format_version(major: int, minor: int, patch: int, suffix: str | None = None) -> str:
    if suffix is not None:
        return f"{major}.{minor}.{patch}-{suffix}"
    return f"{major}.{minor}.{patch}"


def bump_version(current: str, bump_type: str) -> str:
    major, minor, patch, suffix = parse_version(current)
    if bump_type == "major":
        return format_version(major + 1, 0, 0)
    if bump_type == "minor":
        return format_version(major, minor + 1, 0)
    if bump_type == "patch":
        if suffix is not None:
            return format_version(major, minor, patch)
        return format_version(major, minor, patch + 1)
    if bump_type == "rc":
        if suffix and suffix.startswith("rc."):
            try:
                rc_num = int(suffix.split(".")[1])
            except (ValueError, IndexError):
                rc_num = 0
            return format_version(major, minor, patch, f"rc.{rc_num + 1}")
        return format_version(major, minor, patch + 1, "rc.1")
    raise ValueError(f"Unknown bump type: {bump_type}")


def set_version(new_version: str) -> None:
    parse_version(new_version)
    content = VERSION_FILE.read_text(encoding="utf-8")
    updated, count = VERSION_RE.subn(rf'\g<1>{new_version}\g<3>', content)
    if count == 0:
        sys.exit(f"Error: could not rewrite __version__ in {VERSION_FILE}")
    VERSION_FILE.write_text(updated, encoding="utf-8")


def run(args: list[str], check: bool = True, strip: bool = True) -> str:
    result = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip() if strip else result.stdout


def git_release(version: str, push: bool) -> None:
    run(["git", "rev-parse", "--is-inside-work-tree"])
    rel_version_file = VERSION_FILE.relative_to(ROOT).as_posix()
    dirty = [
        line[3:]
        for line in run(["git", "status", "--porcelain"], strip=False).splitlines()
        if line.strip()
    ]
    unexpected = [p for p in dirty if p != rel_version_file]
    if unexpected:
        sys.exit(
            "Error: refusing to release with unrelated dirty files:\n  "
            + "\n  ".join(unexpected)
            + "\nCommit or stash them first."
        )

    tag = f"v{version}"
    staged = False
    if rel_version_file in dirty:
        run(["git", "add", rel_version_file])
        staged = True
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, capture_output=True)
    if diff.returncode != 0:
        run(["git", "commit", "-m", f"chore(release): {version}"])
        print(f"  committed: chore(release): {version}")
    else:
        print("  nothing to commit")
    staged_or_committed = staged

    tag_exists = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}"], cwd=ROOT, capture_output=True
    ).returncode == 0
    if not tag_exists:
        run(["git", "tag", "-a", tag, "-m", f"Release {version}"])
        print(f"  tagged: {tag}")
    else:
        print(f"  tag {tag} already exists, skipping")

    if not push:
        if not staged_or_committed and tag_exists:
            print("Nothing to do: version already committed and tagged.")
        else:
            print("Local only — run with --push (or `release --push`) to publish and trigger CI.")
        return

    remotes = [r for r in run(["git", "remote"]).splitlines() if r.strip()]
    if not remotes:
        print("No git remotes configured; skipping push.")
        return
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    for remote in remotes:
        run(["git", "push", remote, branch])
        run(["git", "push", remote, tag])
        print(f"  pushed branch + {tag} to {remote}")
    print(f"Release {version} published — the Release workflow will build the installers.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Study Assistant version manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/version_manager.py show
  python3 scripts/version_manager.py bump patch
  python3 scripts/version_manager.py bump rc --git
  python3 scripts/version_manager.py set 0.2.0 --git --push
  python3 scripts/version_manager.py release --push
""",
    )
    git_parser = argparse.ArgumentParser(add_help=False)
    git_parser.add_argument("--git", "-g", action="store_true", help="commit the bump and create the vX.Y.Z tag")
    git_parser.add_argument("--push", "-p", action="store_true", help="push the commit and tag (implies --git); triggers the Release workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show", help="print the current version")
    set_parser = subparsers.add_parser("set", parents=[git_parser], help="set an explicit version (X.Y.Z or X.Y.Z-suffix)")
    set_parser.add_argument("version", type=str)
    bump_parser = subparsers.add_parser("bump", parents=[git_parser], help="bump major/minor/patch/rc")
    bump_parser.add_argument("type", choices=["major", "minor", "patch", "rc"])
    subparsers.add_parser("release", parents=[git_parser], help="commit/tag/push the version already recorded in the source")
    args = parser.parse_args()

    version = current_version()
    if args.command == "show":
        print(version)
        return
    try:
        if args.command == "set":
            set_version(args.version)
            print(f"version: {version} -> {args.version}")
            new_version = args.version
        elif args.command == "bump":
            new_version = bump_version(version, args.type)
            set_version(new_version)
            print(f"version: {version} -> {new_version}")
        else:
            new_version = version
            print(f"releasing current version: {version}")
        if args.git or args.push:
            git_release(new_version, push=args.push)
    except ValueError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
