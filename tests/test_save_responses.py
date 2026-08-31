"""Tests for CLI save_responses."""
from __future__ import annotations

from pathlib import Path

from librelyrics.cli import save_responses
from librelyrics.config import get_default_config
from librelyrics.models import LyricsLine, LyricsResponse


def _response(title: str, track_number: int = 1) -> LyricsResponse:
    return LyricsResponse(
        title=title,
        artist="Test Artist",
        album="Test Album",
        lyrics=[LyricsLine(text="hello", start_ms=0)],
        source="Test",
        synced=True,
        metadata={"track_number": track_number},
    )


def test_save_responses_writes_lrc(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    successful, failed, skipped, path = save_responses(
        [_response("Song One")],
        config,
    )
    assert successful == ["Song One"]
    assert failed == []
    assert skipped == []
    assert (Path(path) / "01. Song One.lrc").exists()


def test_save_responses_skips_existing(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    save_responses([_response("Song One")], config)
    successful, failed, skipped, _ = save_responses([_response("Song One")], config)
    assert successful == []
    assert skipped == ["Song One"]
    assert failed == []


def test_save_responses_force_overwrites(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    config["force_download"] = True
    save_responses([_response("Song One")], config)
    successful, _, skipped, _ = save_responses([_response("Song One")], config)
    assert successful == ["Song One"]
    assert skipped == []


def test_save_responses_uses_album_folder(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    config["create_folder"] = True
    _, _, _, path = save_responses(
        [_response("Track")],
        config,
        folder_name="My Album",
    )
    assert (Path(path) / "01. Track.lrc").exists()


def test_save_responses_flat_when_no_folder(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    config["create_folder"] = False
    _, _, _, path = save_responses(
        [_response("Track")],
        config,
        folder_name="Ignored",
    )
    assert path == str(tmp_path)
    assert (tmp_path / "01. Track.lrc").exists()


def test_save_responses_sanitizes_invalid_filename_chars(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    config["file_name"] = "{name}"
    response = _response("Bad:Name?")
    save_responses([response], config)
    files = list(tmp_path.glob("*.lrc"))
    assert len(files) == 1
    assert ":" not in files[0].name
    assert "?" not in files[0].name


def test_save_responses_empty_list(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    successful, failed, skipped, path = save_responses([], config)
    assert successful == []
    assert path == str(tmp_path)


def test_save_responses_album_tag_overrides_lrc_album(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    save_responses(
        [_response("Track")],
        config,
        album_tag="x (Deluxe Edition)",
    )
    content = (tmp_path / "01. Track.lrc").read_text(encoding="utf-8")
    assert "[al:x (Deluxe Edition)]" in content


def test_save_responses_uniquifies_same_run_collisions(tmp_path: Path) -> None:
    config = get_default_config()
    config["download_path"] = str(tmp_path)
    config["file_name"] = "{name}"
    a = _response("Same", track_number=0)
    b = _response("Same", track_number=0)
    b.title = "Same"
    successful, _, skipped, _ = save_responses([a, b], config)
    assert successful == ["Same", "Same"]
    assert skipped == []
    names = sorted(p.name for p in tmp_path.glob("*.lrc"))
    assert names == ["Same (2).lrc", "Same.lrc"]
