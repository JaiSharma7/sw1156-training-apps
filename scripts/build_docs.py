"""Publish the static Modified Puls web app into /docs for GitHub Pages.

Mirror semantics (file-level): copies index.html + css/js/vendor from source into docs/, overwriting
changed files and pruning files that no longer exist in source. It does NOT remove the directory
nodes themselves (rmdir can fail under OneDrive/Windows file locks), and it touches nothing else in
docs/.

Run from the repo root:  python scripts/build_docs.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "apps" / "modified_puls_web"
DOCS = ROOT / "docs"

SUBDIRS = ["css", "js", "vendor"]
FILES = ["index.html"]


def mirror_dir(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    wanted = {p.relative_to(src) for p in src.rglob("*") if p.is_file()}
    for rel in wanted:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, target)
    # Prune stale files that are no longer in source (file-level; keep directory nodes).
    for p in dst.rglob("*"):
        if p.is_file() and p.relative_to(dst) not in wanted:
            p.unlink()


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        mirror_dir(SRC / sub, DOCS / sub)
    for f in FILES:
        shutil.copy2(SRC / f, DOCS / f)
    # GitHub Pages: skip Jekyll so files/dirs are served verbatim.
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"published app to {DOCS} ({', '.join(SUBDIRS)}, {', '.join(FILES)}, .nojekyll)")


if __name__ == "__main__":
    main()
