#!/usr/bin/env python3
"""
Build dist/operators-edge from source files.

This is a deterministic, read-write sync from source-of-truth files
into the dist folder. It does not delete extraneous dist files.
Use --dry-run to preview changes.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


INCLUDE_GLOBS = [
    ".claude/commands/*.md",
    ".claude/hooks/*.py",
    "CLAUDE.md",
    "docs/schema-v2.md",
    "docs/yolo-action-schema.md",
    "templates/active_context_v2.yaml",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_sources(repo_root: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    sources: list[tuple[Path, Path]] = []
    missing_patterns: list[str] = []
    for pattern in INCLUDE_GLOBS:
        matches = sorted([p for p in repo_root.glob(pattern) if p.is_file()])
        if not matches:
            missing_patterns.append(pattern)
            continue
        for src in matches:
            rel = src.relative_to(repo_root)
            sources.append((src, rel))
    # stable ordering
    sources.sort(key=lambda item: str(item[1]))
    return sources, missing_patterns


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/operators-edge from source files.")
    parser.add_argument("--root", default=None, help="Repo root (defaults to script parent).")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without copying.")
    parser.add_argument("--verbose", action="store_true", help="Print progress while processing files.")
    parser.add_argument("--check", action="store_true", help="Check for drift without copying. Non-zero exit on mismatch.")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    dist_root = repo_root / "dist" / "operators-edge"

    sources, missing = collect_sources(repo_root)
    if not sources:
        print("No source files matched include patterns. Nothing to do.")
        if missing:
            print("Missing patterns:")
            for pat in missing:
                print(f"  - {pat}")
        return 1

    created: list[Path] = []
    updated: list[Path] = []
    unchanged: list[Path] = []

    total = len(sources)
    for idx, (src, rel) in enumerate(sources, start=1):
        if args.verbose:
            print(f"[{idx}/{total}] {rel}", flush=True)
        dest = dist_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if src.stat().st_size == dest.stat().st_size and sha256(src) == sha256(dest):
                unchanged.append(rel)
                continue
            updated.append(rel)
        else:
            created.append(rel)

        if not args.dry_run and not args.check:
            shutil.copy2(src, dest)

    if args.check:
        header = "CHECK"
    else:
        header = "DRY RUN" if args.dry_run else "BUILD"
    print(f"{header}: {len(sources)} source files processed")
    print(f"Created: {len(created)} | Updated: {len(updated)} | Unchanged: {len(unchanged)}")

    def print_list(label: str, items: list[Path]) -> None:
        if not items:
            return
        print(f"\n{label}:")
        for rel in items:
            print(f"  - {rel}")

    print_list("Created", created)
    print_list("Updated", updated)

    if missing:
        print("\nWarning: include patterns with no matches:")
        for pat in missing:
            print(f"  - {pat}")

    if args.check and (created or updated or missing):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
