from datetime import UTC, datetime
from pathlib import Path

from archfonts.html import write_index


def test_write_index_escapes_names_and_copies_pngs(tmp_path: Path) -> None:
    source = tmp_path / "build" / "a.png"
    source.parent.mkdir()
    source.write_bytes(b"png-bytes")
    output = tmp_path / "dist"

    index = write_index(
        {"<script>": [source]},
        output,
        generated_at=datetime(2026, 11, 5, 7, 0, tzinfo=UTC),
    )
    text = index.read_text(encoding="utf-8")

    assert index == output / "index.html"
    assert "<h2>&lt;script&gt;</h2>" in text
    assert "<script>" not in text
    assert 'src="png/%3Cscript%3E/a.png"' in text
    assert 'alt="a.png"' in text
    assert "localhost" not in text
    assert "/var/aur" not in text
    assert "Generated 2026-11-05 07:00 UTC." in text
    assert text.count('src="png/%3Cscript%3E/a.png"') == 1
    copied = output / "png" / "<script>" / "a.png"
    assert copied.read_bytes() == b"png-bytes"
    assert "<!DOCTYPE html>" in text
    assert 'lang="en"' in text
    assert "background: #fff" in text
    assert "color: #111" in text
    assert (output / ".nojekyll").is_file()


def test_write_index_keeps_mapping_order(tmp_path: Path) -> None:
    png = tmp_path / "a.png"
    png.write_bytes(b"png")
    output = tmp_path / "dist"
    text = write_index(
        {"ttf-b": [png], "ttf-a": [png]},
        output,
        generated_at=datetime(2026, 11, 5, tzinfo=UTC),
    ).read_text(encoding="utf-8")
    assert text.find("ttf-b") < text.find("ttf-a")


def test_write_index_allows_in_place_pngs(tmp_path: Path) -> None:
    dest = tmp_path / "dist" / "png" / "ttf-demo"
    dest.mkdir(parents=True)
    png = dest / "a.png"
    png.write_bytes(b"png")
    write_index({"ttf-demo": [png]}, tmp_path / "dist")
    assert png.read_bytes() == b"png"
