
from typing import Sequence, Any, List
from pathlib import Path

from silly_engine.jsondb import JsonDb
from models import Media, Medias, Save, Setting, Settings


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



def get_media_db(media) -> JsonDb:
    media_path = Path(media.path).expanduser()
    if not media_path.exists() or not media_path.is_dir():
        raise ValueError(f"Media path does not exist or is not a directory: {media_path}")

    legacy_db_path = media_path / ".save_your_mom.json"
    db_dir = media_path / ".save_your_mom"
    db_path = db_dir / "save_your_mom.json"

    # Keep backward compatibility by migrating the legacy DB file on first access.
    if legacy_db_path.exists() and not db_path.exists():
        db_dir.mkdir(parents=True, exist_ok=True)
        legacy_db_path.replace(db_path)

    db_dir.mkdir(parents=True, exist_ok=True)
    _ensure_media_db_readme(db_dir)

    db = JsonDb(db_path, autosave=True)
    db.collection("saves", Save)
    return db


# ===================================================
# Medias
# ===================================================

def add_media(name: str, description: str, path: str) -> Media:
    media = Media(name=name, description=description, path=path)
    inserted = Medias.insert(media)
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
    return Medias.update(media_dict)

def delete_media_by_id(media_id: str) -> str:
    # Remove only the media entry from the local registry.
    # Never delete media backup DB files from the media path.
    return Medias.delete(media_id)

def _delete_all_medias() -> List[str]:
    return Medias.filter_delete(lambda m: True)

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
        db = get_media_db(media)
        return list(db.collection("saves", Save).all())
    except ValueError:
        return []


def add_save(media, name: str, local_path: str, target_path: str) -> Save:
    home = Path.home()

    # Normalize paths: store with ~/ when inside home directory
    local = Path(local_path).expanduser()
    target = Path(target_path).expanduser()

    try:
        local_path = "~/" + str(local.relative_to(home))
    except ValueError:
        local_path = str(local)

    try:
        target_path = "~/" + str(target.relative_to(home))
    except ValueError:
        target_path = str(target)

    db = get_media_db(media)
    new_save = Save(name=name, local_path=local_path, target_path=target_path)
    db.collection("saves", Save).insert(new_save)
    return new_save


def delete_save_by_id(media, save_id: str) -> str:
    db = get_media_db(media)
    return db.collection("saves", Save).delete(save_id)


def rename_save(media, save_id: str, new_name: str) -> Any:
    db = get_media_db(media)
    collection = db.collection("saves", Save)
    # Get the existing save to preserve local_path and target_path
    existing_save = collection.get(save_id)
    if existing_save:
        # Convert to dict to merge with new name
        save_dict = vars(existing_save).copy()
        save_dict['name'] = new_name
        return collection.update(save_dict)
    return None