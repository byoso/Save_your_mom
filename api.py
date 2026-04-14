
from typing import Sequence, Any, List
from pathlib import Path
from dataclasses import asdict

from silly_engine.jsondb import JsonDb, Collection
from models import Media, Medias, Save, Setting, Settings



def get_media_db(media) -> JsonDb:
    media_path = Path(media.path).expanduser()
    if not media_path.exists() or not media_path.is_dir():
        raise ValueError(f"Media path does not exist or is not a directory: {media_path}")
    db_path = media_path / ".save_your_mom.json"
    db = JsonDb(db_path, autosave=True)
    db.collection("saves", Save)
    return db


# ===================================================
# Medias
# ===================================================

def add_media(name: str, description: str, path: str) -> Media:
    media = Media(name=name, desctiption=description, path=path)
    Medias.insert(media)
    return media

def get_medias() -> Sequence[Any]:
    return Medias.all()

def get_media_by_id(media_id: str) -> Any:
    return Medias.get(media_id)

def delete_media_by_id(media_id: str) -> str:
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
    media_root = Path(media.path).expanduser().resolve()
    target_abs = Path(target_path).expanduser().resolve()

    try:
        target_abs.relative_to(media_root)
    except ValueError as exc:
        raise ValueError(f"Target path must be inside selected media: {media.path}") from exc

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
        save_dict = asdict(existing_save)
        save_dict['name'] = new_name
        return collection.update(save_dict)
    return None