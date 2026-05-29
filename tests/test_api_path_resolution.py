from pathlib import Path
from types import SimpleNamespace

import pytest

import api


@pytest.mark.parametrize(
    "path_inside_home, expected_prefix",
    [
        ("games/save1", "~/games/save1"),
        ("docs", "~/docs"),
    ],
)
def test_normalize_for_storage_inside_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_inside_home: str,
    expected_prefix: str,
):
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True)

    monkeypatch.setattr(api.Path, "home", lambda: fake_home)

    raw_path = fake_home / path_inside_home
    normalized = api._normalize_for_storage(raw_path)

    assert normalized == expected_prefix


def test_normalize_for_storage_outside_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True)
    outside = tmp_path / "outside" / "save"

    monkeypatch.setattr(api.Path, "home", lambda: fake_home)

    assert api._normalize_for_storage(outside) == str(outside)


@pytest.mark.parametrize(
    "target_rel, expected",
    [
        (".", "."),
        ("slot_a", "slot_a"),
        ("folder/slot_b", "folder/slot_b"),
    ],
)
def test_to_target_rel_path_for_paths_inside_media_root(tmp_path: Path, target_rel: str, expected: str):
    media_root = (tmp_path / "media").resolve()
    media_root.mkdir(parents=True)

    if target_rel == ".":
        target_abs = media_root
    else:
        target_abs = (media_root / target_rel).resolve()

    assert api._to_target_rel_path(media_root, target_abs) == expected


def test_to_target_rel_path_outside_media_root_returns_absolute(tmp_path: Path):
    media_root = (tmp_path / "media").resolve()
    outside = (tmp_path / "outside" / "slot_x").resolve()

    media_root.mkdir(parents=True)

    assert api._to_target_rel_path(media_root, outside) == str(outside)


@pytest.mark.parametrize(
    "save_fields, expected_builder",
    [
        ({"target_rel_path": ".", "target_path": ""}, lambda root: str(root)),
        ({"target_rel_path": "slots/s1", "target_path": ""}, lambda root: str(root / "slots" / "s1")),
        ({"target_rel_path": "/tmp/absolute_slot", "target_path": ""}, lambda _root: "/tmp/absolute_slot"),
    ],
)
def test_resolve_target_abs_prefers_target_rel_path(tmp_path: Path, save_fields: dict, expected_builder):
    media_root = (tmp_path / "media").resolve()
    media_root.mkdir(parents=True)

    save = SimpleNamespace(**save_fields)

    assert api._resolve_target_abs(media_root, save) == expected_builder(media_root)


def test_resolve_target_abs_falls_back_to_legacy_target_path(tmp_path: Path):
    media_root = (tmp_path / "media").resolve()
    media_root.mkdir(parents=True)

    save = SimpleNamespace(target_rel_path="", target_path="~/legacy_slot")

    expected = str(Path("~/legacy_slot").expanduser())
    assert api._resolve_target_abs(media_root, save) == expected


def test_resolve_target_abs_defaults_to_media_root(tmp_path: Path):
    media_root = (tmp_path / "media").resolve()
    media_root.mkdir(parents=True)

    save = SimpleNamespace(target_rel_path="", target_path="")

    assert api._resolve_target_abs(media_root, save) == str(media_root)


def test_add_save_and_get_saves_resolve_paths_with_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    media_root = (tmp_path / "media").resolve()
    media_root.mkdir(parents=True)

    local_source = (tmp_path / "local" / "source").resolve()
    local_source.mkdir(parents=True)

    target_folder = (media_root / "slots" / "alpha").resolve()

    media = SimpleNamespace(
        _id="media-test-1",
        name="Media Test",
        description="",
        path=str(media_root),
        profile_db_name="",
    )

    bindings: dict[tuple[str, str], SimpleNamespace] = {}

    def fake_set_binding(media_id: str, save_id: str, local_path: str):
        binding = SimpleNamespace(
            media_id=media_id,
            save_id=save_id,
            local_path=api._normalize_for_storage(Path(local_path).expanduser()),
        )
        bindings[(media_id, save_id)] = binding
        return binding

    def fake_get_binding(media_id: str, save_id: str):
        return bindings.get((media_id, save_id))

    monkeypatch.setattr(api, "_set_save_binding", fake_set_binding)
    monkeypatch.setattr(api, "_get_save_binding", fake_get_binding)

    created = api.add_save(media, "Slot Alpha", str(local_source), str(target_folder))
    saves = api.get_saves(media)

    assert created.target_rel_path == "slots/alpha"
    assert len(saves) == 1

    loaded = saves[0]
    assert loaded.name == "Slot Alpha"
    assert loaded.target_rel_path == "slots/alpha"
    assert loaded.target_path == str(target_folder)
    assert loaded.local_path == api._normalize_for_storage(local_source)
