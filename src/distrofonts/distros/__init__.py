"""Distro adapters for ranking, fetching, and extracting font packages."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from distrofonts.ranking import RankedPackage


@runtime_checkable
class Distro(Protocol):
    """Per-distribution ranking, fetch, and extract adapter."""

    name: str
    display_name: str
    default_source_dir: Path
    default_build_dir: Path
    host_cache_dir: Path
    builtin_ignore: frozenset[str]

    def is_proprietary(self, name: str) -> bool: ...

    def refresh_ranking(self, dest: Path) -> list[RankedPackage]: ...

    def discover_names(self, dest: Path) -> list[str]: ...

    def has_source(self, dest: Path, name: str) -> bool: ...

    def ensure_source(self, name: str, dest: Path, *, update: bool = False) -> str: ...

    def materialize(
        self,
        name: str,
        source_dir: Path,
        build_dir: Path,
        *,
        skip_integrity: bool = False,
    ) -> Path: ...

    def find_ttfs(self, extracted: Path) -> list[Path]: ...


def get_distro(name: str) -> Distro:
    """Return the adapter for ``name``."""
    from distrofonts.distros.archlinux import ArchlinuxDistro
    from distrofonts.distros.debian import DebianDistro

    distros: dict[str, Distro] = {
        ArchlinuxDistro.name: ArchlinuxDistro(),
        DebianDistro.name: DebianDistro(),
    }
    try:
        return distros[name]
    except KeyError as exc:
        known = ", ".join(sorted(distros))
        raise ValueError(f"unknown distro {name!r}; expected one of: {known}") from exc
