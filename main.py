#! /usr/bin/env python3

from interface import App
from api import add_media, get_medias, delete_media_by_id, get_media_by_id, get_first_media, _delete_all_medias

def main():
    App().run()



def test():
    print("main...")
    # add_media("Test", "Wrong test media", "fake/toto")
    # add_media("Test", "Right test media", "fake/target/main")
    # add_media("Test", "Right test media", "fake/target/secondary")

    # print(f"OK: {get_media_by_id('72c1f54c-a369-4c84-8134-8f69f3df56ea')}")
    # print(f"KO: {get_media_by_id('fake')}")
    # first_media = get_first_media()
    # print(f"First media: {first_media}")
    # print(f"Delete: {delete_media_by_id(first_media._id)}")

    print(get_medias(), f"\n{len(get_medias())} medias in total")


if __name__ == "__main__":
    # test()
    main()