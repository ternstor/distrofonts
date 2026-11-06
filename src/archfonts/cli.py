"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

from archfonts.fetch import (
    RANKING_NAME,
    clone_package,
    load_ranking,
    refresh_ranking,
)
from archfonts.html import write_index
from archfonts.package import (
    ArchFontError,
    ArchFontPackage,
    discover_packages,
    existing_previews,
    load_failures,
    load_ignore,
    write_failures,
)
from archfonts.render import render_ttf, trim_png

LOGGER = logging.getLogger("archfonts")


@dataclass(frozen=True)
class Config:
    """Resolved command-line options."""

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


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or a positive integer")
    return number


def parse_args(argv: list[str] | None = None) -> Config:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build PNG files from TTF packages in the AUR."
    )
    parser.add_argument(
        "-o",
        "--output",
        choices=["html"],
        default="html",
        help="output type (default: html)",
    )
    parser.add_argument(
        "-s",
        "--source-dir",
        type=Path,
        default=Path("/var/aur"),
        help="directory where AUR packages live (default: /var/aur)",
    )
    parser.add_argument(
        "-b",
        "--build-dir",
        type=Path,
        default=Path("/tmp/archfonts"),
        help="directory where packages are copied and built (default: /tmp/archfonts)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="directory for the HTML index and PNGs (default: ./dist)",
    )
    parser.add_argument(
        "--ignore-file",
        type=Path,
        default=Path("ignore.txt"),
        help="package names to skip, one per line (default: ./ignore.txt)",
    )
    parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        help="attempt at most this many new packages this run",
    )
    parser.add_argument(
        "--target",
        type=_positive_int,
        default=100,
        help="keep going until this many successful packages exist (default: 100)",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="reuse PNGs already in --output-dir and skip those packages (default: on)",
    )
    parser.add_argument(
        "--fetch",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="clone missing AUR packages from the vote ranking as needed",
    )
    parser.add_argument(
        "--retry-failures",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="retry packages listed in failures.txt (default: skip them)",
    )
    parser.add_argument(
        "--font-size",
        type=_positive_int,
        default=20,
        help="ttf2png font size in pixels (default: 20)",
    )
    parser.add_argument(
        "--skip-integrity",
        action="store_true",
        help="pass --skipchecksums, --skipinteg, and --skippgpcheck to makepkg",
    )
    args = parser.parse_args(argv)
    return Config(
        source_dir=args.source_dir,
        build_dir=args.build_dir,
        output_dir=args.output_dir,
        ignore_file=args.ignore_file,
        output_format=args.output,
        limit=args.limit,
        target=args.target,
        resume=args.resume,
        fetch=args.fetch,
        retry_failures=args.retry_failures,
        font_size=args.font_size,
        skip_integrity=args.skip_integrity,
    )


def candidate_names(config: Config) -> list[str]:
    """Return package names in vote order, cloning the ranking when asked."""
    ranking_path = config.source_dir / RANKING_NAME
    if config.fetch:
        packages = refresh_ranking(config.source_dir)
        return [pkg.name for pkg in packages]
    ranking = load_ranking(ranking_path)
    if ranking:
        discovered = {path.name for path in discover_packages(config.source_dir)}
        extra = sorted(discovered - set(ranking))
        return ranking + extra
    return [path.name for path in discover_packages(config.source_dir)]


def order_previews(
    previews: dict[str, list[Path]], ranking: list[str]
) -> dict[str, list[Path]]:
    """Return previews in ranking order, then any leftovers."""
    ordered: dict[str, list[Path]] = {}
    for name in ranking:
        if name in previews:
            ordered[name] = previews[name]
    for name, pngs in previews.items():
        if name not in ordered:
            ordered[name] = pngs
    return ordered


def render_package(package: ArchFontPackage) -> list[Path]:
    """Build, extract, and render one package. Empty list means failure."""
    if package.build() != 0:
        return []
    package.extract()
    pngs: list[Path] = []
    for ttf in package.find_ttfs():
        png = render_ttf(ttf, package.font_size)
        if png is None:
            LOGGER.error("Failed to render %s", ttf)
            continue
        trim_png(png)
        pngs.append(png)
    return pngs


def run(config: Config) -> int:
    """Build font previews and write the index. Return a process exit code."""
    if not config.source_dir.is_dir():
        if config.fetch:
            config.source_dir.mkdir(parents=True, exist_ok=True)
        else:
            LOGGER.error("Source directory does not exist: %s", config.source_dir)
            return 1

    ignored = load_ignore(config.ignore_file)
    failure_path = config.output_dir / "failures.txt"
    previous_failures = load_failures(failure_path)
    skip_failed = set(previous_failures) if not config.retry_failures else set()
    failed: list[str] = list(previous_failures)
    previews = existing_previews(config.output_dir) if config.resume else {}
    ranking = candidate_names(config)
    attempts = 0
    LOGGER.info(
        "Have %d/%d successful packages before this run",
        len(previews),
        config.target,
    )

    for position, name in enumerate(ranking, start=1):
        if len(previews) >= config.target:
            LOGGER.info("Reached target of %d successful packages", config.target)
            break
        if name in ignored:
            LOGGER.info("[%d] Ignoring %s", position, name)
            continue
        if name in previews:
            LOGGER.info("[%d] Already have %s", position, name)
            continue
        if name in skip_failed:
            LOGGER.info("[%d] Skipping previous failure %s", position, name)
            continue
        if config.limit is not None and attempts >= config.limit:
            LOGGER.info("Reached attempt limit of %d", config.limit)
            break

        source = config.source_dir / name
        if not (source / "PKGBUILD").is_file():
            if config.fetch:
                status = clone_package(name, config.source_dir, update=False)
                LOGGER.info("[%d] %s %s", position, status, name)
                if status == "failed" or not (source / "PKGBUILD").is_file():
                    if name not in failed:
                        failed.append(name)
                    continue
            elif source.is_dir():
                LOGGER.error("[%d] No PKGBUILD for %s", position, name)
                if name not in failed:
                    failed.append(name)
                continue
            else:
                continue

        attempts += 1
        LOGGER.info(
            "[%d] Processing %s (%d/%d successful)",
            position,
            name,
            len(previews),
            config.target,
        )
        package = ArchFontPackage(
            source,
            font_size=config.font_size,
            skip_integrity=config.skip_integrity,
        )
        try:
            package.copy_to(config.build_dir / name)
            pngs = render_package(package)
            if not pngs:
                LOGGER.error("[%d] Build failed for %s", position, name)
                if name not in failed:
                    failed.append(name)
                continue
            previews[name] = pngs
            failed = [item for item in failed if item != name]
        except ArchFontError as exc:
            LOGGER.error("[%d] %s failed: %s", position, name, exc)
            if name not in failed:
                failed.append(name)

    if config.output_format == "html":
        index_path = write_index(order_previews(previews, ranking), config.output_dir)
        LOGGER.info("Wrote %s (%d packages)", index_path, len(previews))
    write_failures(failure_path, failed)
    if len(previews) < config.target:
        LOGGER.warning(
            "Finished with %d/%d successful packages",
            len(previews),
            config.target,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return run(parse_args(argv))
