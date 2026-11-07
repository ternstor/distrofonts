from pathlib import Path

import pytest

from distrofonts.cli import parse_generate_args
from distrofonts.pipeline import run
from distrofonts.process import FontError
from distrofonts.ranking import RankedPackage, write_ranking


def test_parse_args_defaults() -> None:
    config = parse_generate_args([])
    assert config.distro.name == "archlinux"
    assert config.source_dir == Path("/var/aur")
    assert config.build_dir == Path("/tmp/distrofonts")
    assert config.output_dir == Path("dist/archlinux")
    assert config.ignore_file == Path("ignore/archlinux.txt")
    assert config.output_format == "html"
    assert config.limit is None
    assert config.target == 100
    assert config.resume is True
    assert config.fetch is False
    assert config.retry_failures is False
    assert config.font_size == 20
    assert config.skip_integrity is False


def test_parse_args_debian_defaults() -> None:
    config = parse_generate_args(["--distro", "debian"])
    assert config.distro.name == "debian"
    assert config.source_dir == Path("/var/debian")
    assert config.output_dir == Path("dist/debian")
    assert config.ignore_file == Path("ignore/debian.txt")


def test_parse_args_flags() -> None:
    config = parse_generate_args(
        [
            "--source-dir",
            "/aur",
            "--build-dir",
            "/tmp/build",
            "--output-dir",
            "out",
            "--ignore-file",
            "skip.txt",
            "--limit",
            "2",
            "--target",
            "50",
            "--no-resume",
            "--fetch",
            "--retry-failures",
            "--font-size",
            "16",
            "--skip-integrity",
            "-o",
            "html",
        ]
    )
    assert config.source_dir == Path("/aur")
    assert config.build_dir == Path("/tmp/build")
    assert config.output_dir == Path("out")
    assert config.ignore_file == Path("skip.txt")
    assert config.limit == 2
    assert config.target == 50
    assert config.resume is False
    assert config.fetch is True
    assert config.retry_failures is True
    assert config.font_size == 16
    assert config.skip_integrity is True


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch, config, source: Path, png: Path
) -> None:
    def fake_materialize(
        name: str,
        source_dir: Path,
        build_dir: Path,
        *,
        skip_integrity: bool = False,
    ) -> Path:
        del source_dir, build_dir, skip_integrity
        if name == "ttf-bad":
            raise FontError("makepkg failed")
        if name == "ttf-broken":
            raise FontError("no package archive")
        return source / name

    monkeypatch.setattr(config.distro, "materialize", fake_materialize)
    monkeypatch.setattr(
        config.distro, "find_ttfs", lambda extracted: [extracted / "font.ttf"]
    )
    monkeypatch.setattr("distrofonts.pipeline.render_ttf", lambda ttf, font_size: png)
    monkeypatch.setattr("distrofonts.pipeline.trim_png", lambda path: None)


def test_run_writes_index_and_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "aur"
    for name in (
        "ttf-ok",
        "ttf-bad",
        "ttf-broken",
        "ttf-skip",
        "ttf-win10",
        "ttf-late",
    ):
        (source / name).mkdir(parents=True)
        (source / name / "PKGBUILD").write_text(f"pkgname={name}\n", encoding="utf-8")
    (source / "ranking.json").write_text(
        '[{"name": "ttf-bad", "votes": 4}, {"name": "ttf-broken", "votes": 3},'
        '{"name": "ttf-late", "votes": 2}, {"name": "ttf-ok", "votes": 1}]\n',
        encoding="utf-8",
    )
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("ttf-skip\n", encoding="utf-8")
    original_ignore = ignore.read_text(encoding="utf-8")
    png = tmp_path / "preview.ttf.png"
    png.write_bytes(b"png")

    config = parse_generate_args(
        [
            "--source-dir",
            str(source),
            "--build-dir",
            str(tmp_path / "build"),
            "--output-dir",
            str(tmp_path / "dist"),
            "--ignore-file",
            str(ignore),
            "--target",
            "2",
        ]
    )
    _patch_pipeline(monkeypatch, config, source, png)
    assert run(config) == 0

    index = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert index.find("ttf-late") < index.find("ttf-ok")
    assert "ttf-ok" in index
    assert "ttf-bad" not in index
    assert "ttf-broken" not in index
    assert "ttf-skip" not in index
    assert "ttf-win10" not in index
    assert "<title>Arch fonts</title>" in index
    failures = (tmp_path / "dist" / "failures.txt").read_text(encoding="utf-8")
    assert failures == "ttf-bad\nttf-broken\n"
    assert ignore.read_text(encoding="utf-8") == original_ignore
    assert (tmp_path / "dist" / "png" / "ttf-ok" / "preview.ttf.png").is_file()


