
from typing import Sequence, Any, List

from models import Media, Medias, Local, Target


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