import os
from pathlib import Path
from typing import Optional
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class AddMediaDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Add media", transient_for=parent, modal=True)

        self.set_default_size(520, 220)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Add", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_hexpand(True)
        content.add(grid)

        name_label = Gtk.Label(label="Name")
        name_label.set_xalign(0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)

        description_label = Gtk.Label(label="Description")
        description_label.set_xalign(0)
        self.description_entry = Gtk.Entry()
        self.description_entry.set_hexpand(True)

        path_label = Gtk.Label(label="Path")
        path_label.set_xalign(0)
        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)

        pick_folder_button = Gtk.Button()
        pick_folder_button.set_tooltip_text("Select a folder")
        pick_folder_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        pick_folder_button.add(pick_folder_icon)
        pick_folder_button.connect("clicked", self._on_pick_folder_clicked)

        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        path_box.pack_start(self.path_entry, True, True, 0)
        path_box.pack_start(pick_folder_button, False, False, 0)

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(self.name_entry, 1, 0, 1, 1)

        grid.attach(description_label, 0, 1, 1, 1)
        grid.attach(self.description_entry, 1, 1, 1, 1)

        grid.attach(path_label, 0, 2, 1, 1)
        grid.attach(path_box, 1, 2, 1, 1)

        self.show_all()

    def _on_pick_folder_clicked(self, _button):
        chooser = Gtk.FileChooserDialog(
            title="Choose media folder",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        chooser.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Select", Gtk.ResponseType.OK,
        )

        response = chooser.run()
        if response == Gtk.ResponseType.OK:
            selected_folder = chooser.get_filename()
            if selected_folder:
                self.path_entry.set_text(selected_folder)

        chooser.destroy()

    def get_media_data(self):
        name = self.name_entry.get_text().strip()
        description = self.description_entry.get_text().strip()
        path = self.path_entry.get_text().strip()
        # Normalize path: store with ~/ when inside home directory
        home = os.path.expanduser("~")
        if path.startswith(home + "/"):
            path = "~/" + path[len(home) + 1:]

        if not name:
            self._show_error("Name is required.")
            return None

        if not path:
            self._show_error("Path is required.")
            return None

        if not os.path.isdir(os.path.expanduser(path)):
            self._show_error("Path must point to an existing folder.")
            return None

        return {
            "name": name,
            "description": description,
            "path": path,
        }

    def _show_error(self, message):
        error_dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        error_dialog.run()
        error_dialog.destroy()


class DeleteMediaDialog(Gtk.Dialog):
    def __init__(self, parent, media_name: str):
        super().__init__(title="Delete media", transient_for=parent, modal=True)

        self.set_default_size(420, 140)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)

        delete_button = self.add_button("Delete", Gtk.ResponseType.OK)
        delete_button.get_style_context().add_class("delete-confirm-button")
        self.set_default_response(Gtk.ResponseType.CANCEL)

        content = self.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(20)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)

        message = Gtk.Label(label=f'Delete "{media_name}"?\nThis cannot be undone.')
        message.set_xalign(0)
        message.set_line_wrap(True)
        content.add(message)

        self.show_all()


class DeleteSaveDialog(Gtk.Dialog):
    def __init__(self, parent, save_name: str):
        super().__init__(title="Delete save", transient_for=parent, modal=True)

        self.set_default_size(420, 140)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)

        delete_button = self.add_button("Delete", Gtk.ResponseType.OK)
        delete_button.get_style_context().add_class("delete-confirm-button")
        self.set_default_response(Gtk.ResponseType.CANCEL)

        content = self.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(20)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)

        message = Gtk.Label(label=f'Delete save "{save_name}"?\nThis cannot be undone.')
        message.set_xalign(0)
        message.set_line_wrap(True)
        content.add(message)

        self.show_all()


class RenameSaveDialog(Gtk.Dialog):
    def __init__(self, parent, current_name: str):
        super().__init__(title="Rename save", transient_for=parent, modal=True)

        self.set_default_size(400, 120)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Rename", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_spacing(10)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(current_name)
        self.name_entry.set_activates_default(True)
        self.name_entry.select_region(0, -1)
        content.add(self.name_entry)

        self.show_all()

    def get_name(self) -> Optional[str]:
        name = self.name_entry.get_text().strip()
        if not name:
            error_dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Name is required.",
            )
            error_dialog.run()
            error_dialog.destroy()
            return None
        return name


