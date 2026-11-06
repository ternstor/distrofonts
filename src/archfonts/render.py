"""Render TTF files to trimmed PNG previews."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from archfonts.package import ArchFontError, run_command

LOGGER = logging.getLogger("archfonts.render")


def png_path_for(ttf: Path) -> Path:
    """Return the PNG path written beside a TTF file."""
    return Path(str(ttf) + ".png")


def trim_command(png: Path) -> list[str]:
    """Return the ImageMagick trim command for ``png``."""
    magick = shutil.which("magick")
    if magick:
        return [magick, str(png), "-trim", str(png)]
    convert = shutil.which("convert")
    if convert:
        return [convert, "-trim", str(png), str(png)]
    raise ArchFontError("ImageMagick not found")


def render_ttf(ttf: Path, font_size: int) -> Path | None:
    """Render one TTF with ttf2png. Return the PNG path, or None on failure."""
    png = png_path_for(ttf)
    command = ["ttf2png", "-s", str(font_size), "-o", str(png), str(ttf)]
    if run_command(command, ttf.parent, LOGGER) != 0:
        return None
    return png


def trim_png(png: Path) -> None:
    """Trim whitespace from a PNG with ImageMagick."""
    command = trim_command(png)
    if run_command(command, png.parent, LOGGER) != 0:
        raise ArchFontError(f"failed to trim {png}")
