"""Pre-commit check: No sync HTTP libraries in src/.

All external HTTP calls must go through httpx async.
Forbidden imports in src/**/*.py: requests, urllib, urllib3, http.client.

Excluded: notebook/ (server-side requests allowed), tests/ (no blanket ban).
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FORBIDDEN_MODULES = frozenset({"requests", "urllib", "urllib3", "http"})
FORBIDDEN_FROM_MODULES = frozenset({"requests", "urllib", "urllib3", "http.client"})


def _is_excluded(file_path: Path) -> bool:
    parts = set(file_path.parts)
    return bool(parts & {"notebook", "tests"})


class SyncHTTPChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top_level = alias.name.split(".")[0]
            if top_level in FORBIDDEN_MODULES:
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Sync HTTP import '{alias.name}' is forbidden in src/ — use httpx async instead",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        top_level = module.split(".")[0]
        if top_level in FORBIDDEN_MODULES or module in FORBIDDEN_FROM_MODULES:
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    f"Sync HTTP import from '{module}' is forbidden in src/ — use httpx async instead",
                )
            )
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    if _is_excluded(file_path):
        return []
    checker = SyncHTTPChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    src_dir = Path("src")
    if not src_dir.exists():
        print("src/ directory not found")
        return 1
    files = iter_python_files(src_dir)
    return run_checker(check_file, files, "No sync HTTP (requests/urllib) in src/")


if __name__ == "__main__":
    sys.exit(main())
