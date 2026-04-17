import os
from pathlib import Path
from typing import Optional
import gi
from api import get_saves, discover_media_profiles

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _is_within_path(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_removable_mount_path(path: Path) -> bool:
    removable_roots = [
        Path("/media"),
        Path("/run/media"),
        Path("/mnt"),
    ]
    for root in removable_roots:
        resolved_root = root.resolve()
        if _is_within_path(path, resolved_root):
            return True
    return False


def _build_existing_save_path_conflict(
    new_path: Path,
    existing_saves,
    path_attr: str,
    path_label: str,
) -> Optional[str]:
    for existing_save in existing_saves:
        existing_path_raw = getattr(existing_save, path_attr, "")
        if not existing_path_raw:
            continue

        existing_path = Path(existing_path_raw).expanduser().resolve()
        save_name = getattr(existing_save, "name", "-No Name-")

        if new_path == existing_path:
            return (
                f'{path_label} conflicts with existing save "{save_name}": '
                "path is identical."
            )

        if _is_within_path(new_path, existing_path):
            return (
                f'{path_label} conflicts with existing save "{save_name}": '
                "path is inside the existing save path."
            )

        if _is_within_path(existing_path, new_path):
            return (
                f'{path_label} conflicts with existing save "{save_name}": '
                "path contains the existing save path."
            )

    return None


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

        if not path:
            self._show_error("Path is required.")
            return None

        if not os.path.isdir(os.path.expanduser(path)):
            self._show_error("Path must point to an existing folder.")
            return None

        import_choice = None
        profiles = discover_media_profiles(path)
        if profiles:
            chooser = MediaProfileChoiceDialog(self, profiles)
            response = chooser.run()
            if response != Gtk.ResponseType.OK:
                chooser.destroy()
                return {"cancelled": True}
            import_choice = chooser.get_choice()
            chooser.destroy()

            if import_choice["mode"] == "import":
                selected_profile = import_choice["profile"]
                if not name:
                    name = selected_profile.get("name", "")
                if not description:
                    description = selected_profile.get("description", "")

        if not name:
            self._show_error("Name is required.")
            return None

        # Normalize path: store with ~/ when inside home directory
        home = os.path.expanduser("~")
        if path.startswith(home + "/"):
            path = "~/" + path[len(home) + 1:]

        payload = {
            "name": name,
            "description": description,
            "path": path,
        }

        if import_choice and import_choice["mode"] == "import":
            selected_profile = import_choice["profile"]
            payload["media_id"] = selected_profile.get("media_id", "")
            payload["profile_db_name"] = selected_profile.get("profile_db_name", "")

        return payload


class MediaProfileChoiceDialog(Gtk.Dialog):
    def __init__(self, parent, profiles: list[dict[str, str]]):
        super().__init__(title="Media profiles found", transient_for=parent, modal=True)
        self.profiles = profiles

        self.set_default_size(520, 220)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Continue", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_spacing(10)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        message = Gtk.Label(
            label=(
                "Backup profiles were found in this media folder.\n"
                "Choose whether to create a new profile or import an existing one."
            )
        )
        message.set_xalign(0)
        content.add(message)

        self.create_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Create a new media profile")
        self.import_radio = Gtk.RadioButton.new_with_label_from_widget(
            self.create_radio,
            "Import an existing media profile",
        )
        self.import_radio.set_active(True)

        content.add(self.create_radio)
        content.add(self.import_radio)

        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        profile_label = Gtk.Label(label="Existing profile")
        profile_label.set_xalign(0)
        self.profile_combo = Gtk.ComboBoxText()
        self.profile_combo.set_hexpand(True)

        for profile in profiles:
            profile_name = profile.get("name", "") or "-No Name-"
            profile_desc = profile.get("description", "")
            profile_file = profile.get("profile_db_name", "")
            label = f"{profile_name} ({profile_file})"
            if profile_desc:
                label = f"{label} - {profile_desc}"
            self.profile_combo.append_text(label)

        self.profile_combo.set_active(0)
        profile_box.pack_start(profile_label, False, False, 0)
        profile_box.pack_start(self.profile_combo, True, True, 0)
        content.add(profile_box)

        self.create_radio.connect("toggled", self._on_mode_changed)
        self.import_radio.connect("toggled", self._on_mode_changed)
        self._on_mode_changed(None)

        self.show_all()

    def _on_mode_changed(self, _button):
        self.profile_combo.set_sensitive(self.import_radio.get_active())

    def get_choice(self) -> dict:
        if self.create_radio.get_active():
            return {"mode": "create", "profile": None}

        selected_index = self.profile_combo.get_active()
        if selected_index < 0 or selected_index >= len(self.profiles):
            return {"mode": "create", "profile": None}
        return {"mode": "import", "profile": self.profiles[selected_index]}

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


