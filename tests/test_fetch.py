import json
import subprocess
from pathlib import Path

import pytest

from archfonts.fetch import (
    AurPackage,
    clone_package,
    is_proprietary,
    load_ranking,
    order_by_ranking,
    parse_search_results,
    ranking_payload,
    select_top,
    write_ranking,
)


def test_is_proprietary() -> None:
    assert is_proprietary("ttf-ms-fonts")
    assert is_proprietary("ttf-ms-win11-auto")
    assert is_proprietary("ttf-win7-fonts")
    assert is_proprietary("ttf-vista-fonts")
    assert is_proprietary("ttf-mac-fonts")
    assert is_proprietary("ttf-apple-emoji")
    assert is_proprietary("ttf-wps-fonts")
    assert is_proprietary("ttf-office-2007-fonts")
    assert is_proprietary("ttf-tahoma")
    assert not is_proprietary("ttf-iosevka")
    assert not is_proprietary("ttf-google-fonts-git")


def test_parse_search_results_filters_and_sorts() -> None:
    payload = {
        "results": [
            {"Name": "otf-other", "NumVotes": 999},
            {"Name": "ttf-ms-fonts", "NumVotes": 2193},
            {"Name": "ttf-b", "NumVotes": 10},
            {"Name": "ttf-a", "NumVotes": 10},
            {"Name": "ttf-iosevka", "NumVotes": 142},
        ]
    }
    packages = parse_search_results(payload)
    assert [pkg.name for pkg in packages] == ["ttf-iosevka", "ttf-a", "ttf-b"]
    assert packages[0].votes == 142


def test_select_top_and_ranking_roundtrip(tmp_path: Path) -> None:
    packages = [
        AurPackage("ttf-a", 5),
        AurPackage("ttf-b", 4),
        AurPackage("ttf-c", 3),
    ]
    selected = select_top(packages, 2)
    assert [pkg.name for pkg in selected] == ["ttf-a", "ttf-b"]
    path = tmp_path / "ranking.json"
    write_ranking(path, selected)
    assert json.loads(path.read_text(encoding="utf-8")) == ranking_payload(selected)
    assert load_ranking(path) == ["ttf-a", "ttf-b"]
    assert load_ranking(tmp_path / "missing.json") == []


def test_order_by_ranking(tmp_path: Path) -> None:
    for name in ("ttf-a", "ttf-b", "ttf-c"):
        (tmp_path / name).mkdir()
    packages = [tmp_path / "ttf-a", tmp_path / "ttf-c", tmp_path / "ttf-b"]
    ordered = order_by_ranking(packages, ["ttf-c", "ttf-missing", "ttf-a"])
    assert [path.name for path in ordered] == ["ttf-c", "ttf-a", "ttf-b"]


def test_clone_package_skips_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "ttf-demo"
    (repo / ".git").mkdir(parents=True)
    (repo / "PKGBUILD").write_text("pkgname=ttf-demo\n", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("git should not run when skipping")

    monkeypatch.setattr("archfonts.fetch.subprocess.run", fake_run)
    assert clone_package("ttf-demo", tmp_path, update=False) == "skipped"


def test_clone_package_clones_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        command: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["git", "clone", "--depth"]
        dest = Path(command[-1])
        dest.mkdir()
        (dest / ".git").mkdir()
        (dest / "PKGBUILD").write_text("pkgname=ttf-demo\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("archfonts.fetch.subprocess.run", fake_run)
    assert clone_package("ttf-demo", tmp_path, update=False) == "cloned"
    assert (tmp_path / "ttf-demo" / "PKGBUILD").is_file()


def test_clone_package_rejects_empty_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        command: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        dest = Path(command[-1])
        dest.mkdir()
        (dest / ".git").mkdir()
        return subprocess.CompletedProcess(
            command, 0, "", "warning: cloned an empty repository.\n"
        )

    monkeypatch.setattr("archfonts.fetch.subprocess.run", fake_run)
    assert clone_package("ttf-empty", tmp_path, update=False) == "failed"
    assert not (tmp_path / "ttf-empty").exists()


def test_clone_package_reclones_broken(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "ttf-demo"
    (repo / ".git").mkdir(parents=True)

    def fake_run(
        command: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        dest = Path(command[-1])
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".git").mkdir(exist_ok=True)
        (dest / "PKGBUILD").write_text("pkgname=ttf-demo\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("archfonts.fetch.subprocess.run", fake_run)
    assert clone_package("ttf-demo", tmp_path, update=False) == "cloned"
    assert (repo / "PKGBUILD").is_file()
