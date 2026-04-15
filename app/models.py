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

# Target DB


@dataclass
class Save(ValidatedWithId):
    """Save represents a copy operation from a LocalFolder to a TargetFolder"""
    name: str = ""
    local_path: str = ""
    target_path: str = ""


def _migrate_paths_to_tilde(db):
    """Migration 0.1.0: store media paths with ~/ instead of absolute home paths"""
    home = os.path.expanduser("~")
    medias = db.collection("medias")
    for item in medias.data.values():
        path = item.data.get("path", "")
        if path.startswith(home + "/"):
            item.data["path"] = "~/" + path[len(home) + 1:]
    db.save()


local_media_db = JsonDb(
    os.path.join(_BASE_DIR, "database","local_media_db.json"),
    autosave=True,
    version="0.1.0",
    migrations={"0.1.0": _migrate_paths_to_tilde},
)
Medias: Collection = local_media_db.collection("medias", Media)
Settings: Collection = local_media_db.collection("settings", Setting) # singleton