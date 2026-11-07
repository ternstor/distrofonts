from pathlib import Path

from distrofonts.pipeline import GenerateConfig, run
from distrofonts.process import FontError
from distrofonts.ranking import RankedPackage, write_ranking


class FakeDebian:
    """Minimal Debian-like adapter for pipeline tests."""

    name = "debian"
    display_name = "Debian fonts"
    default_source_dir = Path("/var/debian")
    default_build_dir = Path("/tmp/distrofonts")
    host_cache_dir = Path("debian")
    builtin_ignore: frozenset[str] = frozenset()

    def is_proprietary(self, name: str) -> bool:
        return name.endswith("-installer")

    def refresh_ranking(self, dest: Path) -> list[RankedPackage]:
        packages = [
            RankedPackage("fonts-bad", 5),
            RankedPackage("fonts-ok", 4),
            RankedPackage("fonts-broken", 3),
            RankedPackage("fonts-late", 2),
            RankedPackage("ttf-mscorefonts-installer", 1),
        ]
        write_ranking(dest / "ranking.json", packages)
        return packages

    def discover_names(self, dest: Path) -> list[str]:
        if not dest.is_dir():
            return []
        return sorted(
            path.name
            for path in dest.iterdir()
            if path.is_dir() and path.name.startswith(("fonts-", "ttf-"))
        )

    def has_source(self, dest: Path, name: str) -> bool:
        return (dest / name / f"{name}.deb").is_file()

    def ensure_source(self, name: str, dest: Path, *, update: bool = False) -> str:
        del update
        if name == "fonts-missing":
            return "failed"
        pkg_dir = dest / name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / f"{name}.deb").write_bytes(b"deb")
        return "downloaded"

    def materialize(
        self,
        name: str,
        source_dir: Path,
        build_dir: Path,
        *,
        skip_integrity: bool = False,
    ) -> Path:
        del skip_integrity
        if name == "fonts-bad":
            raise FontError("dpkg-deb failed")
        if name == "fonts-broken":
            raise FontError("no TTF files")
        extracted = build_dir / name
        extracted.mkdir(parents=True, exist_ok=True)
        (extracted / "font.ttf").write_bytes(b"font")
        return extracted

    def find_ttfs(self, extracted: Path) -> list[Path]:
        return sorted(extracted.glob("*.ttf"))


def test_pipeline_fills_target_despite_debian_failures(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "debian"
    source.mkdir()
    png = tmp_path / "font.ttf.png"
    png.write_bytes(b"png")
    distro = FakeDebian()
    config = GenerateConfig(
        distro=distro,
        source_dir=source,
        build_dir=tmp_path / "build",
        output_dir=tmp_path / "dist",
        ignore_file=tmp_path / "ignore.txt",
        output_format="html",
        limit=None,
        target=2,
        resume=False,
        fetch=True,
        retry_failures=False,
        font_size=20,
        skip_integrity=False,
    )
    monkeypatch.setattr("distrofonts.pipeline.render_ttf", lambda ttf, font_size: png)
    monkeypatch.setattr("distrofonts.pipeline.trim_png", lambda path: None)

    assert run(config) == 0
    text = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert "<title>Debian fonts</title>" in text
    assert text.find("fonts-ok") < text.find("fonts-late")
    assert "fonts-bad" not in text
    assert "fonts-broken" not in text
    assert "ttf-mscorefonts-installer" not in text
    failures = (tmp_path / "dist" / "failures.txt").read_text(encoding="utf-8")
    assert failures == "fonts-bad\nfonts-broken\n"
    assert distro.has_source(source, "fonts-ok")
    assert distro.has_source(source, "fonts-late")
