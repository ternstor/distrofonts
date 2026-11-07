"""Debian fonts-* / ttf-* adapter ranked by popcon."""

from __future__ import annotations

import gzip
import logging
import shutil
import urllib.request
from pathlib import Path

from distrofonts.process import FontError, run_command
from distrofonts.ranking import USER_AGENT, RankedPackage, write_ranking

LOGGER = logging.getLogger("distrofonts.debian")

POPCON_URL = "https://popcon.debian.org/by_inst.gz"
FONT_PREFIXES = ("fonts-", "ttf-")
_APT_UPDATED = False


def _ensure_apt_index() -> None:
    """Refresh apt lists once so ``apt-get download`` can resolve packages."""
    global _APT_UPDATED
    if _APT_UPDATED:
        return
    if run_command(["sudo", "apt-get", "update"], Path("/tmp"), LOGGER) != 0:
        LOGGER.warning("apt-get update failed; download may use stale indexes")
    _APT_UPDATED = True


def is_font_package(name: str) -> bool:
    """Return True if the name looks like a Debian font package."""
    return name.startswith(FONT_PREFIXES)


def is_proprietary(name: str) -> bool:
    """Return True if the package is a vendor installer, not a font."""
    return name.endswith("-installer")


def parse_popcon(text: str) -> list[RankedPackage]:
    """Keep fonts-* / ttf-* packages, drop installers, sort by inst count."""
    packages: list[RankedPackage] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        # rank name inst vote old recent no-files (maintainer)
        if len(parts) < 3:
            continue
        name = parts[1]
        if not is_font_package(name) or is_proprietary(name):
            continue
        try:
            inst = int(parts[2])
        except ValueError:
            continue
        packages.append(RankedPackage(name=name, votes=inst))
    packages.sort(key=lambda pkg: (-pkg.votes, pkg.name))
    return packages


def fetch_popcon(url: str = POPCON_URL) -> str:
    """Download and decompress the popcon by_inst table."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    if url.endswith(".gz") or payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    return payload.decode("utf-8", errors="replace")


def find_debs(directory: Path) -> list[Path]:
    """Return ``*.deb`` files in ``directory``."""
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.suffix == ".deb")


def find_ttfs(extracted: Path) -> list[Path]:
    """Return TTF files, preferring ``usr/share/fonts``."""
    preferred = extracted / "usr" / "share" / "fonts"
    search_root = preferred if preferred.is_dir() else extracted
    return sorted(path for path in search_root.rglob("*.ttf") if path.is_file())


class DebianDistro:
    """Debian font packages ranked by popcon installation count."""

    name = "debian"
    display_name = "Debian fonts"
    default_source_dir = Path("/var/debian")
    default_build_dir = Path("/tmp/distrofonts")
    host_cache_dir = Path("debian")
    builtin_ignore: frozenset[str] = frozenset()

    def is_proprietary(self, name: str) -> bool:
        return is_proprietary(name)

    def refresh_ranking(self, dest: Path) -> list[RankedPackage]:
        dest.mkdir(parents=True, exist_ok=True)
        _ensure_apt_index()
        packages = parse_popcon(fetch_popcon())
        write_ranking(dest / "ranking.json", packages)
        LOGGER.info("Wrote ranking of %d eligible packages to %s", len(packages), dest)
        return packages

    def discover_names(self, dest: Path) -> list[str]:
        if not dest.is_dir():
            return []
        names = [
            path.name
            for path in dest.iterdir()
            if path.is_dir() and is_font_package(path.name)
        ]
        names.sort()
        return names

    def has_source(self, dest: Path, name: str) -> bool:
        return bool(find_debs(dest / name))

    def ensure_source(self, name: str, dest: Path, *, update: bool = False) -> str:
        pkg_dir = dest / name
        _ensure_apt_index()
        if self.has_source(dest, name) and not update:
            return "skipped"
        if pkg_dir.exists() and update:
            shutil.rmtree(pkg_dir)
        pkg_dir.mkdir(parents=True, exist_ok=True)
        if run_command(["apt-get", "download", name], pkg_dir, LOGGER) != 0:
            shutil.rmtree(pkg_dir, ignore_errors=True)
            return "failed"
        if not self.has_source(dest, name):
            LOGGER.error("apt-get download of %s produced no .deb", name)
            shutil.rmtree(pkg_dir, ignore_errors=True)
            return "failed"
        return "downloaded"

    def materialize(
        self,
        name: str,
        source_dir: Path,
        build_dir: Path,
        *,
        skip_integrity: bool = False,
    ) -> Path:
        del skip_integrity
        debs = find_debs(source_dir / name)
        if not debs:
            raise FontError(f"{name} has no .deb")
        extracted = build_dir / name
        if extracted.exists():
            shutil.rmtree(extracted)
        extracted.mkdir(parents=True, exist_ok=True)
        for deb in debs:
            command = ["dpkg-deb", "-x", str(deb), str(extracted)]
            if run_command(command, extracted, LOGGER) != 0:
                raise FontError(f"failed to extract {deb.name}")
        return extracted

    def find_ttfs(self, extracted: Path) -> list[Path]:
        return find_ttfs(extracted)
