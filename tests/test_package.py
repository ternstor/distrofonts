import tarfile
from pathlib import Path

import pytest

from archfonts.package import (
    ArchFontError,
    ArchFontPackage,
    discover_packages,
    existing_previews,
    find_archives,
    load_failures,
    load_ignore,
    makepkg_command,
)


def test_discover_packages_sorts_and_limits(tmp_path: Path) -> None:
    (tmp_path / "ttf-b").mkdir()
    (tmp_path / "ttf-a").mkdir()
    (tmp_path / "fonts").mkdir()
    (tmp_path / "ttf-file").write_text("not a directory", encoding="utf-8")

    assert [path.name for path in discover_packages(tmp_path, None)] == [
        "ttf-a",
        "ttf-b",
    ]
    assert [path.name for path in discover_packages(tmp_path, 1)] == ["ttf-a"]
    assert discover_packages(tmp_path, 0) == []


def test_existing_previews_and_failures(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    pkg = dist / "png" / "ttf-ok"
    pkg.mkdir(parents=True)
    (pkg / "a.png").write_bytes(b"x")
    (dist / "png" / "ttf-empty").mkdir()
    assert list(existing_previews(dist)) == ["ttf-ok"]
    (dist / "failures.txt").write_text("# note\n\nttf-bad\n", encoding="utf-8")
    assert load_failures(dist / "failures.txt") == ["ttf-bad"]


def test_load_ignore_merges_builtin_names(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    assert load_ignore(missing) == {"ttf-win10"}

    ignore = tmp_path / "ignore.txt"
    ignore.write_text("# comment\n\nttf-skip\n  ttf-other  \n", encoding="utf-8")
    assert load_ignore(ignore) == {"ttf-win10", "ttf-skip", "ttf-other"}


def test_find_archives_dedupes_formats(tmp_path: Path) -> None:
    zst = tmp_path / "ttf-demo-1.0-1-any.pkg.tar.zst"
    xz = tmp_path / "ttf-demo-1.0-1-any.pkg.tar.xz"
    gz = tmp_path / "ttf-demo-1.0-1-any.pkg.tar.gz"
    note = tmp_path / "README.txt"
    for path in (zst, xz, gz, note):
        path.write_bytes(b"x")

    found = find_archives(tmp_path)
    assert found == sorted([zst, xz, gz])
    assert len(found) == 3


def test_extract_xz_keeps_cwd(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "ttf-demo"
    pkg_dir.mkdir()
    stage = tmp_path / "stage" / "usr" / "share" / "fonts"
    stage.mkdir(parents=True)
    (stage / "a.ttf").write_bytes(b"fake-ttf")
    archive = pkg_dir / "ttf-demo-1.0-1-any.pkg.tar.xz"
    with tarfile.open(archive, "w:xz") as tar:
        tar.add(tmp_path / "stage" / "usr", arcname="usr")

    package = ArchFontPackage(pkg_dir, font_size=20, skip_integrity=False)
    cwd = Path.cwd()
    package.extract()
    assert Path.cwd() == cwd
    (pkg_dir / "src-copy.ttf").write_bytes(b"duplicate")
    assert [path.name for path in package.find_ttfs()] == ["a.ttf"]


def test_extract_without_archive_raises(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "ttf-empty"
    pkg_dir.mkdir()
    package = ArchFontPackage(pkg_dir, font_size=20, skip_integrity=False)
    with pytest.raises(ArchFontError, match="no package archive"):
        package.extract()


def test_copy_to_twice(tmp_path: Path) -> None:
    source = tmp_path / "src" / "ttf-demo"
    source.mkdir(parents=True)
    (source / "PKGBUILD").write_text("pkgname=ttf-demo\n", encoding="utf-8")
    dest = tmp_path / "build" / "ttf-demo"
    package = ArchFontPackage(source, font_size=20, skip_integrity=False)

    package.copy_to(dest)
    package.copy_to(dest)

    assert (dest / "PKGBUILD").read_text(encoding="utf-8") == "pkgname=ttf-demo\n"
    assert package.pkg_dir == dest
    assert package.source_dir == source


def test_makepkg_command_skips_integrity_only_when_asked() -> None:
    base = makepkg_command(False)
    assert "--skipchecksums" not in base
    assert "--skipinteg" not in base
    assert "--skippgpcheck" not in base

    skipped = makepkg_command(True)
    assert skipped[-3:] == ["--skipchecksums", "--skipinteg", "--skippgpcheck"]
    assert skipped[:6] == [
        "makepkg",
        "--force",
        "--syncdeps",
        "--ignorearch",
        "--nocolor",
        "--noconfirm",
    ]
