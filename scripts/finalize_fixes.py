#!/usr/bin/env python3
"""
Phase 7 finalization: branch creation (pre), unified diff + test run (post).

Two modes:

  pre   — call BEFORE dispatching fix subagents. Creates a git branch so
          fixes don't land on main. Idempotent: re-uses existing branch
          named `cartographer/fixes-<date>` if it already exists.

  post  — call AFTER all fix subagents return. Aggregates per-fix diffs
          from .cartographer/fix_reports/ into a unified fix_summary.md,
          runs the user-supplied test command if any, and writes a
          status JSON the main agent reads to know whether to keep fixes.

Usage:
    python finalize_fixes.py pre  --project-root . [--branch-name X] [--no-branch]
    python finalize_fixes.py post --project-root . [--test-cmd "pytest -x"] [--output-dir .cartographer]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path


def git(args, cwd, check=True):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), r.stderr.strip()


def in_git_repo(project_root):
    out, _ = git(["rev-parse", "--is-inside-work-tree"], cwd=project_root, check=False)
    return out == "true"


def current_branch(project_root):
    out, _ = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=project_root, check=False)
    return out


def branch_exists(project_root, name):
    out, _ = git(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                 cwd=project_root, check=False)
    return bool(out)


def has_uncommitted_changes(project_root):
    out, _ = git(["status", "--porcelain"], cwd=project_root, check=False)
    return bool(out)


def cmd_pre(args):
    root = Path(args.project_root).resolve()
    if not in_git_repo(root):
        print("Not a git repo — skipping branch creation.", file=sys.stderr)
        return 0

    if args.no_branch:
        print(f"--no-branch set; staying on {current_branch(root)}", file=sys.stderr)
        return 0

    branch = args.branch_name or f"cartographer/fixes-{date.today().isoformat()}"
    cur = current_branch(root)

    if cur == branch:
        print(f"Already on {branch}", file=sys.stderr)
        return 0

    if has_uncommitted_changes(root):
        print(f"Uncommitted changes detected on {cur}.", file=sys.stderr)
        print("Refusing to create branch — commit/stash first, or pass --force "
              "to switch anyway (changes follow you to the new branch).",
              file=sys.stderr)
        if not args.force:
            return 1

    if branch_exists(root, branch):
        out, err = git(["checkout", branch], cwd=root, check=False)
        if err and "Switched" not in err:
            print(f"Couldn't checkout {branch}: {err}", file=sys.stderr)
            return 1
        print(f"Checked out existing branch {branch}", file=sys.stderr)
    else:
        out, err = git(["checkout", "-b", branch], cwd=root, check=False)
        if "Switched" not in err and err:
            print(f"Couldn't create {branch}: {err}", file=sys.stderr)
            return 1
        print(f"Created and checked out {branch}", file=sys.stderr)

    return 0


def parse_fix_report(path: Path):
    """Pull status, files touched, diff blocks from a fix report .md."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\*\*Status\*\*:\s*([\w-]+)", text)
    status = m.group(1) if m else "unknown"
    m = re.search(r"\*\*Backlog item\*\*:\s*(.+)", text)
    summary = m.group(1).strip() if m else path.stem
    files = re.findall(r"\*\*Files touched\*\*:?\s*\n([\s\S]*?)(?=\n##\s|$)", text)
    files_section = files[0] if files else ""
    file_paths = re.findall(r"^-\s+`([^`]+)`", files_section, flags=re.M)
    diff_section = re.search(r"##\s+Diff\s*\n([\s\S]*?)(?=\n##\s|$)", text)
    diff_text = diff_section.group(1).strip() if diff_section else ""
    verif = re.search(r"##\s+Verification\s*\n([\s\S]*?)(?=\n##\s|$)", text)
    verif_text = verif.group(1).strip() if verif else ""
    concerns = re.search(r"##\s+Concerns\s*\n([\s\S]*?)$", text)
    concerns_text = concerns.group(1).strip() if concerns else ""
    return {
        "id": path.stem,
        "status": status,
        "summary": summary,
        "files": file_paths,
        "diff": diff_text,
        "verification": verif_text,
        "concerns": concerns_text,
    }


