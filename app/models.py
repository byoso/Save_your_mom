#! /usr/bin/env python3

import os
from dataclasses import dataclass
from silly_engine.data_validation import ValidatedWithId
from silly_engine.jsondb import JsonDb, Collection


# Local DB
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class Setting(ValidatedWithId):
    selected_media_id: str = ""
    selected_media_name: str = ""


@dataclass
class Media(ValidatedWithId):
    """Medias will be saved on the local DB"""
    name: str = "-No Name-"
    description: str = ""
    path: str = ""
    profile_db_name: str = ""

# Target DB


@dataclass
class Save(ValidatedWithId):
    """Save metadata stored on media and enriched locally for runtime use."""
    name: str = ""
    target_rel_path: str = ""

    # Backward-compatible runtime fields. These are computed in the API layer
    # and can still be present in legacy media databases.
    local_path: str = ""
    target_path: str = ""


@dataclass
class SaveBinding(ValidatedWithId):
    """Machine-local binding between a media/save pair and a local source path."""
    media_id: str = ""
    save_id: str = ""
    local_path: str = ""


def _migrate_paths_to_tilde(db):
    """Migration 0.1.0: store media paths with ~/ instead of absolute home paths"""
    home = os.path.expanduser("~")
    medias = db.collection("medias")
    for item in medias.data.values():
        path = item.data.get("path", "")
        if path.startswith(home + "/"):
            item.data["path"] = "~/" + path[len(home) + 1:]
    db.save()


def _migrate_media_profile_field(db):
    """Migration 0.2.0: ensure medias have a profile_db_name field."""
    medias = db.collection("medias")
    changed = False
    for item in medias.data.values():
        if "profile_db_name" not in item.data:
            item.data["profile_db_name"] = ""
            changed = True
    if changed:
        db.save()


local_media_db = JsonDb(
    os.path.join(_BASE_DIR, "database","local_media_db.json"),
    autosave=True,
    version="0.2.0",
    migrations={
        "0.1.0": _migrate_paths_to_tilde,
        "0.2.0": _migrate_media_profile_field,
    },
)
Medias: Collection = local_media_db.collection("medias", Media)
Settings: Collection = local_media_db.collection("settings", Setting) # singleton
SaveBindings: Collection = local_media_db.collection("save_bindings", SaveBinding)