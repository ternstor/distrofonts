"""Discover Arch font packages, build them, and locate TTF files."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

BUILTIN_IGNORE = ("ttf-win10",)

ARCHIVE_GLOBS = ("*.pkg.tar.zst", "*.pkg.tar.xz", "*.pkg.tar.gz")

MAKEPKG_BASE = [
    "makepkg",
    "--force",
    "--syncdeps",
    "--ignorearch",
    "--nocolor",
    "--noconfirm",
]

SKIP_INTEGRITY = ["--skipchecksums", "--skipinteg", "--skippgpcheck"]


class ArchFontError(Exception):
    """A package failed in a way the batch run can record and continue past."""


def discover_packages(source_dir: Path, limit: int | None = None) -> list[Path]:
    """Return ``ttf-*`` package directories, optionally capped."""
    packages = sorted(path for path in source_dir.glob("ttf-*") if path.is_dir())
    if limit is None:
        return packages
    return packages[:limit]


def load_ignore(path: Path) -> set[str]:
    """Load package names to skip. ``ttf-win10`` is always included."""
    names = set(BUILTIN_IGNORE)
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                names.add(stripped)
    return names


def write_failures(path: Path, names: list[str]) -> None:
    """Write this run's failed package names. Does not touch the ignore file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            unique.append(name)
            seen.add(name)
    path.write_text("".join(f"{name}\n" for name in unique), encoding="utf-8")


def load_failures(path: Path) -> list[str]:
    """Return previously recorded failed package names."""
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def existing_previews(output_dir: Path) -> dict[str, list[Path]]:
    """Return PNG previews already present under ``output_dir/png``."""
    root = output_dir / "png"
    found: dict[str, list[Path]] = {}
    if not root.is_dir():
        return found
    for pkg_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        pngs = sorted(pkg_dir.glob("*.png"))
        if pngs:
            found[pkg_dir.name] = pngs
    return found


def makepkg_command(skip_integrity: bool) -> list[str]:
    """Return the makepkg invocation. Integrity skips are opt-in."""
    command = list(MAKEPKG_BASE)
    if skip_integrity:
        command.extend(SKIP_INTEGRITY)
    return command


def find_archives(pkg_dir: Path) -> list[Path]:
    """Return built package archives in ``pkg_dir``, each path once."""
    archives: set[Path] = set()
    for pattern in ARCHIVE_GLOBS:
        archives.update(pkg_dir.glob(pattern))
    return sorted(archives)


def run_command(command: list[str], cwd: Path, logger: logging.Logger) -> int:
    """Run a command in ``cwd`` and log stderr when it fails."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        logger.error(
            "Error running '%s' in '%s':\n%s",
            " ".join(command),
            cwd,
            completed.stderr,
        )
    return completed.returncode


class ArchFontPackage:
    """One Arch package directory that may contain font files."""

    def __init__(
        self,
        pkg_dir: Path,
        *,
        font_size: int,
        skip_integrity: bool,
    ) -> None:
        self.source_dir = pkg_dir
        self.pkg_dir = pkg_dir
        self.pkg_name = pkg_dir.name
        self.font_size = font_size
        self.skip_integrity = skip_integrity
        self.logger = logging.getLogger(self.pkg_name)

    def copy_to(self, dest: Path) -> None:
        """Copy package sources into ``dest`` and build there afterwards."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.source_dir, dest, dirs_exist_ok=True)
        self.pkg_dir = dest

    def build(self) -> int:
        """Build the package. Return the makepkg exit code."""
        return run_command(
            makepkg_command(self.skip_integrity),
            self.pkg_dir,
            self.logger,
        )

    def extract(self) -> None:
        """Extract every built package archive into the package directory."""
        archives = find_archives(self.pkg_dir)
        if not archives:
            raise ArchFontError(f"no package archive in {self.pkg_dir}")
        for archive in archives:
            code = run_command(
                ["tar", "-xf", str(archive)],
                self.pkg_dir,
                self.logger,
            )
            if code != 0:
                raise ArchFontError(f"failed to extract {archive.name}")

    def find_ttfs(self) -> list[Path]:
        """Return TTF files, preferring those extracted into usr/share/fonts."""
        installed = self.pkg_dir / "usr" / "share" / "fonts"
        if installed.is_dir():
            found = sorted(installed.rglob("*.ttf"))
            if found:
                return found
        return sorted(self.pkg_dir.rglob("*.ttf"))