def cmd_post(args):
    root = Path(args.project_root).resolve()
    out_dir = Path(args.output_dir).resolve()
    fix_reports_dir = out_dir / "fix_reports"
    if not fix_reports_dir.exists():
        print(f"No fix_reports/ at {fix_reports_dir} — nothing to finalize.",
              file=sys.stderr)
        return 1

    fixes = []
    for rp in sorted(fix_reports_dir.glob("*.md")):
        fixes.append(parse_fix_report(rp))

    # group by status
    applied = [f for f in fixes if f["status"].lower() == "applied"]
    skipped = [f for f in fixes if f["status"].lower() == "skipped"]
    failed = [f for f in fixes if f["status"].lower() not in {"applied", "skipped"}]

    # collect unified git diff for tracked files
    all_touched_files = sorted({f for fix in applied for f in fix["files"]})
    git_diff_text = ""
    if in_git_repo(root) and all_touched_files:
        out, _ = git(["diff", "--", *all_touched_files], cwd=root, check=False)
        git_diff_text = out or ""

    # run tests if commanded
    test_result = None
    if args.test_cmd:
        print(f"\nRunning tests: {args.test_cmd}", file=sys.stderr)
        t0 = time.time()
        r = subprocess.run(args.test_cmd, cwd=root, shell=True,
                           capture_output=True, text=True, timeout=args.test_timeout)
        elapsed = time.time() - t0
        test_result = {
            "command": args.test_cmd,
            "returncode": r.returncode,
            "elapsed_seconds": round(elapsed, 1),
            "passed": r.returncode == 0,
            "stdout_tail": (r.stdout or "")[-2000:],
            "stderr_tail": (r.stderr or "")[-2000:],
        }

    # write fix_summary.md
    md = ["# Phase 7 — fix application summary", ""]
    md.append(f"- **Branch**: {current_branch(root) or '(no git)'}")
    md.append(f"- **Applied**: {len(applied)}")
    md.append(f"- **Skipped**: {len(skipped)}")
    md.append(f"- **Failed**: {len(failed)}")
    md.append(f"- **Files touched**: {len(all_touched_files)}")
    if test_result:
        md.append(f"- **Tests**: {'pass' if test_result['passed'] else 'FAIL'} "
                  f"(rc={test_result['returncode']}, {test_result['elapsed_seconds']}s)")
    md.append("")

    if applied:
        md.append("## Applied")
        for f in applied:
            md.append(f"### {f['id']} — {f['summary']}")
            md.append(f"Files: {', '.join('`' + p + '`' for p in f['files'])}")
            if f["concerns"]:
                md.append(f"\n_{f['concerns']}_")
            md.append("")
            if f["diff"]:
                md.append("```")
                md.append(f["diff"][:1500])
                md.append("```")
            md.append("")

    if skipped:
        md.append("## Skipped (bug not where claimed — useful signal)")
        for f in skipped:
            md.append(f"- **{f['id']}**: {f['summary']}")
            if f["concerns"]:
                md.append(f"  - {f['concerns'][:300]}")
        md.append("")

    if failed:
        md.append("## Failed (need attention)")
        for f in failed:
            md.append(f"- **{f['id']}**: status={f['status']} — {f['summary']}")
        md.append("")

    if git_diff_text:
        md.append("## Combined git diff")
        md.append("```diff")
        md.append(git_diff_text[:8000])
        if len(git_diff_text) > 8000:
            md.append(f"\n... (truncated; {len(git_diff_text) - 8000} more chars in repo)")
        md.append("```")

    if test_result:
        md.append("## Test run")
        md.append(f"- Command: `{test_result['command']}`")
        md.append(f"- Result: {'pass' if test_result['passed'] else 'FAIL'} "
                  f"(rc={test_result['returncode']}, "
                  f"{test_result['elapsed_seconds']}s)")
        if test_result["stdout_tail"]:
            md.append("\n### stdout (tail)")
            md.append("```")
            md.append(test_result["stdout_tail"])
            md.append("```")
        if test_result["stderr_tail"]:
            md.append("\n### stderr (tail)")
            md.append("```")
            md.append(test_result["stderr_tail"])
            md.append("```")

    summary_md = out_dir / "fix_summary.md"
    summary_md.write_text("\n".join(md), encoding="utf-8")

    summary_json = out_dir / "fix_summary.json"
    summary_json.write_text(
        json.dumps({
            "applied": [f["id"] for f in applied],
            "skipped": [f["id"] for f in skipped],
            "failed": [f["id"] for f in failed],
            "files_touched": all_touched_files,
            "branch": current_branch(root),
            "test_result": test_result,
        }, indent=2),
        encoding="utf-8",
    )

    print(f"\nWrote {summary_md}", file=sys.stderr)
    print(f"Wrote {summary_json}", file=sys.stderr)
    print(f"\nApplied: {len(applied)}  Skipped: {len(skipped)}  Failed: {len(failed)}",
          file=sys.stderr)
    if test_result:
        verdict = "PASS" if test_result["passed"] else "FAIL"
        print(f"Tests: {verdict}", file=sys.stderr)

    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("pre", help="Run before fix dispatch — create a branch.")
    pre.add_argument("--project-root", required=True)
    pre.add_argument("--branch-name", default=None,
                     help="Default: cartographer/fixes-<YYYY-MM-DD>")
    pre.add_argument("--no-branch", action="store_true",
                     help="Stay on current branch (don't create one).")
    pre.add_argument("--force", action="store_true",
                     help="Switch even with uncommitted changes.")

    post = sub.add_parser("post", help="Run after fix dispatch — aggregate + test.")
    post.add_argument("--project-root", required=True)
    post.add_argument("--output-dir", default=".cartographer")
    post.add_argument("--test-cmd", default=None,
                      help="Shell command to run for verification (e.g. 'pytest -x').")
    post.add_argument("--test-timeout", type=int, default=300,
                      help="Test timeout in seconds (default: 300).")

    args = ap.parse_args()
    if args.cmd == "pre":
        sys.exit(cmd_pre(args))
    else:
        sys.exit(cmd_post(args))


if __name__ == "__main__":
    main()