class EditMediaDialog(Gtk.Dialog):
    def __init__(self, parent, current_name: str, current_description: str):
        super().__init__(title="Edit media", transient_for=parent, modal=True)

        self.set_default_size(480, 160)
        self.set_resizable(False)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Save", Gtk.ResponseType.OK)
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
        self.name_entry.set_text(current_name)
        self.name_entry.set_activates_default(True)

        description_label = Gtk.Label(label="Description")
        description_label.set_xalign(0)
        self.description_entry = Gtk.Entry()
        self.description_entry.set_hexpand(True)
        self.description_entry.set_text(current_description)

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(self.name_entry, 1, 0, 1, 1)

        grid.attach(description_label, 0, 1, 1, 1)
        grid.attach(self.description_entry, 1, 1, 1, 1)

        self.show_all()

    def get_media_data(self):
        name = self.name_entry.get_text().strip()
        description = self.description_entry.get_text().strip()

        if not name:
            self._show_error("Name is required.")
            return None

        return {
            "name": name,
            "description": description,
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

        local_abs = Path(local_path).expanduser().resolve()
        target_abs = Path(target_path).expanduser().resolve()
        media_root = (Path.home() / "media").resolve()
        selected_media_path = getattr(self.selected_media, "path", "")
        selected_media_root = Path(selected_media_path).expanduser().resolve() if selected_media_path else None

        if _is_within_path(local_abs, media_root):
            self._show_error(
                "Source path (From) must be outside ~/media.\n"
                "Local backups must stay on the PC."
            )
            return None

        if _is_removable_mount_path(local_abs):
            self._show_error(
                "Source path (From) cannot be on a removable media mount.\n"
                "Please choose a folder on the PC internal storage."
            )
            return None

        if selected_media_root is not None and _is_within_path(local_abs, selected_media_root):
            self._show_error(
                "Source path (From) cannot be inside the selected media path."
            )
            return None

        if local_abs == target_abs:
            self._show_error(
                "Source path (From) and destination path (To) cannot be identical."
            )
            return None

        if _is_within_path(local_abs, target_abs):
            self._show_error(
                "Source path (From) cannot be inside destination path (To)."
            )
            return None

        if _is_within_path(target_abs, local_abs):
            self._show_error(
                "Destination path (To) cannot be inside source path (From)."
            )
            return None

        existing_saves = get_saves(self.selected_media)

        local_conflict = _build_existing_save_path_conflict(
            new_path=local_abs,
            existing_saves=existing_saves,
            path_attr="local_path",
            path_label="Source path (From)",
        )
        if local_conflict:
            self._show_error(local_conflict)
            return None

        target_conflict = _build_existing_save_path_conflict(
            new_path=target_abs,
            existing_saves=existing_saves,
            path_attr="target_path",
            path_label="Destination path (To)",
        )
        if target_conflict:
            self._show_error(target_conflict)
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


class RenameReportDialog(Gtk.Dialog):
    def __init__(self, parent, save_name: str, renames: list):
        super().__init__(title="Incident report", transient_for=parent, modal=False)
        self.set_default_size(600, 360)
        self.add_button("OK", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.connect("response", lambda dialog, _response: dialog.destroy())

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_monospace(True)
        text_view.set_wrap_mode(Gtk.WrapMode.NONE)

        buf = text_view.get_buffer()
        rename_entries = []
        error_entries = []
        other_entries = []

        for reason, original, final in renames:
            entry_save_name = save_name
            entry_reason = reason
            if " | save: " in reason:
                entry_reason, entry_save_name = reason.split(" | save: ", 1)
                entry_reason = entry_reason.strip()
                entry_save_name = entry_save_name.strip() or save_name

            reason_lower = entry_reason.lower()
            if reason_lower.startswith("error"):
                error_entries.append((entry_save_name, entry_reason, original, final))
            elif "collision" in reason_lower or "conflict" in reason_lower:
                rename_entries.append((entry_save_name, entry_reason, original, final))
            else:
                other_entries.append((entry_save_name, entry_reason, original, final))

        report_lines = ["Incident report"]

        if rename_entries:
            report_lines.append("")
            report_lines.append("[Rename incidents]")
            report_lines.append("Some files or folders were renamed to avoid conflicts on the destination filesystem.")
            report_lines.append("")
            for entry_save_name, entry_reason, original, final in rename_entries:
                report_lines.append(
                    f"[Save: {entry_save_name}]\n[{entry_reason}]\n  {original!r}  ->  {final!r}"
                )
                report_lines.append("")
            report_lines.append("_" * 20)

        if error_entries:
            report_lines.append("")
            report_lines.append("[Error incidents]")
            report_lines.append("")
            for entry_save_name, entry_reason, original, _final in error_entries:
                report_lines.append(
                    f"[Save: {entry_save_name}]\n[{entry_reason}]\n  {original}"
                )
                report_lines.append("")
            report_lines.append("_" * 20)

        if other_entries:
            report_lines.append("")
            report_lines.append("[Other incidents]")
            report_lines.append("")
            for entry_save_name, entry_reason, original, final in other_entries:
                report_lines.append(
                    f"[Save: {entry_save_name}]\n[{entry_reason}]\n  {original!r}  ->  {final!r}"
                )
                report_lines.append("")
            report_lines.append("_" * 20)

        if not rename_entries and not error_entries and not other_entries:
            report_lines.append("")
            report_lines.append("No incident to report.")

        buf.set_text("\n".join(report_lines).rstrip())

        scrolled.add(text_view)
        content.add(scrolled)

        self.show_all()
