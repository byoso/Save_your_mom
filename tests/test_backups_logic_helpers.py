from pathlib import Path

import pytest

import backups_logic as bl


@pytest.mark.parametrize(
    "raw_name, expected",
    [
        ("normal.txt", "normal.txt"),
        ("file<name>", "file_name_"),
        ("name|with*chars?", "name_with_chars_"),
        ("trail. ", "trail"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("", "_"),
    ],
)
def test_sanitize_for_fat(raw_name: str, expected: str):
    assert bl._sanitize_for_fat(raw_name) == expected


@pytest.mark.parametrize(
    "text, max_bytes, expected",
    [
        ("hello", 10, "hello"),
        ("hello", 3, "hel"),
        ("caf\u00e9", 5, "caf\u00e9"),
        ("caf\u00e9", 4, "caf"),
        ("\U0001F512secure", 4, "\U0001F512"),
        ("\U0001F512secure", 3, ""),
        ("test", 0, ""),
    ],
)
def test_truncate_utf8(text: str, max_bytes: int, expected: str):
    assert bl._truncate_utf8(text, max_bytes) == expected


def test_is_within_true_and_false(tmp_path: Path):
    parent = tmp_path / "parent"
    child = parent / "child"
    sibling = tmp_path / "sibling"
    child.mkdir(parents=True)
    sibling.mkdir(parents=True)

    assert bl._is_within(child, parent) is True
    assert bl._is_within(parent, parent) is True
    assert bl._is_within(sibling, parent) is False


@pytest.mark.parametrize(
    "source_rel, destination_rel, parent_guard_rel, expected_message",
    [
        ("src", "outside/dst", "guard", "must be inside"),
        ("src", "src", "", "Source and destination are identical"),
        ("src", "src/nested", "", "cannot be nested"),
        ("src/nested", "src", "", "cannot be nested"),
    ],
)
def test_prepare_destination_validation_errors(
    tmp_path: Path,
    source_rel: str,
    destination_rel: str,
    parent_guard_rel: str,
    expected_message: str,
):
    source = (tmp_path / source_rel).resolve()
    destination = (tmp_path / destination_rel).resolve()
    parent_guard = (tmp_path / parent_guard_rel).resolve() if parent_guard_rel else tmp_path.resolve()

    source.mkdir(parents=True, exist_ok=True)
    if parent_guard_rel:
        parent_guard.mkdir(parents=True, exist_ok=True)

    with pytest.raises(bl.BackupLogicError, match=expected_message):
        bl._prepare_destination(source, destination, parent_guard, merge_mode=True, destination_label="Target path")


def test_prepare_destination_creates_missing_directory(tmp_path: Path):
    source = tmp_path / "src"
    destination = tmp_path / "media" / "slot"
    parent_guard = tmp_path / "media"

    source.mkdir(parents=True)
    parent_guard.mkdir(parents=True)

    bl._prepare_destination(source, destination, parent_guard, merge_mode=True, destination_label="Target path")

    assert destination.exists()
    assert destination.is_dir()


def test_prepare_destination_legacy_mode_clears_existing_content(tmp_path: Path):
    source = tmp_path / "src"
    destination = tmp_path / "media" / "slot"
    parent_guard = tmp_path / "media"

    source.mkdir(parents=True)
    destination.mkdir(parents=True)
    parent_guard.mkdir(parents=True, exist_ok=True)
    (destination / "old.txt").write_text("old", encoding="utf-8")

    bl._prepare_destination(source, destination, parent_guard, merge_mode=False, destination_label="Target path")

    assert list(destination.iterdir()) == []
