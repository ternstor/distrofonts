"""Shared generate loop: rank, fetch, extract, render, write HTML."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from distrofonts.distros import Distro
from distrofonts.html import write_index
from distrofonts.process import FontError
from distrofonts.ranking import load_ranking
from distrofonts.render import render_ttf, trim_png

LOGGER = logging.getLogger("distrofonts.pipeline")


@dataclass
class GenerateConfig:
    """Settings for one generate run."""

    distro: Distro
    source_dir: Path
    build_dir: Path
    output_dir: Path
    ignore_file: Path
    output_format: str
    limit: int | None
    target: int
    resume: bool
    fetch: bool
    retry_failures: bool
    font_size: int
    skip_integrity: bool


def load_ignore(path: Path, extra: Iterable[str] = ()) -> set[str]:
    """Return skipped package names from ``path`` plus ``extra``."""
    names = {name for name in extra if name}
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.add(stripped)
    return names


def existing_previews(output_dir: Path) -> list[str]:
    """Return package names that already have at least one PNG."""
    png_root = output_dir / "png"
    if not png_root.is_dir():
        return []
    names: list[str] = []
    for path in sorted(png_root.iterdir()):
        if path.is_dir() and any(path.glob("*.png")):
            names.append(path.name)
    return names


def load_failures(path: Path) -> list[str]:
    """Return previously recorded failed package names."""
    if not path.is_file():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.append(stripped)
    return names


def write_failures(path: Path, names: Iterable[str]) -> None:
    """Write failed package names, one per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    unique = list(dict.fromkeys(names))
    path.write_text("".join(f"{name}\n" for name in unique), encoding="utf-8")


def candidate_names(config: GenerateConfig) -> list[str]:
    """Return package names in ranking order, fetching ranking if requested."""
    dest = config.source_dir
    if config.fetch:
        packages = config.distro.refresh_ranking(dest)
        return [pkg.name for pkg in packages]
    ranking = load_ranking(dest / "ranking.json")
    discovered = config.distro.discover_names(dest)
    if ranking:
        extra = sorted(set(discovered) - set(ranking))
        return ranking + extra
    return discovered


def collect_existing_pngs(
    output_dir: Path, names: Iterable[str]
) -> dict[str, list[Path]]:
    """Map package names to PNG files already under ``output_dir/png``."""
    previews: dict[str, list[Path]] = {}
    for name in names:
        png_dir = output_dir / "png" / name
        if png_dir.is_dir():
            pngs = sorted(path for path in png_dir.glob("*.png") if path.is_file())
            if pngs:
                previews[name] = pngs
    return previews


def process_package(config: GenerateConfig, name: str) -> list[Path]:
    """Fetch, extract, and render one package. Raise FontError on failure."""
    distro = config.distro
    if not distro.has_source(config.source_dir, name):
        if not config.fetch:
            raise FontError(f"{name} has no source")
        status = distro.ensure_source(name, config.source_dir)
        if status == "failed" or not distro.has_source(config.source_dir, name):
            raise FontError(f"could not fetch {name}")
    extracted = distro.materialize(
        name,
        config.source_dir,
        config.build_dir,
        skip_integrity=config.skip_integrity,
    )
    ttfs = distro.find_ttfs(extracted)
    if not ttfs:
        raise FontError(f"{name} produced no TTF files")
    pngs: list[Path] = []
    dest = config.output_dir / "png" / name
    dest.mkdir(parents=True, exist_ok=True)
    for ttf in ttfs:
        rendered = render_ttf(ttf, config.font_size)
        if rendered is None:
            continue
        trim_png(rendered)
        dest_file = dest / rendered.name
        if rendered.resolve() != dest_file.resolve():
            shutil.copy(rendered, dest_file)
        pngs.append(dest_file)
    if not pngs:
        raise FontError(f"{name} produced no PNG previews")
    return pngs


def run(config: GenerateConfig) -> int:
    """Generate previews until ``target`` successes. Return a process exit code."""
    if not config.fetch and not config.source_dir.is_dir():
        LOGGER.error("Source directory does not exist: %s", config.source_dir)
        return 1

    ignore = load_ignore(config.ignore_file, config.distro.builtin_ignore)
    failures_path = config.output_dir / "failures.txt"
    previous_failures = load_failures(failures_path)
    if config.resume and not config.retry_failures:
        skip_failures = set(previous_failures)
    else:
        skip_failures = set()
    already = set(existing_previews(config.output_dir)) if config.resume else set()

    names = candidate_names(config)
    if config.limit is not None:
        names = names[: config.limit]

    successes: dict[str, list[Path]] = {}
    if config.resume:
        successes.update(collect_existing_pngs(config.output_dir, names))

    recorded_failures: list[str] = list(previous_failures) if config.resume else []
    attempts = 0
    for name in names:
        if len(successes) >= config.target:
            break
        if name in ignore or config.distro.is_proprietary(name):
            continue
        if name in already:
            continue
        if name in skip_failures:
            continue
        attempts += 1
        try:
            pngs = process_package(config, name)
        except FontError as exc:
            LOGGER.error("%s: %s", name, exc)
            recorded_failures.append(name)
            write_failures(failures_path, recorded_failures)
            continue
        successes[name] = pngs
        LOGGER.info(
            "Rendered %s (%d/%d)",
            name,
            len(successes),
            config.target,
        )

    if not successes:
        LOGGER.error("No packages produced PNG previews")
        write_failures(failures_path, recorded_failures)
        return 1

    ordered = {name: successes[name] for name in names if name in successes}
    write_index(ordered, config.output_dir, title=config.distro.display_name)
    write_failures(failures_path, recorded_failures)
    LOGGER.info(
        "Wrote %s (%d packages, %d attempts this run)",
        config.output_dir / "index.html",
        len(ordered),
        attempts,
    )
    return 0
