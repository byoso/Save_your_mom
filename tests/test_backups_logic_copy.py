from pathlib import Path

import pytest

import backups_logic as bl


def test_copy_local_to_target_copies_files_and_skips_metadata_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source"
    media_root = tmp_path / "media"
    target = media_root / "save_a"

    (source / "sub").mkdir(parents=True)
    (source / "sub" / "data.txt").write_text("payload", encoding="utf-8")
    (source / ".save_your_mom").mkdir(parents=True)
    (source / ".save_your_mom" / "hidden.txt").write_text("metadata", encoding="utf-8")

    (media_root / ".save_your_mom").mkdir(parents=True)

    monkeypatch.setattr(bl, "_is_case_sensitive_fs", lambda _path: True)

    incidents = bl.copy_local_to_target(str(source), str(target), str(media_root))

    assert incidents == []
    assert (target / "sub" / "data.txt").read_text(encoding="utf-8") == "payload"
    assert not (target / ".save_your_mom").exists()


def test_copy_local_to_target_empty_target_path_raises_error(tmp_path: Path):
    source = tmp_path / "source"
    media_root = tmp_path / "media"
    source.mkdir(parents=True)
    media_root.mkdir(parents=True)

    with pytest.raises(bl.BackupLogicError, match="Target path must be inside"):
        bl.copy_local_to_target(str(source), "", str(media_root))


@pytest.mark.parametrize("merge_mode", [True, False])
def test_copy_target_to_local_creates_destination_and_copies_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    merge_mode: bool,
):
    source = tmp_path / "media" / "save_src"
    destination = tmp_path / "pc" / "local_slot"

    (source / "folder").mkdir(parents=True)
    (source / "folder" / "save.dat").write_text("abc", encoding="utf-8")

    monkeypatch.setattr(bl, "_is_case_sensitive_fs", lambda _path: True)

    incidents = bl.copy_target_to_local(
        target_path=str(source),
        local_path=str(destination),
        user_home=str(tmp_path),
        merge_mode=merge_mode,
    )

    assert incidents == []
    assert (destination / "folder" / "save.dat").read_text(encoding="utf-8") == "abc"


def test_copy_target_to_local_missing_source_raises_error(tmp_path: Path):
    missing_source = tmp_path / "missing"
    destination = tmp_path / "pc" / "local_slot"

    with pytest.raises(bl.BackupLogicError, match="Source path does not exist"):
        bl.copy_target_to_local(
            target_path=str(missing_source),
            local_path=str(destination),
            user_home=str(tmp_path),
        )
