import tarfile
from pathlib import Path

import pytest

from distrofonts.distros.archlinux import (
    ArchlinuxDistro,
    find_archives,
    makepkg_command,
)
from distrofonts.pipeline import existing_previews, load_failures, load_ignore
from distrofonts.process import FontError


def test_discover_packages_sorts(tmp_path: Path) -> None:
    (tmp_path / "ttf-b").mkdir()
    (tmp_path / "ttf-a").mkdir()
    (tmp_path / "fonts").mkdir()
    (tmp_path / "ttf-file").write_text("not a directory", encoding="utf-8")
    distro = ArchlinuxDistro()
    assert distro.discover_names(tmp_path) == ["ttf-a", "ttf-b"]


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
    assert load_ignore(missing, {"ttf-win10"}) == {"ttf-win10"}

    ignore = tmp_path / "ignore.txt"
    ignore.write_text("# comment\n\nttf-skip\n  ttf-other  \n", encoding="utf-8")
    assert load_ignore(ignore, {"ttf-win10"}) == {"ttf-win10", "ttf-skip", "ttf-other"}


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
    (pkg_dir / "PKGBUILD").write_text("pkgname=ttf-demo\n", encoding="utf-8")
    stage = tmp_path / "stage" / "usr" / "share" / "fonts"
    stage.mkdir(parents=True)
    (stage / "a.ttf").write_bytes(b"fake-ttf")
    archive = pkg_dir / "ttf-demo-1.0-1-any.pkg.tar.xz"
    with tarfile.open(archive, "w:xz") as tar:
        tar.add(tmp_path / "stage" / "usr", arcname="usr")

    distro = ArchlinuxDistro()
    cwd = Path.cwd()

    def fake_makepkg(command: list[str], cwd: Path, logger: object) -> int:
        del command, cwd, logger
        return 0

    import distrofonts.distros.archlinux as arch

    original = arch.run_command
    arch.run_command = fake_makepkg  # type: ignore[assignment]
    try:
        extracted = distro.materialize(
            "ttf-demo", tmp_path, tmp_path / "build", skip_integrity=False
        )
    finally:
        arch.run_command = original
    assert Path.cwd() == cwd
    (extracted / "src-copy.ttf").write_bytes(b"duplicate")
    assert [path.name for path in distro.find_ttfs(extracted)] == ["a.ttf"]


def test_extract_without_archive_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_dir = tmp_path / "ttf-empty"
    pkg_dir.mkdir()
    (pkg_dir / "PKGBUILD").write_text("pkgname=ttf-empty\n", encoding="utf-8")
    distro = ArchlinuxDistro()
    monkeypatch.setattr(
        "distrofonts.distros.archlinux.run_command", lambda *args, **kwargs: 0
    )
    with pytest.raises(FontError, match="no package archive"):
        distro.materialize("ttf-empty", tmp_path, tmp_path / "build")


def test_copy_to_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "src" / "ttf-demo"
    source.mkdir(parents=True)
    (source / "PKGBUILD").write_text("pkgname=ttf-demo\n", encoding="utf-8")
    archive_dir = tmp_path / "build" / "ttf-demo"
    distro = ArchlinuxDistro()

    def fake_run(command: list[str], cwd: Path, logger: object) -> int:
        del command, logger
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / "ttf-demo-1.0-1-any.pkg.tar.xz").write_bytes(b"x")
        return 0

    monkeypatch.setattr("distrofonts.distros.archlinux.run_command", fake_run)
    monkeypatch.setattr(
        "distrofonts.distros.archlinux.extract_archive", lambda archive, dest: None
    )
    distro.materialize("ttf-demo", source.parent, tmp_path / "build")
    distro.materialize("ttf-demo", source.parent, tmp_path / "build")
    pkgbuild = (archive_dir / "PKGBUILD").read_text(encoding="utf-8")
    assert pkgbuild == "pkgname=ttf-demo\n"


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
