#! /usr/bin/env python3

import gi.repository
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


from api import add_media, get_medias, get_media_by_id, delete_media_by_id, _delete_all_medias, get_first_media


def main():
    pass









def test():
    print("main...")
    # add_media("Test", "Wrong test media", "test/toto")
    # add_media("Test", "Right test media", "test/target/main")
    # add_media("Test", "Right test media", "test/target/secondary")

    # print(f"OK: {get_media_by_id('72c1f54c-a369-4c84-8134-8f69f3df56ea')}")
    # print(f"KO: {get_media_by_id('fake')}")
    # first_media = get_first_media()
    # print(f"First media: {first_media}")
    # print(f"Delete: {delete_media_by_id(first_media._id)}")

    print(get_medias(), f"\n{len(get_medias())} medias in total")


if __name__ == "__main__":
    # test()
    main()