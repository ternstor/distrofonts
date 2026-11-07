"""Command-line interface for distrofonts generate and fetch."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from distrofonts.distros import Distro, get_distro
from distrofonts.pipeline import GenerateConfig
from distrofonts.pipeline import run as run_generate
from distrofonts.ranking import RankedPackage, select_top

LOGGER = logging.getLogger("distrofonts")

DEFAULT_TARGET = 100
DEFAULT_TOP = 100
DISTRO_CHOICES = ("archlinux", "debian")


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _positive_or_zero(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or a positive integer")
    return number


def _add_distro_argument(parser: argparse.ArgumentParser, default: str | None) -> None:
    kwargs: dict[str, object] = {
        "choices": DISTRO_CHOICES,
        "help": "distribution adapter to use",
    }
    if default is None:
        kwargs["required"] = True
    else:
        kwargs["default"] = default
    parser.add_argument("--distro", **kwargs)


def _add_generate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="directory of cached package sources",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="scratch directory for extract/build (default: /tmp/distrofonts)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="directory for index.html and png/ (default: dist/<distro>)",
    )
    parser.add_argument(
        "--ignore-file",
        type=Path,
        default=None,
        help="package names to skip (default: ignore/<distro>.txt)",
    )
    parser.add_argument(
        "-o",
        "--output-format",
        choices=("html",),
        default="html",
        help="output format (default: html)",
    )
    parser.add_argument(
        "--limit",
        type=_positive_or_zero,
        default=None,
        help="maximum number of ranked packages to consider",
    )
    parser.add_argument(
        "--target",
        type=_positive,
        default=DEFAULT_TARGET,
        help="stop after this many successful packages (default: 100)",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="reuse existing PNGs and skip recorded failures (default: true)",
    )
    parser.add_argument(
        "--fetch",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="refresh ranking and fetch missing packages (default: false)",
    )
    parser.add_argument(
        "--retry-failures",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="retry names listed in failures.txt (default: false)",
    )
    parser.add_argument(
        "--font-size",
        type=_positive,
        default=20,
        help="ttf2png font size (default: 20)",
    )
    parser.add_argument(
        "--skip-integrity",
        action="store_true",
        help="skip makepkg integrity checks (Arch only)",
    )


def _add_fetch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="directory to cache packages into",
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
        help="refresh already-cached packages instead of skipping them",
    )


def _parser(
    *, default_distro: str | None, require_command: bool
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build PNG previews of popular Linux font packages."
    )
    sub = parser.add_subparsers(dest="command", required=require_command)

    generate = sub.add_parser("generate", help="build PNG previews")
    _add_distro_argument(generate, default_distro)
    _add_generate_arguments(generate)

    fetch = sub.add_parser("fetch", help="rank and cache font packages")
    _add_distro_argument(fetch, default_distro)
    _add_fetch_arguments(fetch)
    return parser


def parse_args(
    argv: list[str] | None = None,
    *,
    default_distro: str | None = "archlinux",
    default_command: str | None = None,
) -> argparse.Namespace:
    """Parse CLI arguments for distrofonts or the Arch aliases."""
    args = list(argv) if argv is not None else None
    require_command = default_command is None
    if default_command is not None:
        if args is None:
            import sys

            args = sys.argv[1:]
        if not args or args[0] not in {"generate", "fetch", "-h", "--help"}:
            args = [default_command, *args]
    parser = _parser(default_distro=default_distro, require_command=require_command)
    return parser.parse_args(args)


def parse_generate_args(argv: list[str] | None = None) -> GenerateConfig:
    """Parse generate flags into a ``GenerateConfig`` (Arch defaults)."""
    return _config_from_args(
        parse_args(argv, default_distro="archlinux", default_command="generate")
    )


def _config_from_args(args: argparse.Namespace) -> GenerateConfig:
    distro = get_distro(args.distro)
    source_dir = args.source_dir or distro.default_source_dir
    build_dir = args.build_dir or distro.default_build_dir
    output_dir = args.output_dir or Path("dist") / distro.name
    ignore_file = args.ignore_file or Path("ignore") / f"{distro.name}.txt"
    return GenerateConfig(
        distro=distro,
        source_dir=source_dir,
        build_dir=build_dir,
        output_dir=output_dir,
        ignore_file=ignore_file,
        output_format=args.output_format,
        limit=args.limit,
        target=args.target,
        resume=args.resume,
        fetch=args.fetch,
        retry_failures=args.retry_failures,
        font_size=args.font_size,
        skip_integrity=args.skip_integrity,
    )


def fetch_run(distro: Distro, dest: Path, top: int, update: bool) -> int:
    """Fetch ranking and cache packages. Return a process exit code."""
    packages: list[RankedPackage] = distro.refresh_ranking(dest)
    selected = select_top(packages, top)
    LOGGER.info(
        "Fetching the top %d of %d eligible packages", len(selected), len(packages)
    )
    failures = 0
    for index, package in enumerate(selected, start=1):
        status = distro.ensure_source(package.name, dest, update=update)
        LOGGER.info(
            "[%d/%d] %s %s (%d)",
            index,
            len(selected),
            status,
            package.name,
            package.votes,
        )
        if status == "failed":
            failures += 1
    return 1 if failures else 0


def run(config: GenerateConfig) -> int:
    """Run generate. Kept as a named entry for tests."""
    return run_generate(config)


def main(
    argv: list[str] | None = None,
    *,
    default_distro: str | None = None,
    default_command: str | None = None,
) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args(
        argv, default_distro=default_distro, default_command=default_command
    )
    if args.command == "fetch":
        distro = get_distro(args.distro)
        dest = args.dest or distro.host_cache_dir
        return fetch_run(distro, dest, args.top, args.update)
    return run(_config_from_args(args))


def archfonts_main(argv: list[str] | None = None) -> int:
    """Backward-compatible generate entry for Arch."""
    return main(argv, default_distro="archlinux", default_command="generate")


def archfonts_fetch_main(argv: list[str] | None = None) -> int:
    """Backward-compatible fetch entry for Arch."""
    return main(argv, default_distro="archlinux", default_command="fetch")


if __name__ == "__main__":
    raise SystemExit(main())
