"""Publish the static Modified Puls web app into /docs for GitHub Pages.

Mirror semantics (file-level): copies index.html + css/js/vendor from source into docs/, overwriting
changed files and pruning files that no longer exist in source. It does NOT remove the directory
nodes themselves (rmdir can fail under OneDrive/Windows file locks), and it touches nothing else in
docs/.

Cache-busting: the SOURCE keeps clean asset URLs, but the published docs/ copies get a content-hash
query (`?v=<hash>`) appended to local CSS/JS/vendor references and to relative ES-module imports. The
hash only changes when content changes, so browsers re-fetch updated files after a redeploy but keep
caching unchanged ones.

Run from the repo root:  python scripts/build_docs.py
"""

import hashlib
import re
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
    for p in dst.rglob("*"):
        if p.is_file() and p.relative_to(dst) not in wanted:
            p.unlink()


def content_token() -> str:
    h = hashlib.sha1()
    for sub in SUBDIRS:
        for p in sorted((SRC / sub).rglob("*")):
            if p.is_file():
                h.update(p.read_bytes())
    for f in FILES:
        h.update((SRC / f).read_bytes())
    return h.hexdigest()[:8]


def bust_html(text: str, token: str) -> str:
    # Append ?v=token to local href/src referencing css/js/vendor assets.
    return re.sub(
        r'((?:href|src)=")((?:css|js|vendor)/[^"?]+)(")',
        rf"\1\2?v={token}\3",
        text,
    )


def bust_js(text: str, token: str) -> str:
    # Append ?v=token to relative ES-module import specifiers (e.g. from "./routing.js").
    return re.sub(
        r'(from\s+")(\./[^"?]+\.js)(")',
        rf"\1\2?v={token}\3",
        text,
    )


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        mirror_dir(SRC / sub, DOCS / sub)
    for f in FILES:
        shutil.copy2(SRC / f, DOCS / f)

    token = content_token()
    index = DOCS / "index.html"
    index.write_text(bust_html(index.read_text(encoding="utf-8"), token), encoding="utf-8")
    for js in (DOCS / "js").glob("*.js"):
        js.write_text(bust_js(js.read_text(encoding="utf-8"), token), encoding="utf-8")

    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"published app to {DOCS} (cache-bust token v={token})")


if __name__ == "__main__":
    main()
