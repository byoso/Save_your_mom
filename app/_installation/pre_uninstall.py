#! /usr/bin/env python3

"""Pre-uninstall helper: ask user to confirm full data removal.

Shows a modal GTK dialog asking if the user wants to completely remove
all the application's data. If the user answers "Yes", the
database file is deleted. If "No", nothing is removed.
"""

from pathlib import Path
import sys
import shutil

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


DATA = Path("~/.local/share/geninstaller-applications/.data/SaveYourMom")
WINDOW_TITLE = "SaveYourMom - Uninstall"
MESSAGE_QUESTION = "Do you want to completely remove all the application's data ?"
MESSAGE_DELETED = "All data removed successfully."


def confirm_and_remove_db() -> int:
    """Show confirmation dialog and remove DB file if confirmed.

    Returns an exit code: 0 for success/no-delete, 1 for deletion performed,
    2 for errors during deletion.
    """
    parent = None
    message = MESSAGE_QUESTION

    dialog = Gtk.MessageDialog(
        parent,
        Gtk.DialogFlags.MODAL,
        Gtk.MessageType.QUESTION,
        Gtk.ButtonsType.YES_NO,
        message,
    )
    dialog.set_title(WINDOW_TITLE)
    response = dialog.run()
    dialog.destroy()

    if response == Gtk.ResponseType.YES:
        try:
            data_folder = DATA.expanduser().resolve()
            if data_folder.exists():
                # If it's a directory, remove it and all its contents; otherwise remove the file
                if data_folder.is_dir():
                    shutil.rmtree(data_folder)
                else:
                    data_folder.unlink()
                info = Gtk.MessageDialog(
                    parent,
                    Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.INFO,
                    Gtk.ButtonsType.OK,
                    MESSAGE_DELETED,
                )
                info.run()
                info.destroy()
                return 1
            else:
                info = Gtk.MessageDialog(
                    parent,
                    Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.INFO,
                    Gtk.ButtonsType.OK,
                    "Database file not found — nothing to remove.",
                )
                info.run()
                info.destroy()
                return 0
        except Exception as e:
            err = Gtk.MessageDialog(
                parent,
                Gtk.DialogFlags.MODAL,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                f"Error removing database: {e}",
            )
            err.run()
            err.destroy()
            return 2
    else:
        # User chose No — do nothing
        return 0


def main() -> None:
    rc = confirm_and_remove_db()
    # Map return codes to process exit codes
    if rc == 2:
        sys.exit(2)
    elif rc == 1:
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
