"""Fetch the most-voted AUR ttf-* packages."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("archfonts.fetch")

AUR_RPC = "https://aur.archlinux.org/rpc/v5/search/ttf-?by=name"
AUR_CLONE = "https://aur.archlinux.org/{name}.git"
USER_AGENT = "archfonts/1.0 (https://github.com/ternstor/distrofonts)"
RANKING_NAME = "ranking.json"

# Packages that need local Windows/macOS/WPS vendor files and cannot be
# built in a clean Docker container.
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

DEFAULT_TOP = 100


@dataclass(frozen=True)
class AurPackage:
    """One AUR package name and vote count."""

    name: str
    votes: int


def is_proprietary(name: str) -> bool:
    """Return True if the package needs vendor font files."""
    return name.startswith(PROPRIETARY_PREFIXES)


def parse_search_results(payload: dict[str, Any]) -> list[AurPackage]:
    """Keep ttf-* packages, drop proprietary names, sort by votes."""
    packages: list[AurPackage] = []
    for row in payload.get("results", []):
        name = str(row.get("Name", ""))
        if not name.startswith("ttf-") or is_proprietary(name):
            continue
        packages.append(AurPackage(name=name, votes=int(row.get("NumVotes", 0))))
    packages.sort(key=lambda pkg: (-pkg.votes, pkg.name))
    return packages


def select_top(packages: list[AurPackage], top: int) -> list[AurPackage]:
    """Return the first ``top`` packages."""
    if top < 0:
        raise ValueError("top must be zero or a positive integer")
    return packages[:top]


def ranking_payload(packages: list[AurPackage]) -> list[dict[str, str | int]]:
    """Serialize ranking for ranking.json."""
    return [{"name": pkg.name, "votes": pkg.votes} for pkg in packages]


def write_ranking(path: Path, packages: list[AurPackage]) -> None:
    """Write vote order next to the cloned packages."""
    path.write_text(
        json.dumps(ranking_payload(packages), indent=2) + "\n",
        encoding="utf-8",
    )


def load_ranking(path: Path) -> list[str]:
    """Return package names in vote order, or an empty list if missing."""
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


def fetch_search(url: str = AUR_RPC) -> dict[str, Any]:
    """Query the AUR RPC search endpoint."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _has_pkgbuild(repo: Path) -> bool:
    return (repo / "PKGBUILD").is_file()


def clone_package(name: str, dest: Path, *, update: bool) -> str:
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


def _positive_or_zero(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("top must be zero or a positive integer")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse fetch CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Clone the most-voted AUR ttf-* packages."
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("aur"),
        help="directory to clone packages into (default: ./aur)",
    )
    parser.add_argument(
        "--top",
        type=_positive_or_zero,
        default=DEFAULT_TOP,
        help="number of packages to fetch (default: 100)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="git pull existing clones instead of skipping them",
    )
    return parser.parse_args(argv)


def refresh_ranking(dest: Path) -> list[AurPackage]:
    """Query AUR and write the full eligible ranking to ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    packages = parse_search_results(fetch_search())
    write_ranking(dest / RANKING_NAME, packages)
    LOGGER.info("Wrote ranking of %d eligible packages to %s", len(packages), dest)
    return packages


def run(dest: Path, top: int, update: bool) -> int:
    """Fetch ranking and clone packages. Return a process exit code."""
    packages = refresh_ranking(dest)
    selected = select_top(packages, top)
    LOGGER.info(
        "Cloning the top %d of %d eligible packages", len(selected), len(packages)
    )

    failures = 0
    for index, package in enumerate(selected, start=1):
        status = clone_package(package.name, dest, update=update)
        LOGGER.info(
            "[%d/%d] %s %s (%d votes)",
            index,
            len(selected),
            status,
            package.name,
            package.votes,
        )
        if status == "failed":
            failures += 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args(argv)
    return run(args.dest, args.top, args.update)


if __name__ == "__main__":
    raise SystemExit(main())
