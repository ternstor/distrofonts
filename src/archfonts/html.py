"""Write an HTML index of rendered font previews."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import escape
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

GENERATED_MARK = "<!-- GENERATED -->"
CONTENT_MARK = "<!-- CONTENT -->"


def template_text() -> str:
    """Load the packaged HTML template."""
    resource = files("archfonts").joinpath("templates", "index.html")
    try:
        return resource.read_text(encoding="utf-8")
    except FileNotFoundError:
        fallback = Path(__file__).resolve().parent / "templates" / "index.html"
        return fallback.read_text(encoding="utf-8")


def write_index(
    ttfs: Mapping[str, Sequence[Path]],
    output_dir: Path,
    *,
    generated_at: datetime | None = None,
) -> Path:
    """Copy PNGs under ``output_dir`` and write ``index.html``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    when = generated_at or datetime.now(UTC)
    stamp = when.strftime("%Y-%m-%d %H:%M UTC")
    sections: list[str] = []
    for pkg_name, pngs in ttfs.items():
        dest = output_dir / "png" / pkg_name
        dest.mkdir(parents=True, exist_ok=True)
        items: list[str] = []
        for png in pngs:
            dest_file = dest / png.name
            if png.resolve() != dest_file.resolve():
                shutil.copy(png, dest_file)
            rel = f"png/{quote(pkg_name)}/{quote(png.name)}"
            label = escape(png.name)
            items.append(f'<li>{label}<br><img src="{rel}" alt="{label}"></li>')
        body = "\n".join(items)
        sections.append(f"<h2>{escape(pkg_name)}</h2>\n<ul>\n{body}\n</ul>")

    html = template_text()
    html = html.replace(GENERATED_MARK, escape(stamp))
    html = html.replace(CONTENT_MARK, "\n".join(sections))
    index = output_dir / "index.html"
    index.write_text(html, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return index
