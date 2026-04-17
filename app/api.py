
from typing import Sequence, Any, List
from pathlib import Path
import re
import shutil
from uuid import uuid4

from silly_engine.jsondb import JsonDb
from models import Media, Medias, Save, SaveBinding, SaveBindings, Setting, Settings


MEDIA_DB_README_CONTENT = (
    "Save Your Mom - Backup metadata directory\n"
    "\n"
    "This folder contains data used by the backup application \"Save your mom\".\n"
    "If you no longer plan to use this backup with the application,\n"
    "you can safely delete this folder and its files.\n"
)


def _ensure_media_db_readme(db_dir: Path) -> None:
    readme_path = db_dir / "readme.txt"
    if not readme_path.exists():
        readme_path.write_text(MEDIA_DB_README_CONTENT, encoding="utf-8")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    slug = slug.strip("_")
    return slug or "media"


def _normalize_for_storage(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def _get_media_root(media) -> Path:
    media_path = Path(media.path).expanduser()
    if not media_path.exists() or not media_path.is_dir():
        raise ValueError(f"Media path does not exist or is not a directory: {media_path}")
    return media_path


def _get_media_db_dir(media_root: Path) -> Path:
    db_dir = media_root / ".save_your_mom"
    db_dir.mkdir(parents=True, exist_ok=True)
    _ensure_media_db_readme(db_dir)
    return db_dir


def _iter_profile_db_paths(db_dir: Path) -> list[Path]:
    profiles_dir = db_dir / "profiles"
    if not profiles_dir.exists() or not profiles_dir.is_dir():
        return []
    return sorted([p for p in profiles_dir.glob("*.json") if p.is_file()])


def _create_profile_db_file_name(media) -> str:
    slug = _slugify(getattr(media, "name", "media"))
    return f"{slug}__{uuid4().hex[:8]}.json"


def _upsert_local_media_profile_name(media_id: str, profile_db_name: str) -> None:
    media = Medias.get(media_id)
    if media is None:
        return
    media_dict = vars(media).copy()
    media_dict["profile_db_name"] = profile_db_name
    Medias.update(media_dict)


def _extract_media_metadata(metadata: Any) -> dict[str, str]:
    if metadata is None:
        return {"media_id": "", "name": "", "description": ""}

    if isinstance(metadata, dict):
        source = metadata
    elif hasattr(metadata, "data") and isinstance(metadata.data, dict):
        source = metadata.data
    else:
        source = {
            "media_id": getattr(metadata, "media_id", ""),
            "name": getattr(metadata, "name", ""),
            "description": getattr(metadata, "description", ""),
        }

    return {
        "media_id": str(source.get("media_id", "") or ""),
        "name": str(source.get("name", "") or ""),
        "description": str(source.get("description", "") or ""),
    }


def _get_profile_db_by_media_id(db_dir: Path, media_id: str) -> Path | None:
    for profile_path in _iter_profile_db_paths(db_dir):
        try:
            db = JsonDb(profile_path, autosave=True)
            metadata = db.collection("media").first()
            metadata_payload = _extract_media_metadata(metadata)
            if metadata_payload["media_id"] == media_id:
                return profile_path
        except Exception:
            continue
    return None


def _init_profile_db(profile_db_path: Path, media) -> JsonDb:
    db = JsonDb(profile_db_path, autosave=True)
    db.collection("saves", Save)
    media_collection = db.collection("media")
    media_collection.first_update(
        {
            "media_id": media._id,
            "name": media.name,
            "description": media.description,
        }
    )
    return db


def _ensure_profile_db(media, db_dir: Path) -> Path:
    profiles_dir = db_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    created_name = _create_profile_db_file_name(media)
    created_path = profiles_dir / created_name
    _init_profile_db(created_path, media)
    _upsert_local_media_profile_name(media._id, created_name)
    return created_path


def _migrate_legacy_db_to_profile(media, db_dir: Path, legacy_db_path: Path) -> Path:
    profiles_dir = db_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    profile_name = _create_profile_db_file_name(media)
    profile_path = profiles_dir / profile_name
    while profile_path.exists():
        profile_name = _create_profile_db_file_name(media)
        profile_path = profiles_dir / profile_name

    try:
        legacy_db_path.replace(profile_path)
    except OSError:
        shutil.copy2(legacy_db_path, profile_path)

    _upsert_local_media_profile_name(media._id, profile_name)
    return profile_path


def _resolve_media_db_path(media, db_dir: Path) -> Path:
    # Legacy v0 format at media root.
    legacy_root_file = db_dir.parent / ".save_your_mom.json"
    # Legacy v1 single-file format.
    legacy_single_file = db_dir / "save_your_mom.json"

    profile_db_name = getattr(media, "profile_db_name", "") or ""
    if profile_db_name:
        explicit_profile_path = db_dir / "profiles" / profile_db_name
        if explicit_profile_path.exists():
            return explicit_profile_path

    matched_profile_path = _get_profile_db_by_media_id(db_dir, media._id)
    if matched_profile_path is not None:
        matched_name = matched_profile_path.name
        if matched_name != profile_db_name:
            _upsert_local_media_profile_name(media._id, matched_name)
        return matched_profile_path

    if legacy_single_file.exists():
        return _migrate_legacy_db_to_profile(media, db_dir, legacy_single_file)

    if legacy_root_file.exists():
        return _migrate_legacy_db_to_profile(media, db_dir, legacy_root_file)

    return _ensure_profile_db(media, db_dir)


def _to_target_rel_path(media_root: Path, target_abs: Path) -> str:
    try:
        rel = target_abs.relative_to(media_root.resolve())
        rel_str = str(rel)
        return "." if rel_str == "" else rel_str
    except ValueError:
        # Keep backward compatibility when target is outside media root.
        return str(target_abs)


def _resolve_target_abs(media_root: Path, save) -> str:
    rel_path = getattr(save, "target_rel_path", "")
    if rel_path:
        rel = Path(rel_path)
        if rel_path == ".":
            target_abs = media_root
        elif rel.is_absolute():
            target_abs = rel
        else:
            target_abs = media_root / rel
        return str(target_abs)

    legacy_target = getattr(save, "target_path", "")
    if legacy_target:
        return str(Path(legacy_target).expanduser())

    return str(media_root)


def _get_save_binding(media_id: str, save_id: str) -> Any:
    matches = SaveBindings.filter(
        lambda item: item.get("media_id") == media_id and item.get("save_id") == save_id
    )
    return matches[0] if matches else None


def _set_save_binding(media_id: str, save_id: str, local_path: str) -> Any:
    local_norm = _normalize_for_storage(Path(local_path).expanduser())
    existing = _get_save_binding(media_id, save_id)
    binding_payload = {
        "media_id": media_id,
        "save_id": save_id,
        "local_path": local_norm,
    }
    if existing is None:
        return SaveBindings.insert(SaveBinding(**binding_payload))

    binding_dict = vars(existing).copy()
    binding_dict.update(binding_payload)
    return SaveBindings.update(binding_dict)


def _delete_save_binding(media_id: str, save_id: str) -> list[str]:
    return SaveBindings.filter_delete(
        lambda item: item.get("media_id") == media_id and item.get("save_id") == save_id
    )


def _delete_all_bindings_for_media(media_id: str) -> list[str]:
    return SaveBindings.filter_delete(
        lambda item: item.get("media_id") == media_id
    )


def _cleanup_orphan_save_bindings() -> list[str]:
    media_ids = {media._id for media in Medias.all()}
    return SaveBindings.filter_delete(
        lambda item: item.get("media_id") not in media_ids
    )


def _delete_media_profile_from_support(media) -> bool:
    try:
        media_root = _get_media_root(media)
    except ValueError:
        return False

    db_dir = media_root / ".save_your_mom"
    profile_db_name = getattr(media, "profile_db_name", "") or ""

    profile_path: Path | None = None
    if profile_db_name:
        candidate = db_dir / "profiles" / profile_db_name
        if candidate.exists() and candidate.is_file():
            profile_path = candidate

    if profile_path is None:
        profile_path = _get_profile_db_by_media_id(db_dir, media._id)

    if profile_path is None:
        return False

    try:
        profile_path.unlink(missing_ok=True)
    except OSError:
        return False

    # If no profile DB remains, remove the whole metadata directory.
    # Keep the directory if another local media still targets the same path.
    remaining_profiles = _iter_profile_db_paths(db_dir)
    if not remaining_profiles:
        current_media_root_str = str(media_root.resolve())
        has_other_media_on_same_path = False
        for other_media in Medias.all():
            if getattr(other_media, "_id", "") == media._id:
                continue
            other_path_raw = getattr(other_media, "path", "")
            if not other_path_raw:
                continue
            other_path = Path(str(other_path_raw)).expanduser()
            try:
                other_root_str = str(other_path.resolve())
            except OSError:
                continue
            if other_root_str == current_media_root_str:
                has_other_media_on_same_path = True
                break

        if has_other_media_on_same_path:
            return True

        try:
            shutil.rmtree(db_dir)
        except OSError:
            # Non-fatal: profile was deleted successfully, cleanup can be partial.
            pass

    return True


def _sync_media_metadata(db: JsonDb, media) -> None:
    db.collection("media").first_update(
        {
            "media_id": media._id,
            "name": media.name,
            "description": media.description,
        }
    )


def discover_media_profiles(path: str) -> list[dict[str, str]]:
    media_root = Path(path).expanduser()
    if not media_root.exists() or not media_root.is_dir():
        return []

    db_dir = media_root / ".save_your_mom"
    profiles = []
    for profile_path in _iter_profile_db_paths(db_dir):
        try:
            db = JsonDb(profile_path, autosave=True)
            metadata = db.collection("media").first()
            metadata_payload = _extract_media_metadata(metadata)
            profiles.append(
                {
                    "profile_db_name": profile_path.name,
                    "media_id": metadata_payload["media_id"],
                    "name": metadata_payload["name"],
                    "description": metadata_payload["description"],
                }
            )
        except Exception:
            continue
    return profiles



def get_media_db(media) -> JsonDb:
    media_root = _get_media_root(media)
    db_dir = _get_media_db_dir(media_root)
    db_path = _resolve_media_db_path(media, db_dir)

    db = JsonDb(db_path, autosave=True)
    db.collection("saves", Save)
    return db


# ===================================================
# Medias
# ===================================================

def add_media(
    name: str,
    description: str,
    path: str,
    media_id: str | None = None,
    profile_db_name: str = "",
) -> Any:
    if media_id:
        existing = Medias.get(media_id)
        if existing is not None:
            media_dict = vars(existing).copy()
            media_dict["name"] = name
            media_dict["description"] = description
            media_dict["path"] = path
            media_dict["profile_db_name"] = profile_db_name
            updated = Medias.update(media_dict)
            try:
                get_media_db(updated)
            except ValueError:
                pass
            return updated

    media_payload = {
        "name": name,
        "description": description,
        "path": path,
        "profile_db_name": profile_db_name,
    }
    if media_id:
        media_payload["_id"] = media_id
    media = Media(**media_payload)
    inserted = Medias.insert(media)
    # Initialize (or match) profile DB on media at creation time.
    try:
        get_media_db(inserted)
    except ValueError:
        pass
    return inserted

def get_medias() -> Sequence[Any]:
    return Medias.all()

def get_media_by_id(media_id: str) -> Any:
    return Medias.get(media_id)


def update_media(media_id: str, name: str, description: str) -> Any:
    existing_media = Medias.get(media_id)
    if existing_media is None:
        return None

    media_dict = vars(existing_media).copy()
    media_dict["name"] = name
    media_dict["description"] = description
    updated = Medias.update(media_dict)

    # Ensure support metadata stays in sync with local media metadata.
    try:
        db = get_media_db(updated)
        _sync_media_metadata(db, updated)
    except ValueError:
        pass

    return updated

def delete_media_by_id(media_id: str) -> str:
    media = Medias.get(media_id)
    if media is not None:
        _delete_media_profile_from_support(media)
        _delete_all_bindings_for_media(media_id)
    return Medias.delete(media_id)

def _delete_all_medias() -> List[str]:
    deleted_ids: List[str] = []
    for media in list(Medias.all()):
        deleted_ids.append(delete_media_by_id(media._id))
    return deleted_ids

def get_first_media() -> Any:
    return Medias.first()



# ===================================================
# Settings
# ===================================================

def get_or_create_setting() -> Any:
    setting = Settings.first()
    if setting is None:
        setting = Settings.insert(Setting())
    return setting


def get_current_setting() -> Any:
    _cleanup_orphan_save_bindings()
    return get_or_create_setting()


def set_selected_media(media_id: str, media_name: str) -> Any:
    return Settings.first_update(
        {
            "selected_media_id": media_id,
            "selected_media_name": media_name,
        }
    )


# ===================================================
# Saves
# ===================================================


def get_saves(media) -> list:
    try:
        media_root = _get_media_root(media)
        db = get_media_db(media)
        saves = list(db.collection("saves", Save).all())

        enriched_saves = []
        for save in saves:
            save_dict = vars(save).copy()

            # Resolve target absolute path for runtime copy operations.
            save_dict["target_path"] = _resolve_target_abs(media_root, save)

            # Resolve local path from machine-local binding first,
            # then fallback to legacy field if present.
            binding = _get_save_binding(media._id, save._id)
            if binding is not None:
                save_dict["local_path"] = getattr(binding, "local_path", "")
            else:
                save_dict["local_path"] = getattr(save, "local_path", "")

            enriched_saves.append(Save(**save_dict))

        return enriched_saves
    except ValueError:
        return []


def add_save(media, name: str, local_path: str, target_path: str) -> Save:
    media_root = _get_media_root(media)
    target_abs = Path(target_path).expanduser().resolve()
    target_rel_path = _to_target_rel_path(media_root, target_abs)

    db = get_media_db(media)
    new_save = Save(name=name, target_rel_path=target_rel_path)
    inserted = db.collection("saves", Save).insert(new_save)

    _set_save_binding(media._id, inserted._id, local_path)

    save_dict = vars(inserted).copy()
    save_dict["local_path"] = _normalize_for_storage(Path(local_path).expanduser())
    save_dict["target_path"] = str(target_abs)
    return Save(**save_dict)


def set_save_local_binding(media, save_id: str, local_path: str) -> Any:
    return _set_save_binding(media._id, save_id, local_path)


def sync_media_metadata_to_support(media) -> bool:
    try:
        db = get_media_db(media)
        _sync_media_metadata(db, media)
        return True
    except ValueError:
        return False


def delete_save_by_id(media, save_id: str) -> str:
    db = get_media_db(media)
    deleted_id = db.collection("saves", Save).delete(save_id)
    _delete_save_binding(media._id, save_id)
    return deleted_id


def rename_save(media, save_id: str, new_name: str) -> Any:
    db = get_media_db(media)
    collection = db.collection("saves", Save)
    # Get the existing save to preserve target_rel_path.
    existing_save = collection.get(save_id)
    if existing_save:
        save_dict = vars(existing_save).copy()
        save_dict['name'] = new_name
        return collection.update(save_dict)
    return None