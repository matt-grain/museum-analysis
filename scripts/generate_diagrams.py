"""Render every Mermaid .mmd file under docs/diagrams/ to an SVG next to it.

Uses ``npx @mermaid-js/mermaid-cli`` (installed on demand). We keep the
Mermaid source hand-authored under ``docs/diagrams/`` — this script is
purely a local renderer so reviewers get both the source AND a pre-rendered
SVG in the repo (GitHub renders the Mermaid inline anyway, so SVGs are a
nice-to-have, not a hard requirement).

Usage:
    uv run python scripts/generate_diagrams.py

Requirements:
    - Node.js + ``npx`` on PATH (for ``@mermaid-js/mermaid-cli``).

Windows note:
    Matt's Docker stack runs under WSL; this script itself runs fine from
    either Git Bash or WSL. ``shutil.which`` resolves to ``npx.cmd`` /
    ``npx.ps1`` on Windows, which subprocess then needs as an absolute
    path — we handle both.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DIAGRAMS_DIR = Path("docs/diagrams")


def _resolve_npx() -> str:
    path = shutil.which("npx")
    if path is None:
        print(
            "ERROR: 'npx' not found on PATH. Install Node.js to render Mermaid diagrams.",
            file=sys.stderr,
        )
        sys.exit(1)
    return path


def _render_one(npx: str, mmd: Path) -> int:
    """Render a single .mmd file to .svg. Returns 0 on success, non-zero on failure."""
    svg = mmd.with_suffix(".svg")
    print(f"  {mmd.name} -> {svg.name}")
    result = subprocess.run(
        [
            npx,
            "-y",
            "@mermaid-js/mermaid-cli",
            "-i",
            str(mmd),
            "-o",
            str(svg),
            "-b",
            "white",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"    FAILED: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode


def main() -> int:
    if not DIAGRAMS_DIR.exists():
        print(f"ERROR: {DIAGRAMS_DIR} not found. Nothing to render.", file=sys.stderr)
        return 1

    mmds = sorted(DIAGRAMS_DIR.glob("*.mmd"))
    if not mmds:
        print(f"No .mmd files under {DIAGRAMS_DIR}.")
        return 0

    npx = _resolve_npx()
    print(f"Rendering {len(mmds)} Mermaid diagrams via {npx} ...")

    failures = sum(_render_one(npx, m) != 0 for m in mmds)
    if failures:
        print(f"\n{failures} of {len(mmds)} diagrams failed to render.", file=sys.stderr)
        return 1

    print(f"\nAll {len(mmds)} diagrams rendered to {DIAGRAMS_DIR}/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