class AddSaveDialog(Gtk.Dialog):
    def __init__(self, parent, selected_media):
        super().__init__(title="Add save", transient_for=parent, modal=True)
        self.selected_media = selected_media

        self.set_default_size(520, 200)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Add", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_hexpand(True)
        content.add(grid)

        name_label = Gtk.Label(label="Name")
        name_label.set_xalign(0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)

        local_label = Gtk.Label(label="From")
        local_label.set_xalign(0)
        self.local_entry = Gtk.Entry()
        self.local_entry.set_hexpand(True)
        local_pick_button = Gtk.Button()
        local_pick_button.set_tooltip_text("Select source folder")
        local_pick_button.add(Gtk.Image.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON))
        local_pick_button.connect("clicked", self._on_pick_local_clicked)
        local_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        local_box.pack_start(self.local_entry, True, True, 0)
        local_box.pack_start(local_pick_button, False, False, 0)

        target_label = Gtk.Label(label="To")
        target_label.set_xalign(0)
        self.target_entry = Gtk.Entry()
        self.target_entry.set_hexpand(True)
        target_pick_button = Gtk.Button()
        target_pick_button.set_tooltip_text("Select destination folder")
        target_pick_button.add(Gtk.Image.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON))
        target_pick_button.connect("clicked", self._on_pick_target_clicked)
        target_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        target_box.pack_start(self.target_entry, True, True, 0)
        target_box.pack_start(target_pick_button, False, False, 0)

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(self.name_entry, 1, 0, 1, 1)

        grid.attach(local_label, 0, 1, 1, 1)
        grid.attach(local_box, 1, 1, 1, 1)

        grid.attach(target_label, 0, 2, 1, 1)
        grid.attach(target_box, 1, 2, 1, 1)

        media_path = getattr(self.selected_media, "path", "")
        if media_path:
            self.target_entry.set_text(media_path)

        self.show_all()

    def _on_pick_local_clicked(self, _button):
        self._pick_folder("Choose source folder", self.local_entry)

    def _on_pick_target_clicked(self, _button):
        media_path = getattr(self.selected_media, "path", "")
        initial_folder = os.path.expanduser(media_path) if media_path else None
        self._pick_folder("Choose destination folder", self.target_entry, initial_folder)

    def _pick_folder(self, title: str, entry: Gtk.Entry, initial_folder: Optional[str] = None):
        chooser = Gtk.FileChooserDialog(
            title=title,
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        chooser.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Select", Gtk.ResponseType.OK,
        )

        if initial_folder and os.path.isdir(initial_folder):
            chooser.set_current_folder(initial_folder)

        response = chooser.run()
        if response == Gtk.ResponseType.OK:
            selected = chooser.get_filename()
            if selected:
                entry.set_text(selected)
        chooser.destroy()

    def get_save_data(self):
        name = self.name_entry.get_text().strip()
        local_path = self.local_entry.get_text().strip()
        target_path = self.target_entry.get_text().strip()

        if not name:
            self._show_error("Name is required.")
            return None

        if not local_path:
            self._show_error("Source path (From) is required.")
            return None

        if not os.path.isdir(os.path.expanduser(local_path)):
            self._show_error("Source path (From) must point to an existing folder.")
            return None

        if not target_path:
            self._show_error("Destination path (To) is required.")
            return None

        if not os.path.isdir(os.path.expanduser(target_path)):
            self._show_error("Destination path (To) must point to an existing folder.")
            return None

        media_path = getattr(self.selected_media, "path", "")
        media_root = Path(media_path).expanduser().resolve() if media_path else None
        target_abs = Path(target_path).expanduser().resolve()

        if media_root is None or not media_root.is_dir():
            self._show_error("Selected media is unavailable.")
            return None

        try:
            target_abs.relative_to(media_root)
        except ValueError:
            self._show_error(f"Target path must be inside selected media: {media_path}")
            return None

        return {
            "name": name,
            "local_path": local_path,
            "target_path": target_path,
        }

    def _show_error(self, message: str):
        error_dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        error_dialog.run()
        error_dialog.destroy()
