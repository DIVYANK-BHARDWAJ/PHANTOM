#!/usr/bin/env python3
"""
Package Submission ZIP
======================
Packages the runnable solution, code, configuration, evaluation reports,
and documentation into code.zip according to AGENTS.md §6.9:
- Includes: code/, evaluation/, docs/, tests/, README.md, problem_statement.md, CLAUDE.md, AGENTS.md
- Strictly excludes: dataset/, __pycache__, .git, virtual environments, scratch files, and nested archives.
"""

import os
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = REPO_ROOT / "code.zip"

EXCLUDED_DIRS = {
    "dataset",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    ".idea",
    "venv",
    ".venv",
    "scratch",
    "phantom_real_world_benchmark"
}

EXCLUDED_FILES = {
    "code.zip",
    "agent-trace.zip",
    "log.txt"
}

def package_submission():
    print(f"=== Packaging Submission ZIP: {ZIP_PATH} ===")
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    included_count = 0
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(REPO_ROOT):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

            for f in files:
                if f in EXCLUDED_FILES or f.endswith((".pyc", ".pyo", ".tmp")):
                    continue
                full_path = Path(root) / f
                rel_path = full_path.relative_to(REPO_ROOT)
                zipf.write(full_path, rel_path)
                included_count += 1

    print(f"Package created successfully with {included_count} files.")
    print(f"ZIP Size: {ZIP_PATH.stat().st_size / (1024 * 1024):.2f} MB")

if __name__ == "__main__":
    package_submission()
