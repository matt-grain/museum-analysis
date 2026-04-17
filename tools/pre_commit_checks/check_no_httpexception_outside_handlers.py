"""Pre-commit check: HTTPException must stay in the HTTP layer.

Services, workflows, clients, and repositories must raise domain exceptions.
Routers MAY raise HTTPException for HTTP-layer concerns (auth gates, 401s
before the domain is touched) — CLAUDE.md §Layered architecture allows this.
main.py and exception_handlers.py are also allowlisted because they register
and handle HTTPException.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

ALLOWLISTED_SUFFIXES = ("main.py", "exception_handlers.py")


def _is_allowlisted(file_path: Path) -> bool:
    # HTTP-layer files can freely use HTTPException.
    if file_path.name in ALLOWLISTED_SUFFIXES:
        return True
    # Router files are part of the HTTP layer — they can use HTTPException
    # for auth gates and input validation before the domain is reached.
    return "routers" in file_path.parts


class HTTPExceptionChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module in ("fastapi", "fastapi.exceptions"):
            for alias in node.names:
                if alias.name == "HTTPException":
                    self.violations.append(
                        Violation(
                            self.file_path,
                            node.lineno,
                            "HTTPException is only allowed in main.py / exception_handlers.py"
                            " — raise a domain exception instead",
                        )
                    )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "fastapi":
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        "HTTPException is only allowed in main.py / exception_handlers.py"
                        " — raise a domain exception instead",
                    )
                )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is not None:
            exc = node.exc
            name = None
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            elif isinstance(exc, ast.Name):
                name = exc.id
            elif isinstance(exc, ast.Call) and isinstance(exc.func, ast.Attribute):
                name = exc.func.attr
            if name == "HTTPException":
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        "HTTPException is only allowed in main.py / exception_handlers.py"
                        " — raise a domain exception instead",
                    )
                )
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    if _is_allowlisted(file_path):
        return []
    checker = HTTPExceptionChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    src_dir = Path("src")
    if not src_dir.exists():
        print("src/ directory not found")
        return 1
    files = iter_python_files(src_dir)
    return run_checker(
        check_file,
        files,
        "HTTPException only in main.py / exception_handlers.py",
    )


if __name__ == "__main__":
    sys.exit(main())
