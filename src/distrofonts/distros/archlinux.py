"""Arch Linux AUR ttf-* adapter."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

from distrofonts.process import FontError, run_command
from distrofonts.ranking import USER_AGENT, RankedPackage, write_ranking

LOGGER = logging.getLogger("distrofonts.archlinux")

AUR_RPC = "https://aur.archlinux.org/rpc/v5/search/ttf-?by=name"
AUR_CLONE = "https://aur.archlinux.org/{name}.git"

PROPRIETARY_PREFIXES = (
    "ttf-ms-",
    "ttf-win",
    "ttf-vista-fonts",
    "ttf-mac-fonts",
    "ttf-apple-emoji",
    "ttf-wps-fonts",
    "ttf-office-2007-fonts",
    "ttf-tahoma",
)


def is_proprietary(name: str) -> bool:
    """Return True if the package needs vendor font files."""
    return name.startswith(PROPRIETARY_PREFIXES)


def parse_search_results(payload: dict[str, Any]) -> list[RankedPackage]:
    """Keep ttf-* packages, drop proprietary names, sort by votes."""
    packages: list[RankedPackage] = []
    for row in payload.get("results", []):
        name = str(row.get("Name", ""))
        if not name.startswith("ttf-") or is_proprietary(name):
            continue
        packages.append(RankedPackage(name=name, votes=int(row.get("NumVotes", 0))))
    packages.sort(key=lambda pkg: (-pkg.votes, pkg.name))
    return packages


def fetch_search(url: str = AUR_RPC) -> dict[str, Any]:
    """Query the AUR RPC search endpoint."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _has_pkgbuild(repo: Path) -> bool:
    return (repo / "PKGBUILD").is_file()


def clone_package(name: str, dest: Path, *, update: bool = False) -> str:
    """Clone or skip (or update) one AUR git repository. Return a status."""
    repo = dest / name
    git_dir = repo / ".git"
    if git_dir.is_dir() and _has_pkgbuild(repo):
        if not update:
            return "skipped"
        completed = subprocess.run(
            ["git", "-C", str(repo), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            LOGGER.error("git pull failed for %s:\n%s", name, completed.stderr)
            return "failed"
        if not _has_pkgbuild(repo):
            LOGGER.error("git pull of %s left no PKGBUILD", name)
            return "failed"
        return "updated"
    if repo.exists():
        shutil.rmtree(repo)
    dest.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "clone", "--depth", "1", AUR_CLONE.format(name=name), str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        LOGGER.error("git clone failed for %s:\n%s", name, completed.stderr)
        shutil.rmtree(repo, ignore_errors=True)
        return "failed"
    if not _has_pkgbuild(repo):
        LOGGER.error(
            "git clone of %s produced no PKGBUILD:\n%s",
            name,
            completed.stderr,
        )
        shutil.rmtree(repo, ignore_errors=True)
        return "failed"
    return "cloned"


def makepkg_command(skip_integrity: bool) -> list[str]:
    """Return the makepkg argv, optionally skipping integrity checks."""
    command = [
        "makepkg",
        "--force",
        "--syncdeps",
        "--ignorearch",
        "--nocolor",
        "--noconfirm",
    ]
    if skip_integrity:
        command.extend(["--skipchecksums", "--skipinteg", "--skippgpcheck"])
    return command


def find_archives(directory: Path) -> list[Path]:
    """Return unique ``*.pkg.tar.*`` archives in ``directory``."""
    found: dict[Path, Path] = {}
    for path in directory.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if ".pkg.tar." not in name:
            continue
        found[path.resolve()] = path
    return sorted(found.values())


def extract_archive(archive: Path, dest: Path) -> None:
    """Extract a pacman package archive into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".xz"):
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter="data")
        return
    if run_command(["tar", "xf", str(archive)], dest, LOGGER) != 0:
        raise FontError(f"failed to extract {archive}")


def find_ttfs(extracted: Path) -> list[Path]:
    """Return TTF files, preferring ``usr/share/fonts``."""
    preferred = extracted / "usr" / "share" / "fonts"
    search_root = preferred if preferred.is_dir() else extracted
    return sorted(path for path in search_root.rglob("*.ttf") if path.is_file())


class ArchlinuxDistro:
    """AUR ttf-* packages ranked by vote count."""

    name = "archlinux"
    display_name = "Arch fonts"
    default_source_dir = Path("/var/aur")
    default_build_dir = Path("/tmp/distrofonts")
    host_cache_dir = Path("aur")
    builtin_ignore: frozenset[str] = frozenset({"ttf-win10"})

    def is_proprietary(self, name: str) -> bool:
        return is_proprietary(name)

    def refresh_ranking(self, dest: Path) -> list[RankedPackage]:
        dest.mkdir(parents=True, exist_ok=True)
        packages = parse_search_results(fetch_search())
        write_ranking(dest / "ranking.json", packages)
        LOGGER.info("Wrote ranking of %d eligible packages to %s", len(packages), dest)
        return packages

    def discover_names(self, dest: Path) -> list[str]:
        if not dest.is_dir():
            return []
        names = [
            path.name
            for path in dest.iterdir()
            if path.is_dir() and path.name.startswith("ttf-")
        ]
        names.sort()
        return names

    def has_source(self, dest: Path, name: str) -> bool:
        return _has_pkgbuild(dest / name)

    def ensure_source(self, name: str, dest: Path, *, update: bool = False) -> str:
        return clone_package(name, dest, update=update)

    def materialize(
        self,
        name: str,
        source_dir: Path,
        build_dir: Path,
        *,
        skip_integrity: bool = False,
    ) -> Path:
        source = source_dir / name
        if not _has_pkgbuild(source):
            raise FontError(f"{name} has no PKGBUILD")
        pkg_dir = build_dir / name
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)
        shutil.copytree(source, pkg_dir)
        if run_command(makepkg_command(skip_integrity), pkg_dir, LOGGER) != 0:
            raise FontError(f"makepkg failed for {name}")
        archives = find_archives(pkg_dir)
        if not archives:
            raise FontError(f"{name} produced no package archive")
        for archive in archives:
            extract_archive(archive, pkg_dir)
        return pkg_dir

    def find_ttfs(self, extracted: Path) -> list[Path]:
        return find_ttfs(extracted)
