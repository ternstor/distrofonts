from pathlib import Path

from distrofonts.distros.debian import (
    DebianDistro,
    is_font_package,
    is_proprietary,
    parse_popcon,
)


def test_is_font_package_and_proprietary() -> None:
    assert is_font_package("fonts-dejavu-core")
    assert is_font_package("ttf-bitstream-vera")
    assert not is_font_package("libreoffice")
    assert is_proprietary("ttf-mscorefonts-installer")
    assert is_proprietary("fonts-foo-installer")
    assert not is_proprietary("fonts-liberation")


def test_parse_popcon_filters_and_sorts() -> None:
    text = """\
#rank name inst vote old recent no-files (maintainer)
1     bash                           9000 8000 1 1 0 (Someone)
2     fonts-b                        500 400 1 1 0 (Foo Bar)
3     fonts-a                        800 700 1 1 0 (Foo)
4     ttf-mscorefonts-installer      9999 1 1 1 0 (Installer)
5     ttf-bitstream-vera             100 90 1 1 0 (Vera)
6     fonts-a-installer              50 40 1 1 0 (Skip)
7     fonts-skip                     not-a-number 1 1 1 0 (Bad)
"""
    packages = parse_popcon(text)
    assert [pkg.name for pkg in packages] == [
        "fonts-a",
        "fonts-b",
        "ttf-bitstream-vera",
    ]
    assert packages[0].votes == 800
    assert packages[2].votes == 100


def test_debian_discover_and_has_source(tmp_path: Path) -> None:
    distro = DebianDistro()
    (tmp_path / "fonts-ok").mkdir()
    (tmp_path / "fonts-ok" / "fonts-ok_1_all.deb").write_bytes(b"deb")
    (tmp_path / "ttf-old").mkdir()
    (tmp_path / "not-a-font").mkdir()
    assert distro.discover_names(tmp_path) == ["fonts-ok", "ttf-old"]
    assert distro.has_source(tmp_path, "fonts-ok")
    assert not distro.has_source(tmp_path, "ttf-old")