def test_run_resumes_and_fills_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "aur"
    for name in ("ttf-old", "ttf-bad", "ttf-new"):
        (source / name).mkdir(parents=True)
        (source / name / "PKGBUILD").write_text(f"pkgname={name}\n", encoding="utf-8")
    (source / "ranking.json").write_text(
        '[{"name":"ttf-old","votes":3},{"name":"ttf-bad","votes":2},'
        '{"name":"ttf-new","votes":1}]\n',
        encoding="utf-8",
    )
    dist = tmp_path / "dist"
    existing = dist / "png" / "ttf-old"
    existing.mkdir(parents=True)
    (existing / "old.png").write_bytes(b"old")
    (dist / "failures.txt").write_text("ttf-bad\n", encoding="utf-8")
    png = tmp_path / "preview.ttf.png"
    png.write_bytes(b"png")
    built: list[str] = []

    config = parse_generate_args(
        [
            "--source-dir",
            str(source),
            "--build-dir",
            str(tmp_path / "build"),
            "--output-dir",
            str(dist),
            "--ignore-file",
            str(tmp_path / "ignore.txt"),
            "--target",
            "2",
            "--resume",
        ]
    )

    def fake_materialize(
        name: str,
        source_dir: Path,
        build_dir: Path,
        *,
        skip_integrity: bool = False,
    ) -> Path:
        del source_dir, build_dir, skip_integrity
        built.append(name)
        if name == "ttf-bad":
            raise FontError("makepkg failed")
        return source / name

    monkeypatch.setattr(config.distro, "materialize", fake_materialize)
    monkeypatch.setattr(
        config.distro, "find_ttfs", lambda extracted: [extracted / "font.ttf"]
    )
    monkeypatch.setattr("distrofonts.pipeline.render_ttf", lambda ttf, font_size: png)
    monkeypatch.setattr("distrofonts.pipeline.trim_png", lambda path: None)

    assert run(config) == 0
    assert built == ["ttf-new"]
    text = (dist / "index.html").read_text(encoding="utf-8")
    assert text.find("ttf-old") < text.find("ttf-new")
    assert "ttf-bad" not in text
    assert (dist / "failures.txt").read_text(encoding="utf-8") == "ttf-bad\n"


def test_run_fetch_clones_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "aur"
    source.mkdir()
    png = tmp_path / "preview.ttf.png"
    png.write_bytes(b"png")
    cloned: list[str] = []

    config = parse_generate_args(
        [
            "--source-dir",
            str(source),
            "--build-dir",
            str(tmp_path / "build"),
            "--output-dir",
            str(tmp_path / "dist"),
            "--target",
            "1",
            "--fetch",
            "--no-resume",
        ]
    )

    def fake_refresh(dest: Path):
        packages = [RankedPackage("ttf-cloned", 9)]
        write_ranking(dest / "ranking.json", packages)
        return packages

    def fake_clone(name: str, dest: Path, *, update: bool = False) -> str:
        del update
        cloned.append(name)
        (dest / name).mkdir()
        (dest / name / ".git").mkdir()
        (dest / name / "PKGBUILD").write_text("pkgname=ttf-cloned\n", encoding="utf-8")
        return "cloned"

    monkeypatch.setattr(config.distro, "refresh_ranking", fake_refresh)
    monkeypatch.setattr(config.distro, "ensure_source", fake_clone)
    monkeypatch.setattr(
        config.distro, "materialize", lambda *a, **k: source / "ttf-cloned"
    )
    monkeypatch.setattr(
        config.distro, "find_ttfs", lambda extracted: [extracted / "font.ttf"]
    )
    monkeypatch.setattr("distrofonts.pipeline.render_ttf", lambda ttf, font_size: png)
    monkeypatch.setattr("distrofonts.pipeline.trim_png", lambda path: None)

    assert run(config) == 0
    assert cloned == ["ttf-cloned"]
    assert "ttf-cloned" in (tmp_path / "dist" / "index.html").read_text(
        encoding="utf-8"
    )


def test_run_records_missing_pkgbuild(tmp_path: Path) -> None:
    source = tmp_path / "aur"
    (source / "ttf-empty").mkdir(parents=True)
    (source / "ranking.json").write_text(
        '[{"name":"ttf-empty","votes":1}]\n',
        encoding="utf-8",
    )
    dist = tmp_path / "dist"
    config = parse_generate_args(
        [
            "--source-dir",
            str(source),
            "--output-dir",
            str(dist),
            "--ignore-file",
            str(tmp_path / "ignore.txt"),
            "--target",
            "1",
            "--no-fetch",
        ]
    )
    assert run(config) == 1
    assert (dist / "failures.txt").read_text(encoding="utf-8") == "ttf-empty\n"


def test_run_missing_source_returns_error(tmp_path: Path) -> None:
    config = parse_generate_args(
        [
            "--source-dir",
            str(tmp_path / "missing"),
            "--output-dir",
            str(tmp_path / "dist"),
            "--ignore-file",
            str(tmp_path / "ignore.txt"),
            "--no-fetch",
        ]
    )
    assert run(config) == 1
    assert not (tmp_path / "dist" / "index.html").exists()
