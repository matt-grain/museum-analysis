"""Pre-commit check: routers must not import from sqlalchemy.

Covers the deferred Phase 3 item from REVIEW.md: "routers can't import
sqlalchemy.text". Enforces the same contract that import-linter enforces
for `museums.repositories` / `museums.models` / `museums.clients`, but
for the `sqlalchemy` runtime package — catches regressions where a
router sneaks in a direct `from sqlalchemy import text` or
`from sqlalchemy.ext.asyncio import AsyncSession`.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker


class SqlAlchemyInRoutersChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "sqlalchemy" or alias.name.startswith("sqlalchemy."):
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Router imports `{alias.name}` — DB concerns belong in a service/repository",
                    )
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module == "sqlalchemy" or module.startswith("sqlalchemy."):
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    f"Router imports from `{module}` — DB concerns belong in a service/repository",
                )
            )


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = SqlAlchemyInRoutersChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    routers_dir = Path("src/museums/routers")
    if not routers_dir.exists():
        print("src/museums/routers/ directory not found")
        return 0
    files = iter_python_files(routers_dir)
    return run_checker(check_file, files, "Routers must not import sqlalchemy")


if __name__ == "__main__":
    sys.exit(main())
