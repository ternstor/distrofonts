"""Shared ranking.json helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("distrofonts.ranking")

RANKING_NAME = "ranking.json"
USER_AGENT = "distrofonts/1.0 (https://github.com/ternstor/distrofonts)"


@dataclass(frozen=True)
class RankedPackage:
    """One package name and popularity score."""

    name: str
    votes: int


def ranking_payload(packages: list[RankedPackage]) -> list[dict[str, str | int]]:
    """Serialize ranking for ranking.json."""
    return [{"name": pkg.name, "votes": pkg.votes} for pkg in packages]


def write_ranking(path: Path, packages: list[RankedPackage]) -> None:
    """Write vote/popularity order next to cached packages."""
    path.write_text(
        json.dumps(ranking_payload(packages), indent=2) + "\n",
        encoding="utf-8",
    )


def load_ranking(path: Path) -> list[str]:
    """Return package names in ranking order, or an empty list if missing."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("Could not parse ranking file %s", path)
        return []
    names: list[str] = []
    for row in data:
        name = row.get("name") if isinstance(row, dict) else None
        if isinstance(name, str) and name:
            names.append(name)
    return names


def select_top(packages: list[RankedPackage], top: int) -> list[RankedPackage]:
    """Return the first ``top`` packages."""
    if top < 0:
        raise ValueError("top must be zero or a positive integer")
    return packages[:top]


def order_by_ranking(packages: list[Path], ranking: list[str]) -> list[Path]:
    """Put ranked packages first, then any leftovers in name order."""
    by_name = {path.name: path for path in packages}
    ordered: list[Path] = []
    seen: set[str] = set()
    for name in ranking:
        path = by_name.get(name)
        if path is not None:
            ordered.append(path)
            seen.add(name)
    leftovers = sorted(path for path in packages if path.name not in seen)
    return ordered + leftovers
