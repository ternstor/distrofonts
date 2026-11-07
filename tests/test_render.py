import subprocess
from pathlib import Path

import pytest

from distrofonts.process import FontError
from distrofonts.render import render_ttf, trim_command, trim_png


def test_render_ttf_uses_font_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert cwd == tmp_path
        assert capture_output and text and not check
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("distrofonts.process.subprocess.run", fake_run)
    ttf = tmp_path / "a.ttf"
    ttf.write_bytes(b"font")

    assert render_ttf(ttf, 32) == Path(str(ttf) + ".png")
    assert commands == [["ttf2png", "-s", "32", "-o", str(ttf) + ".png", str(ttf)]]


def test_render_ttf_failure_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        command: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "boom")

    monkeypatch.setattr("distrofonts.process.subprocess.run", fake_run)
    ttf = tmp_path / "a.ttf"
    ttf.write_bytes(b"font")
    assert render_ttf(ttf, 20) is None


def test_trim_command_prefers_magick(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def which(name: str) -> str | None:
        if name == "magick":
            return "/usr/bin/magick"
        return "/usr/bin/convert"

    monkeypatch.setattr("distrofonts.render.shutil.which", which)
    png = tmp_path / "a.png"
    assert trim_command(png) == ["/usr/bin/magick", str(png), "-trim", str(png)]


def test_trim_command_falls_back_to_convert(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def which(name: str) -> str | None:
        if name == "convert":
            return "/usr/bin/convert"
        return None

    monkeypatch.setattr("distrofonts.render.shutil.which", which)
    png = tmp_path / "a.png"
    assert trim_command(png) == ["/usr/bin/convert", "-trim", str(png), str(png)]


def test_trim_command_requires_imagemagick(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("distrofonts.render.shutil.which", lambda name: None)
    with pytest.raises(FontError, match="ImageMagick not found"):
        trim_command(tmp_path / "a.png")


def test_trim_png_runs_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    png = tmp_path / "a.png"
    png.write_bytes(b"png")
    seen: list[list[str]] = []

    monkeypatch.setattr(
        "distrofonts.render.trim_command",
        lambda path: ["magick", str(path), "-trim", str(path)],
    )

    def fake_run(
        command: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("distrofonts.process.subprocess.run", fake_run)
    trim_png(png)
    assert seen == [["magick", str(png), "-trim", str(png)]]
