#! /usr/bin/env python3

from dataclasses import dataclass
from silly_engine.data_validation import ValidatedWithId
from silly_engine.jsondb import JsonDb, Collection


# Local DB

@dataclass
class Media(ValidatedWithId):
    """Medias will be saved on the local DB"""
    name: str = "-No Name-"
    desctiption: str = ""
    path: str = ""


# Target DB

@dataclass
class Local(ValidatedWithId):
    """Locals will be saved on the target DB"""
    desctiption: str = ""
    path: str = ""

@dataclass
class Target(ValidatedWithId):
    """Targets will be saved on the target DB as well"""
    path: str = ""



local_media_db = JsonDb("local_media_db.json", autosave=True)
Medias: Collection = local_media_db.collection("medias", Media)