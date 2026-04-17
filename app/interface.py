import os
import subprocess
import threading
import time
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, Gdk, GLib

from api import (
    add_media,
    get_medias,
    set_selected_media,
    get_current_setting,
    get_media_by_id,
    update_media,
    delete_media_by_id,
    get_first_media,
    get_saves,
    add_save,
    delete_save_by_id,
    rename_save,
    set_save_local_binding,
    sync_media_metadata_to_support,
)
from backups_logic import copy_local_to_target, copy_target_to_local, BackupLogicError
from media_dialog import (
    AddMediaDialog,
    DeleteMediaDialog,
    EditMediaDialog,
    AddSaveDialog,
    DeleteSaveDialog,
    RenameSaveDialog,
    RenameReportDialog,
)

from models import Medias, Settings, Save

APP_TITLE = "Save Your Mom (and mine !)"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class MediaRow(Gtk.ListBoxRow):
    def __init__(self, media):
        super().__init__()
        self.media = media
        self._id = media._id
        self._is_selected = False  # Local selection state
        self.get_style_context().add_class("media-row")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.set_margin_top(5)
        content.set_margin_bottom(5)
        content.set_margin_start(14)
        content.set_margin_end(14)

        is_valid = os.path.isdir(os.path.expanduser(media.path))
        icon_name = "emblem-ok-symbolic" if is_valid else "window-close-symbolic"
        icon_class = "media-valid" if is_valid else "media-invalid"
        validity_icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR)
        validity_icon.get_style_context().add_class(icon_class)

        name_label = Gtk.Label(label=media.name)
        name_label.set_xalign(0)
        name_label.get_style_context().add_class("media-name")

        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_box.pack_start(validity_icon, False, False, 0)
        name_box.pack_start(name_label, True, True, 0)

        path_label = Gtk.Label(label=media.path)
        path_label.set_xalign(0)
        path_label.get_style_context().add_class("media-path")

        content.pack_start(name_box, False, False, 0)
        content.pack_start(path_label, False, False, 0)

        if media.description:
            description_label = Gtk.Label(label=media.description)
            description_label.set_xalign(0)
            description_label.get_style_context().add_class("media-description")
            content.pack_start(description_label, False, False, 0)

        self.add(content)

    @property
    def is_selected(self) -> bool:
        """Get the local selection state."""
        return self._is_selected

    def set_selected(self, is_selected: bool) -> None:
        """Update selection state and apply corresponding CSS class."""
        self._is_selected = is_selected
        style_context = self.get_style_context()
        if is_selected:
            style_context.add_class("media-row-selected")
        else:
            style_context.remove_class("media-row-selected")


class SaveRow(Gtk.ListBoxRow):
    def __init__(self, parent_window, save, media, on_refresh_saves, on_hover_status, on_set_status):
        super().__init__()
        self.parent_window = parent_window
        self.save = save
        self.media = media
        self.on_refresh_saves = on_refresh_saves
        self.on_set_status = on_set_status
        self.set_activatable(False)
        self.set_selectable(False)
        self.get_style_context().add_class("save-row")

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        container.set_margin_top(6)
        container.set_margin_bottom(6)
        container.set_margin_start(14)
        container.set_margin_end(14)

        # Title line: edit button + name
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        edit_button = Gtk.Button()
        edit_button.set_tooltip_text("Rename save")
        edit_button.add(Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.SMALL_TOOLBAR))
        edit_button.get_style_context().add_class("save-row-edit-button")
        edit_button.connect("clicked", self._on_rename_clicked)
        title_box.pack_start(edit_button, False, False, 0)

        name_label = Gtk.Label(label=save.name)
        name_label.set_xalign(0)
        name_label.get_style_context().add_class("media-name")
        title_box.pack_start(name_label, True, True, 0)

        container.pack_start(title_box, False, False, 0)

        # Actions line: centered controls + delete button on the far right
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        center_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        center_group.set_halign(Gtk.Align.CENTER)
        center_group.set_hexpand(True)

        # Local path validity indicator (left of PC button)
        local_path = getattr(save, "local_path", "")
        local_is_configured = bool(local_path)
        local_is_valid = local_is_configured and os.path.isdir(os.path.expanduser(local_path))
        local_icon_name = "emblem-ok-symbolic" if local_is_valid else "window-close-symbolic"
        local_icon_class = "media-valid" if local_is_valid else "media-invalid"
        local_validity_icon = Gtk.Image.new_from_icon_name(local_icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        local_validity_icon.get_style_context().add_class(local_icon_class)
        if not local_is_configured:
            local_validity_icon.set_tooltip_text("Local path: Not configured")
        elif not local_is_valid:
            local_validity_icon.set_tooltip_text("Local path: Missing")
        else:
            local_validity_icon.set_tooltip_text("Local path: Ready")
        center_group.pack_start(local_validity_icon, False, False, 0)

        pc_button = Gtk.Button()
        pc_button.set_tooltip_text(save.local_path if save.local_path else "Local path not configured")
        pc_button.get_style_context().add_class("save-row-device-button")
        pc_icon = Gtk.Image.new_from_icon_name("computer-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        pc_icon.get_style_context().add_class("save-row-device-icon")
        pc_button.add(pc_icon)
        pc_button.set_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        pc_button.connect("enter-notify-event", lambda _w, _e, p=save.local_path: on_hover_status(f"local_path: {p}"))
        pc_button.connect("clicked", self._on_pc_button_clicked, save.local_path)
        pc_button.set_margin_end(28)
        center_group.pack_start(pc_button, False, False, 0)

        arrow_right = Gtk.Button()
        arrow_right.set_tooltip_text("Copy to media")
        arrow_right.add(Gtk.Image.new_from_icon_name("go-next-symbolic", Gtk.IconSize.BUTTON))
        arrow_right.get_style_context().add_class("save-row-arrow-right")
        arrow_right.connect("clicked", self._on_arrow_right_clicked)
        center_group.pack_start(arrow_right, False, False, 0)

        separator_label = Gtk.Label(label="•••••••")
        separator_label.get_style_context().add_class("save-row-separator")
        separator_label.set_margin_start(10)
        separator_label.set_margin_end(10)
        center_group.pack_start(separator_label, False, False, 0)

        arrow_left = Gtk.Button()
        arrow_left.set_tooltip_text("Restore from media")
        arrow_left.add(Gtk.Image.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.BUTTON))
        arrow_left.get_style_context().add_class("save-row-arrow-left")
        arrow_left.connect("clicked", self._on_arrow_left_clicked)
        arrow_left.set_margin_end(28)
        center_group.pack_start(arrow_left, False, False, 0)

        usb_button = Gtk.Button()
        usb_button.set_tooltip_text(save.target_path)
        usb_button.get_style_context().add_class("save-row-device-button")
        usb_icon = Gtk.Image.new_from_icon_name("drive-removable-media-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        usb_icon.get_style_context().add_class("save-row-device-icon")
        usb_button.add(usb_icon)
        usb_button.set_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        usb_button.connect("enter-notify-event", lambda _w, _e, p=save.target_path: on_hover_status(f"target_path: {p}"))
        usb_button.connect("clicked", self._on_usb_button_clicked, save.target_path)
        center_group.pack_start(usb_button, False, False, 0)

        # Target path validity indicator (right of USB button)
        target_is_valid = os.path.isdir(os.path.expanduser(save.target_path))
        target_icon_name = "emblem-ok-symbolic" if target_is_valid else "window-close-symbolic"
        target_icon_class = "media-valid" if target_is_valid else "media-invalid"
        target_validity_icon = Gtk.Image.new_from_icon_name(target_icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        target_validity_icon.get_style_context().add_class(target_icon_class)
        center_group.pack_start(target_validity_icon, False, False, 0)

        actions_box.pack_start(center_group, True, True, 0)

        # Spacer keeps delete button fully right while preserving centered group
        right_spacer = Gtk.Box()
        right_spacer.set_size_request(8, -1)
        actions_box.pack_start(right_spacer, False, False, 0)

        delete_button = Gtk.Button()
        delete_button.set_tooltip_text("Delete save")
        delete_button.add(Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON))
        delete_button.get_style_context().add_class("save-row-delete-button")
        delete_button.connect("clicked", self._on_delete_clicked)
        actions_box.pack_end(delete_button, False, False, 0)

        container.pack_start(actions_box, False, False, 0)
        self.add(container)

    def _on_rename_clicked(self, _button):
        dialog = RenameSaveDialog(self.parent_window, self.save.name)
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                self.on_set_status("Rename canceled")
                break

            new_name = dialog.get_name()
            if not new_name:
                continue

            rename_save(self.media, self.save._id, new_name)
            self.on_refresh_saves()
            self.on_set_status(f"Save renamed: {new_name}")
            break

        dialog.destroy()

    def _on_pc_button_clicked(self, _button, path):
        # Open file explorer to local_path if it exists, otherwise start rebind assistant.
        expanded_path = os.path.expanduser(path)
        if os.path.isdir(expanded_path):
            try:
                subprocess.Popen(["xdg-open", expanded_path])
            except Exception as e:
                self.on_set_status(f"Error opening file explorer: {e}")
        else:
            rebound = self.parent_window._prompt_rebind_save(self.save, self.media)
            if rebound:
                self.on_refresh_saves()
            else:
                self.on_set_status("Local path is not configured")

    def _on_usb_button_clicked(self, _button, path):
        # Open file explorer to target_path if it exists, otherwise show status message
        expanded_path = os.path.expanduser(path)
        if os.path.isdir(expanded_path):
            try:
                subprocess.Popen(["xdg-open", expanded_path])
            except Exception as e:
                self.on_set_status(f"Error opening file explorer: {e}")
        else:
            self.on_set_status("Path does not exist")

    def _on_arrow_right_clicked(self, _button):
        if self.parent_window._op_animation_running:
            return
        self.parent_window._start_save_operation(self.save, self.media, to_media=True)

    def _on_arrow_left_clicked(self, _button):
        if self.parent_window._op_animation_running:
            return
        self.parent_window._start_save_operation(self.save, self.media, to_media=False)

    def _on_delete_clicked(self, _button):
        dialog = DeleteSaveDialog(self.parent_window, self.save.name)
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            self.on_set_status("Delete save canceled")
            return

        delete_save_by_id(self.media, self.save._id)
        self.on_refresh_saves()
        self.on_set_status(f"Save deleted: {self.save.name}")


class App(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_TITLE)
        self.progress_min_interval_seconds = 0.08
        self.progress_fallback_threshold = 40
        self._op_animation_running = False
        self.set_default_size(800, 600)
        self.connect("destroy", Gtk.main_quit)
        self._load_css()

        icon = GdkPixbuf.Pixbuf.new_from_file(os.path.join(BASE_DIR, "icon.png"))
        self.set_icon(icon)

        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root_box.set_hexpand(True)
        root_box.set_vexpand(True)

        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)

        box_simple_use = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_simple_use.get_style_context().add_class("medias-root")
        tab_simple_use = self._build_tab_with_fallback_icon(
            "Simple use",
            [
                "face-smile-symbolic",
                "face-smile",
                "input-touchpad-symbolic",
                "gesture-tap-symbolic",
                "avatar-default-symbolic",
                "system-users-symbolic",
                "user-available-symbolic",
            ],
        )

        simple_use_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        simple_use_controls_box.get_style_context().add_class("media-controls")
        simple_use_controls_box.set_hexpand(True)
        simple_use_controls_box.set_size_request(-1, 76)

        self.refresh_simple_use_button = Gtk.Button()
        self.refresh_simple_use_button.set_tooltip_text("Refresh simple use")
        self.refresh_simple_use_button.add(
            Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        )
        self.refresh_simple_use_button.get_style_context().add_class("refresh-button")
        self.refresh_simple_use_button.connect("clicked", self._on_simple_use_refresh_clicked)
        simple_use_controls_box.pack_start(self.refresh_simple_use_button, False, False, 0)

        self.selected_media_info_box_simple_use = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.selected_media_info_box_simple_use.set_hexpand(True)
        self.selected_media_info_box_simple_use.set_margin_start(12)
        self.selected_media_info_box_simple_use.set_margin_end(8)
        self.selected_media_info_box_simple_use.get_style_context().add_class("selected-media-info")
        simple_use_controls_box.pack_start(self.selected_media_info_box_simple_use, True, True, 0)

        self.simple_use_op_check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.DIALOG)
        self.simple_use_op_check.get_style_context().add_class("media-valid")
        self.simple_use_op_check.set_margin_end(12)
        self.simple_use_op_check.set_no_show_all(True)
        simple_use_controls_box.pack_end(self.simple_use_op_check, False, False, 0)

        self.simple_use_op_spinner = Gtk.Spinner()
        self.simple_use_op_spinner.set_size_request(48, 48)
        self.simple_use_op_spinner.get_style_context().add_class("op-spinner")
        self.simple_use_op_spinner.set_margin_end(12)
        self.simple_use_op_spinner.set_no_show_all(True)
        simple_use_controls_box.pack_end(self.simple_use_op_spinner, False, False, 0)

        box_simple_use.pack_start(simple_use_controls_box, False, False, 0)

        self.simple_use_content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.simple_use_content_box.set_hexpand(True)
        self.simple_use_content_box.set_vexpand(True)

        self.simple_use_center_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        self.simple_use_center_row.set_halign(Gtk.Align.CENTER)
        self.simple_use_center_row.set_valign(Gtk.Align.CENTER)
        self.simple_use_center_row.get_style_context().add_class("simple-use-center-row")

        self.simple_use_left_status_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.DIALOG)
        self.simple_use_left_status_icon.get_style_context().add_class("simple-use-status-icon")
        self.simple_use_center_row.pack_start(self.simple_use_left_status_icon, False, False, 0)

        self.simple_use_pc_button = Gtk.Button()
        self.simple_use_pc_button.set_tooltip_text("Open first available local path")
        self.simple_use_pc_button.get_style_context().add_class("save-row-device-button")
        self.simple_use_pc_button.get_style_context().add_class("simple-use-device-button")
        simple_use_pc_icon = Gtk.Image.new_from_icon_name("computer-symbolic", Gtk.IconSize.DIALOG)
        simple_use_pc_icon.get_style_context().add_class("save-row-device-icon")
        simple_use_pc_icon.get_style_context().add_class("simple-use-device-icon")
        self.simple_use_pc_button.add(simple_use_pc_icon)
        self.simple_use_pc_button.connect("clicked", self._on_simple_use_pc_button_clicked)
        self.simple_use_center_row.pack_start(self.simple_use_pc_button, False, False, 0)

        self.simple_use_arrow_right = Gtk.Button()
        self.simple_use_arrow_right.set_tooltip_text("Copy all saves to media")
        self.simple_use_arrow_right.add(Gtk.Image.new_from_icon_name("go-next-symbolic", Gtk.IconSize.DIALOG))
        self.simple_use_arrow_right.get_style_context().add_class("save-row-arrow-right")
        self.simple_use_arrow_right.get_style_context().add_class("simple-use-arrow-button")
        self.simple_use_arrow_right.connect("clicked", self._on_simple_use_arrow_right_clicked)
        self.simple_use_center_row.pack_start(self.simple_use_arrow_right, False, False, 0)

        simple_use_separator = Gtk.Label(label="•••••••")
        simple_use_separator.get_style_context().add_class("save-row-separator")
        simple_use_separator.get_style_context().add_class("simple-use-separator")
        self.simple_use_center_row.pack_start(simple_use_separator, False, False, 0)

        self.simple_use_arrow_left = Gtk.Button()
        self.simple_use_arrow_left.set_tooltip_text("Restore all saves from media")
        self.simple_use_arrow_left.add(Gtk.Image.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.DIALOG))
        self.simple_use_arrow_left.get_style_context().add_class("save-row-arrow-left")
        self.simple_use_arrow_left.get_style_context().add_class("simple-use-arrow-button")
        self.simple_use_arrow_left.connect("clicked", self._on_simple_use_arrow_left_clicked)
        self.simple_use_center_row.pack_start(self.simple_use_arrow_left, False, False, 0)

        self.simple_use_usb_button = Gtk.Button()
        self.simple_use_usb_button.set_tooltip_text("Open first available target path")
        self.simple_use_usb_button.get_style_context().add_class("save-row-device-button")
        self.simple_use_usb_button.get_style_context().add_class("simple-use-device-button")
        simple_use_usb_icon = Gtk.Image.new_from_icon_name("drive-removable-media-symbolic", Gtk.IconSize.DIALOG)
        simple_use_usb_icon.get_style_context().add_class("save-row-device-icon")
        simple_use_usb_icon.get_style_context().add_class("simple-use-device-icon")
        self.simple_use_usb_button.add(simple_use_usb_icon)
        self.simple_use_usb_button.connect("clicked", self._on_simple_use_usb_button_clicked)
        self.simple_use_center_row.pack_start(self.simple_use_usb_button, False, False, 0)

        self.simple_use_right_status_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.DIALOG)
        self.simple_use_right_status_icon.get_style_context().add_class("simple-use-status-icon")
        self.simple_use_center_row.pack_start(self.simple_use_right_status_icon, False, False, 0)

        self.simple_use_content_box.pack_start(self.simple_use_center_row, True, True, 0)
        box_simple_use.pack_start(self.simple_use_content_box, True, True, 0)

        box_saves = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_saves.get_style_context().add_class("medias-root")

        saves_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        saves_controls_box.get_style_context().add_class("media-controls")
        saves_controls_box.set_hexpand(True)
        saves_controls_box.set_size_request(-1, 76)

        self.add_save_button = Gtk.Button(label="+ Add a save")
        self.add_save_button.get_style_context().add_class("add-media-button")
        self.add_save_button.connect("clicked", self._on_add_save_clicked)
        saves_controls_box.pack_start(self.add_save_button, False, False, 0)

        self.refresh_saves_button = Gtk.Button()
        self.refresh_saves_button.set_tooltip_text("Refresh saves list")
        self.refresh_saves_button.add(
            Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        )
        self.refresh_saves_button.get_style_context().add_class("refresh-button")
        self.refresh_saves_button.connect("clicked", self._on_saves_refresh_clicked)
        saves_controls_box.pack_start(self.refresh_saves_button, False, False, 0)

        # Keep Simple use media info aligned with other tabs by reserving
        # the same horizontal space as "Add save" + refresh (+ controls spacing).
        self.add_save_button.connect("size-allocate", self._sync_simple_use_refresh_button_width)
        self.refresh_saves_button.connect("size-allocate", self._sync_simple_use_refresh_button_width)

        self.selected_media_info_box_saves = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.selected_media_info_box_saves.set_hexpand(True)
        self.selected_media_info_box_saves.set_margin_start(12)
        self.selected_media_info_box_saves.set_margin_end(8)
        self.selected_media_info_box_saves.get_style_context().add_class("selected-media-info")
        saves_controls_box.pack_start(self.selected_media_info_box_saves, True, True, 0)

        self.saves_op_check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.DIALOG)
        self.saves_op_check.get_style_context().add_class("media-valid")
        self.saves_op_check.set_margin_end(12)
        self.saves_op_check.set_no_show_all(True)
        saves_controls_box.pack_end(self.saves_op_check, False, False, 0)

        self.saves_op_spinner = Gtk.Spinner()
        self.saves_op_spinner.set_size_request(48, 48)
        self.saves_op_spinner.get_style_context().add_class("op-spinner")
        self.saves_op_spinner.set_margin_end(12)
        self.saves_op_spinner.set_no_show_all(True)
        saves_controls_box.pack_end(self.saves_op_spinner, False, False, 0)

        box_saves.pack_start(saves_controls_box, False, False, 0)

        self.saves_list = Gtk.ListBox()
        self.saves_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.saves_list.get_style_context().add_class("media-list")

        saves_scroller = Gtk.ScrolledWindow()
        saves_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        saves_scroller.set_hexpand(True)
        saves_scroller.set_vexpand(True)
        saves_scroller.add(self.saves_list)
        box_saves.pack_start(saves_scroller, True, True, 0)
        tab_saves = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tab_saves.pack_start(Gtk.Image.new_from_icon_name("folder-symbolic", Gtk.IconSize.SMALL_TOOLBAR), False, False, 0)
        tab_saves_label = Gtk.Label(label="Saves")
        tab_saves_label.set_margin_top(12)
        tab_saves_label.set_margin_bottom(12)
        tab_saves.pack_start(tab_saves_label, False, False, 0)
        tab_saves.show_all()

        box_medias = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_medias.get_style_context().add_class("medias-root")

        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        controls_box.get_style_context().add_class("media-controls")
        controls_box.set_hexpand(True)
        controls_box.set_size_request(-1, 76)

        self.add_media_button = Gtk.Button(label="+ Add media")
        self.add_media_button.get_style_context().add_class("add-media-button")
        self.add_media_button.connect("clicked", self._on_add_media_clicked)
        controls_box.pack_start(self.add_media_button, False, False, 0)

        refresh_button = Gtk.Button()
        refresh_button.set_tooltip_text("Refresh media list")
        refresh_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_button.add(refresh_icon)
        refresh_button.get_style_context().add_class("refresh-button")
        refresh_button.connect("clicked", self._on_refresh_clicked)
        controls_box.pack_start(refresh_button, False, False, 0)

        self.selected_media_info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.selected_media_info_box.set_hexpand(True)
        self.selected_media_info_box.set_margin_start(12)
        self.selected_media_info_box.set_margin_end(8)
        self.selected_media_info_box.get_style_context().add_class("selected-media-info")
        controls_box.pack_start(self.selected_media_info_box, True, True, 0)

        self.folder_media_button = Gtk.Button()
        self.folder_media_button.set_tooltip_text("Open media folder")
        folder_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        self.folder_media_button.add(folder_icon)
        self.folder_media_button.get_style_context().add_class("folder-media-button")
        self.folder_media_button.connect("clicked", self._on_open_media_folder_clicked)
        controls_box.pack_start(self.folder_media_button, False, False, 0)

        self.edit_media_button = Gtk.Button()
        self.edit_media_button.set_tooltip_text("Edit selected media")
        edit_icon = Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.BUTTON)
        self.edit_media_button.add(edit_icon)
        self.edit_media_button.get_style_context().add_class("edit-media-button")
        self.edit_media_button.connect("clicked", self._on_edit_media_clicked)
        controls_box.pack_start(self.edit_media_button, False, False, 0)

        self.delete_media_button = Gtk.Button()
        self.delete_media_button.set_tooltip_text("Delete selected media")
        delete_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON)
        self.delete_media_button.add(delete_icon)
        self.delete_media_button.get_style_context().add_class("delete-media-button")
        self.delete_media_button.connect("clicked", self._on_delete_media_clicked)
        controls_box.pack_start(self.delete_media_button, False, False, 0)

        box_medias.pack_start(controls_box, False, False, 0)

        self.media_list = Gtk.ListBox()
        self.media_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.media_list.get_style_context().add_class("media-list")
        self.media_list.connect("row-activated", self._on_media_row_activated)

        list_scroller = Gtk.ScrolledWindow()
        list_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroller.set_hexpand(True)
        list_scroller.set_vexpand(True)
        list_scroller.add(self.media_list)
        box_medias.pack_start(list_scroller, True, True, 0)

        tab_medias = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tab_medias.pack_start(Gtk.Image.new_from_icon_name("drive-removable-media-symbolic", Gtk.IconSize.SMALL_TOOLBAR), False, False, 0)
        tab_medias_label = Gtk.Label(label="Medias")
        tab_medias_label.set_margin_top(12)
        tab_medias_label.set_margin_bottom(12)
        tab_medias.pack_start(tab_medias_label, False, False, 0)
        tab_medias.show_all()

        notebook.append_page(box_simple_use, tab_simple_use)
        notebook.child_set_property(box_simple_use, "tab-expand", True)

        notebook.append_page(box_medias, tab_medias)
        notebook.child_set_property(box_medias, "tab-expand", True)

        notebook.append_page(box_saves, tab_saves)
        notebook.child_set_property(box_saves, "tab-expand", True)

        root_box.pack_start(notebook, True, True, 0)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_box.get_style_context().add_class("status-bar")
        status_box.set_size_request(-1, 34)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0)
        self.status_label.get_style_context().add_class("status-label")
        self.status_label.set_margin_start(12)
        self.status_label.set_margin_end(12)
        status_box.pack_start(self.status_label, True, True, 0)

        root_box.pack_start(status_box, False, False, 0)

        self.add(root_box)
        self._refresh_media_list()

    def run(self):
        self.show_all()
        self._ensure_selected_media_consistency()
        self._refresh_media_list()
        self._refresh_media_dependent_views()
        Gtk.main()

    def _load_css(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_path(os.path.join(BASE_DIR, "style.css"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_tab_with_fallback_icon(self, label_text: str, icon_candidates: list[str]) -> Gtk.Box:
        icon_theme = Gtk.IconTheme.get_default()
        selected_icon = "avatar-default-symbolic"
        for icon_name in icon_candidates:
            if icon_theme.has_icon(icon_name):
                selected_icon = icon_name
                break

        tab = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tab.pack_start(Gtk.Image.new_from_icon_name(selected_icon, Gtk.IconSize.SMALL_TOOLBAR), False, False, 0)

        tab_label = Gtk.Label(label=label_text)
        tab_label.set_margin_top(12)
        tab_label.set_margin_bottom(12)
        tab.pack_start(tab_label, False, False, 0)
        tab.show_all()
        return tab

    def _get_selected_media_id(self) -> str:
        setting = get_current_setting()
        return getattr(setting, "selected_media_id", "")

    def _get_selected_media(self):
        media_id = self._get_selected_media_id()
        if not media_id:
            return None
        return get_media_by_id(media_id)

    def _refresh_media_dependent_views(self):
        media, saves = self._get_selected_media_and_saves()
        self._refresh_selected_media_info()
        self._refresh_selected_media_info_saves()
        self._refresh_selected_media_info_simple_use()
        self._refresh_saves_list(media=media, saves=saves)
        self._refresh_simple_use_center(media=media, saves=saves)
        self._update_add_save_button_state()

    def _ensure_selected_media_consistency(self):
        media_id = self._get_selected_media_id()
        if media_id and get_media_by_id(media_id) is not None:
            return

        first_media = get_first_media()
        if first_media is None:
            set_selected_media("", "")
            return

        set_selected_media(first_media._id, first_media.name)

    def _is_media_path_available(self, media) -> bool:
        return os.path.isdir(os.path.expanduser(media.path))

    def _auto_select_available_media_on_refresh(self) -> bool:
        selected_media = self._get_selected_media()
        if selected_media is not None and self._is_media_path_available(selected_media):
            return False

        for media in get_medias():
            if self._is_media_path_available(media):
                set_selected_media(media._id, media.name)
                return True

        return False

    def _refresh_media_list(self):
        for row in self.media_list.get_children():
            self.media_list.remove(row)

        medias = list(get_medias())
        if not medias:
            empty_row = Gtk.ListBoxRow()
            empty_row.set_activatable(False)
            empty_row.set_selectable(False)

            empty_label = Gtk.Label(label="No media yet. Add your first one above.")
            empty_label.set_xalign(0)
            empty_label.get_style_context().add_class("media-empty")
            empty_label.set_margin_top(20)
            empty_label.set_margin_bottom(20)
            empty_label.set_margin_start(20)
            empty_label.set_margin_end(20)

            empty_row.add(empty_label)
            self.media_list.add(empty_row)
            self.media_list.show_all()
            return

        selected_media_id = self._get_selected_media_id()
        selected_row = None

        for media in medias:
            row = MediaRow(media)
            self.media_list.add(row)
            if media._id == selected_media_id:
                selected_row = row

        # Ensure all rows start deselected
        for row in self.media_list.get_children():
            if isinstance(row, MediaRow):
                row.set_selected(False)

        self.media_list.show_all()
        # Then select only the target row
        if selected_row is not None:
            selected_row.set_selected(True)

    def _on_add_media_clicked(self, _button):
        dialog = AddMediaDialog(self)
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                break

            payload = dialog.get_media_data()
            if not payload:
                self._set_status("Invalid media input")
                dialog.show_all()
                continue

            if payload.get("cancelled"):
                self._set_status("Add media canceled")
                dialog.show_all()
                continue

            media_name = str(payload.get("name", "")).strip()
            media_description = str(payload.get("description", "")).strip()
            media_path = str(payload.get("path", "")).strip()
            media_id = payload.get("media_id")
            media_id = str(media_id).strip() if media_id else None
            profile_db_name = str(payload.get("profile_db_name", "")).strip()

            if not media_name or not media_path:
                self._set_status("Invalid media input")
                dialog.show_all()
                continue

            new_media = add_media(
                media_name,
                media_description,
                media_path,
                media_id=media_id,
                profile_db_name=profile_db_name,
            )
            dialog.destroy()
            self._select_media_by_id(new_media._id, new_media.name)
            self._set_status(f"Media added: {new_media.name}")
            return

        if response != Gtk.ResponseType.OK:
            self._set_status("Add media canceled")

        dialog.destroy()

    def _select_media_by_id(self, media_id: str, media_name: str | None = None):
        if media_name is None:
            media = get_media_by_id(media_id)
            if media is None:
                return False
            media_name = media.name

        if media_name is None:
            return False

        set_selected_media(media_id, media_name)
        self._refresh_media_list()
        return self._activate_media_row_by_id(media_id)

    def _activate_media_row_by_id(self, media_id: str) -> bool:
        # Deselect all other rows
        for row in self.media_list.get_children():
            if isinstance(row, MediaRow):
                row.set_selected(False)

        # Select target row
        for row in self.media_list.get_children():
            if getattr(row, "_id", None) == media_id:
                row.set_selected(True)
                row.grab_focus()
                self.media_list.emit("row-activated", row)
                return True

        return False

    def _on_media_row_activated(self, _list_box, row):
        media = getattr(row, "media", None)
        if media is None:
            return

        # Deselect all other rows
        for other_row in self.media_list.get_children():
            if isinstance(other_row, MediaRow) and other_row != row:
                other_row.set_selected(False)

        # Select this row
        if isinstance(row, MediaRow):
            row.set_selected(True)

        current_media_id = self._get_selected_media_id()
        if current_media_id != media._id:
            set_selected_media(media._id, media.name)

        self._refresh_media_dependent_views()
        self._set_status(f"Selected media: {media.name}")

    def _on_refresh_clicked(self, _button):
        self._auto_select_available_media_on_refresh()
        self._refresh_media_list()
        self._refresh_media_dependent_views()
        self._set_status("Media list refreshed")

    def _on_saves_refresh_clicked(self, _button):
        self._auto_select_available_media_on_refresh()
        self._refresh_media_list()
        self._refresh_media_dependent_views()
        self._set_status("Folders list refreshed")

    def _on_simple_use_refresh_clicked(self, _button):
        self._auto_select_available_media_on_refresh()
        self._refresh_media_list()
        self._refresh_media_dependent_views()
        self._set_status("Simple use refreshed")

    def _run_in_background(self, target):
        worker = threading.Thread(target=target, daemon=True)
        worker.start()

    def _queue_status_update(self, message: str):
        GLib.idle_add(self._set_status, message)

    def _show_incident_report(self, save_name: str, incidents: list[tuple[str, str, str]]):
        if not incidents:
            return
        RenameReportDialog(self, save_name, incidents)

    def _queue_incident_report(self, save_name: str, incidents: list[tuple[str, str, str]]):
        GLib.idle_add(self._show_incident_report, save_name, incidents)

    def _op_spinners_start(self):
        self._op_animation_running = True
        self._op_start_time = time.monotonic()
        for spinner in (self.saves_op_spinner, self.simple_use_op_spinner):
            spinner.show()
            spinner.start()
        for check in (self.saves_op_check, self.simple_use_op_check):
            check.hide()

    def _op_spinners_done(self):
        elapsed_ms = int((time.monotonic() - self._op_start_time) * 1000)
        delay_ms = max(0, 500 - elapsed_ms)
        GLib.timeout_add(delay_ms, self._op_show_check)

    def _op_show_check(self):
        for spinner in (self.saves_op_spinner, self.simple_use_op_spinner):
            spinner.stop()
            spinner.hide()
        for check in (self.saves_op_check, self.simple_use_op_check):
            check.show()
        GLib.timeout_add(1000, self._op_hide_check)
        return False

    def _op_hide_check(self):
        self._op_animation_running = False
        for check in (self.saves_op_check, self.simple_use_op_check):
            check.hide()
        return False

    def _make_file_progress_callback(self, action: str, save_name: str):
        state = {
            "started": time.monotonic(),
            "last_update": 0.0,
            "file_count": 0,
            "fallback_counter": False,
        }

        def _on_file_progress(file_name: str):
            state["file_count"] += 1
            now = time.monotonic()

            if (
                not state["fallback_counter"]
                and state["file_count"] >= self.progress_fallback_threshold
                and (now - state["started"] <= 1.0)
            ):
                state["fallback_counter"] = True

            if now - state["last_update"] < self.progress_min_interval_seconds:
                return

            state["last_update"] = now
            if state["fallback_counter"]:
                message = f"{action} {save_name}... [{state['file_count']}] files copied"
            else:
                display_name = file_name
                if len(display_name) > 96:
                    display_name = f"...{display_name[-93:]}"
                message = f"{action} {save_name}... [{state['file_count']}] {display_name}"

            self._queue_status_update(message)

        return _on_file_progress

    def _start_save_operation(self, save: Save, media, to_media: bool):
        if to_media and not os.path.isdir(os.path.expanduser(save.local_path)):
            rebound = self._prompt_rebind_save(save, media)
            if not rebound:
                self._set_status(f"Local path not configured for {save.name}")
                return

            refreshed_save = None
            for candidate in get_saves(media):
                if candidate._id == save._id:
                    refreshed_save = candidate
                    break
            if refreshed_save is not None:
                save = refreshed_save

        action = "Saving" if to_media else "Restoring"
        self._queue_status_update(f"{action} {save.name}...")
        self._op_spinners_start()

        def _worker():
            progress_cb = self._make_file_progress_callback(action, save.name)
            try:
                if to_media:
                    sync_media_metadata_to_support(media)
                    incidents = copy_local_to_target(
                        local_path=save.local_path,
                        target_path=save.target_path,
                        media_path=media.path,
                        on_file_progress=progress_cb,
                    )
                else:
                    incidents = copy_target_to_local(
                        target_path=save.target_path,
                        local_path=save.local_path,
                        on_file_progress=progress_cb,
                    )

                GLib.idle_add(self._refresh_media_dependent_views)
                if incidents:
                    self._queue_incident_report(save.name, incidents)

                if to_media:
                    self._queue_status_update("Copy complete (merge)")
                else:
                    self._queue_status_update("Restore complete (merge)")
            except BackupLogicError as e:
                self._queue_incident_report(save.name, [(f"Error | save: {save.name}", str(e), "")])
                self._queue_status_update(str(e))
            except Exception as e:
                self._queue_incident_report(save.name, [(f"Error | save: {save.name}", str(e), "")])
                if to_media:
                    self._queue_status_update(f"Copy failed: {e}")
                else:
                    self._queue_status_update(f"Restore failed: {e}")
            finally:
                GLib.idle_add(self._op_spinners_done)

        self._run_in_background(_worker)

    def _get_selected_media_and_saves(self):
        media = self._get_selected_media()
        if media is None:
            return None, []

        if not os.path.isdir(os.path.expanduser(media.path)):
            return media, []

        saves = list(get_saves(media))
        return media, saves

    def _compute_simple_use_aggregate_status(self, saves: list[Save]) -> tuple[bool, bool]:
        if not saves:
            return False, False

        all_on_pc = all(os.path.isdir(os.path.expanduser(save.local_path)) for save in saves)
        all_on_usb = all(os.path.isdir(os.path.expanduser(save.target_path)) for save in saves)
        return all_on_pc, all_on_usb

    def _set_simple_use_status_icon(self, icon: Gtk.Image, is_available: bool):
        icon_name = "emblem-ok-symbolic" if is_available else "window-close-symbolic"
        icon.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        style_context = icon.get_style_context()
        if is_available:
            style_context.add_class("media-valid")
            style_context.remove_class("media-invalid")
        else:
            style_context.add_class("media-invalid")
            style_context.remove_class("media-valid")

    def _refresh_simple_use_center(self, media=None, saves: list[Save] | None = None):
        if media is None or saves is None:
            media, saves = self._get_selected_media_and_saves()

        assert saves is not None
        all_on_pc, all_on_usb = self._compute_simple_use_aggregate_status(saves)

        self._set_simple_use_status_icon(self.simple_use_left_status_icon, all_on_pc)
        self._set_simple_use_status_icon(self.simple_use_right_status_icon, all_on_usb)

        has_saves = len(saves) > 0
        any_pc_available = any(os.path.isdir(os.path.expanduser(save.local_path)) for save in saves)
        media_path_available = media is not None and os.path.isdir(os.path.expanduser(media.path))

        self.simple_use_arrow_right.set_sensitive(has_saves)
        self.simple_use_arrow_left.set_sensitive(has_saves)
        self.simple_use_pc_button.set_sensitive(any_pc_available)
        self.simple_use_usb_button.set_sensitive(media_path_available)

        if media is None:
            self.simple_use_arrow_right.set_tooltip_text("No selected media")
            self.simple_use_arrow_left.set_tooltip_text("No selected media")
            return

        self.simple_use_arrow_right.set_tooltip_text(f"Copy all saves of {media.name} to media")
        self.simple_use_arrow_left.set_tooltip_text(f"Restore all saves of {media.name} from media")

    def _on_simple_use_pc_button_clicked(self, _button):
        media, saves = self._get_selected_media_and_saves()
        if media is None:
            self._set_status("No media selected")
            return

        for save in saves:
            expanded_path = os.path.expanduser(save.local_path)
            if os.path.isdir(expanded_path):
                try:
                    subprocess.Popen(["xdg-open", expanded_path])
                    self._set_status(f"Opened local path: {expanded_path}")
                except Exception as e:
                    self._set_status(f"Error opening file explorer: {e}")
                return

        self._set_status("No available local path among selected media saves")

    def _on_simple_use_usb_button_clicked(self, _button):
        media, _saves = self._get_selected_media_and_saves()
        if media is None:
            self._set_status("No media selected")
            return

        expanded_path = os.path.expanduser(media.path)
        if not os.path.isdir(expanded_path):
            self._set_status("Media path does not exist")
            return

        try:
            subprocess.Popen(["xdg-open", expanded_path])
            self._set_status(f"Opened media path: {expanded_path}")
        except Exception as e:
            self._set_status(f"Error opening file explorer: {e}")

    def _run_simple_use_batch(self, to_media: bool):
        media, saves = self._get_selected_media_and_saves()
        if media is None:
            self._set_status("No media selected")
            return

        if not saves:
            self._set_status("No saves available for selected media")
            return

        skipped_rebind: list[str] = []
        saves_to_process = saves
        if to_media:
            saves_to_process, skipped_rebind = self._prepare_batch_saves_for_media_copy(media, saves)
            if not saves_to_process:
                if skipped_rebind:
                    skipped_count = len(skipped_rebind)
                    self._set_status(
                        f"Batch canceled: {skipped_count} save(s) require local rebind"
                    )
                else:
                    self._set_status("No save ready for batch copy")
                return

        action = "Saving" if to_media else "Restoring"
        self._queue_status_update(f"{action} {saves_to_process[0].name}...")
        self._op_spinners_start()

        def _worker():
            success_count = 0
            failure_count = 0
            errors: list[str] = []
            incident_entries: list[tuple[str, str, str]] = []

            for save in saves_to_process:
                self._queue_status_update(f"{action} {save.name}...")
                progress_cb = self._make_file_progress_callback(action, save.name)
                try:
                    if to_media:
                        sync_media_metadata_to_support(media)
                        incidents = copy_local_to_target(
                            local_path=save.local_path,
                            target_path=save.target_path,
                            media_path=media.path,
                            on_file_progress=progress_cb,
                        )
                    else:
                        incidents = copy_target_to_local(
                            target_path=save.target_path,
                            local_path=save.local_path,
                            on_file_progress=progress_cb,
                        )

                    success_count += 1
                    for reason, original, final in incidents:
                        incident_entries.append((f"{reason} | save: {save.name}", original, final))
                except BackupLogicError as e:
                    failure_count += 1
                    error_message = f"{save.name}: {e}"
                    errors.append(error_message)
                    incident_entries.append((f"Error | save: {save.name}", str(e), ""))
                except Exception as e:
                    failure_count += 1
                    error_message = f"{save.name}: {e}"
                    errors.append(error_message)
                    incident_entries.append((f"Error | save: {save.name}", str(e), ""))

            GLib.idle_add(self._refresh_media_dependent_views)

            if skipped_rebind:
                for save_name in skipped_rebind:
                    incident_entries.append(
                        (
                            f"Skipped (rebind required) | save: {save_name}",
                            "Local path is not configured",
                            "",
                        )
                    )

            if incident_entries:
                self._queue_incident_report(f"{media.name} (Simple use batch)", incident_entries)

            if failure_count == 0:
                if to_media:
                    if skipped_rebind:
                        self._queue_status_update(
                            f"Batch copy complete: {success_count} save(s), {len(skipped_rebind)} skipped (rebind required)"
                        )
                    else:
                        self._queue_status_update(f"Batch copy complete: {success_count} save(s)")
                else:
                    self._queue_status_update(f"Batch restore complete: {success_count} save(s)")
                GLib.idle_add(self._op_spinners_done)
                return

            first_error = errors[0] if errors else "unknown error"
            if to_media:
                if skipped_rebind:
                    first_error = f"{first_error}. {len(skipped_rebind)} skipped (rebind required)"
                self._queue_status_update(
                    f"Batch copy finished with errors ({success_count} ok / {failure_count} failed). First error: {first_error}"
                )
            else:
                self._queue_status_update(
                    f"Batch restore finished with errors ({success_count} ok / {failure_count} failed). First error: {first_error}"
                )
            GLib.idle_add(self._op_spinners_done)

        self._run_in_background(_worker)

    def _prepare_batch_saves_for_media_copy(self, media, saves: list[Save]) -> tuple[list[Save], list[str]]:
        ready_saves: list[Save] = []
        skipped_saves: list[str] = []

        for save in saves:
            if os.path.isdir(os.path.expanduser(save.local_path)):
                ready_saves.append(save)
                continue

            self._set_status(f"Local path missing for {save.name}. Please choose a folder.")
            rebound = self._prompt_rebind_save(save, media)
            if not rebound:
                skipped_saves.append(save.name)
                continue

            refreshed_save = None
            for candidate in get_saves(media):
                if candidate._id == save._id:
                    refreshed_save = candidate
                    break

            if refreshed_save is None or not os.path.isdir(os.path.expanduser(refreshed_save.local_path)):
                skipped_saves.append(save.name)
                continue

            ready_saves.append(refreshed_save)

        return ready_saves, skipped_saves

    def _on_simple_use_arrow_right_clicked(self, _button):
        if self._op_animation_running:
            return
        self._run_simple_use_batch(to_media=True)

    def _on_simple_use_arrow_left_clicked(self, _button):
        if self._op_animation_running:
            return
        self._run_simple_use_batch(to_media=False)

    def _prompt_rebind_save(self, save: Save, media) -> bool:
        chooser = Gtk.FileChooserDialog(
            title=f"Choose local folder for '{save.name}'",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        chooser.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Bind", Gtk.ResponseType.OK,
        )

        response = chooser.run()
        if response != Gtk.ResponseType.OK:
            chooser.destroy()
            return False

        selected_folder = chooser.get_filename()
        chooser.destroy()

        if not selected_folder or not os.path.isdir(selected_folder):
            self._set_status("Invalid local path selected")
            return False

        set_save_local_binding(media, save._id, selected_folder)
        self._refresh_media_dependent_views()
        self._set_status(f"Local path configured for save: {save.name}")
        return True

    def _sync_simple_use_refresh_button_width(self, *_args):
        if not hasattr(self, "refresh_simple_use_button"):
            return

        add_width = self.add_save_button.get_allocated_width()
        refresh_width = self.refresh_saves_button.get_allocated_width()
        if add_width <= 0 or refresh_width <= 0:
            return

        # 8 matches controls box spacing used in both banners.
        combined_width = add_width + refresh_width + 8
        self.refresh_simple_use_button.set_size_request(combined_width, -1)

    def _set_status(self, message: str):
        self.status_label.set_text(message)

    def _refresh_selected_media_info(self):
        for child in self.selected_media_info_box.get_children():
            self.selected_media_info_box.remove(child)

        media_id = self._get_selected_media_id()
        show_delete = False
        media_path_exists = False

        if not media_id:
            no_media_label = Gtk.Label(label="Please add a media")
            no_media_label.get_style_context().add_class("no-media-label")
            no_media_label.set_xalign(0)
            self.selected_media_info_box.pack_start(no_media_label, False, False, 0)
        else:
            media = get_media_by_id(media_id)
            if media is None:
                no_media_label = Gtk.Label(label="Please add a media")
                no_media_label.get_style_context().add_class("no-media-label")
                no_media_label.set_xalign(0)
                self.selected_media_info_box.pack_start(no_media_label, False, False, 0)
            else:
                show_delete = True
                media_path_exists = os.path.isdir(os.path.expanduser(media.path))
                icon_name = "emblem-ok-symbolic" if media_path_exists else "window-close-symbolic"
                icon_class = "media-valid" if media_path_exists else "media-invalid"
                validity_icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DND)
                validity_icon.get_style_context().add_class(icon_class)

                info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                info_box.set_margin_start(6)

                name_label = Gtk.Label(label=media.name)
                name_label.set_xalign(0)
                name_label.get_style_context().add_class("selected-media-name")

                path_label = Gtk.Label(label=media.path)
                path_label.set_xalign(0)
                path_label.get_style_context().add_class("selected-media-path")

                info_box.pack_start(name_label, False, False, 0)
                info_box.pack_start(path_label, False, False, 0)

                if media.description:
                    desc_label = Gtk.Label(label=media.description)
                    desc_label.set_xalign(0)
                    desc_label.get_style_context().add_class("selected-media-path")
                    info_box.pack_start(desc_label, False, False, 0)

                self.selected_media_info_box.pack_start(validity_icon, False, False, 0)
                self.selected_media_info_box.pack_start(info_box, True, True, 0)

        self.selected_media_info_box.show_all()
        if show_delete:
            self.folder_media_button.show_all()
            self.folder_media_button.set_sensitive(media_path_exists)
            self.edit_media_button.show_all()
            self.delete_media_button.show_all()
        else:
            self.folder_media_button.hide()
            self.edit_media_button.hide()
            self.delete_media_button.hide()

    def _on_open_media_folder_clicked(self, _button):
        media_id = self._get_selected_media_id()

        if not media_id:
            self._set_status("No media selected")
            return

        media = get_media_by_id(media_id)
        if media is None:
            self._set_status("Selected media not found")
            return

        expanded_path = os.path.expanduser(media.path)
        if not os.path.isdir(expanded_path):
            self._set_status("Media path does not exist")
            return

        try:
            subprocess.Popen(["xdg-open", expanded_path])
            self._set_status(f"Opened media folder: {expanded_path}")
        except Exception as e:
            self._set_status(f"Error opening file explorer: {e}")

    def _on_edit_media_clicked(self, _button):
        media_id = self._get_selected_media_id()

        if not media_id:
            return

        media = get_media_by_id(media_id)
        if media is None:
            self._set_status("Selected media not found")
            return

        dialog = EditMediaDialog(self, media.name, media.description)
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                self._set_status("Edit canceled")
                break

            payload = dialog.get_media_data()
            if not payload:
                dialog.show_all()
                continue

            updated_media = update_media(media_id, payload["name"], payload["description"])
            if updated_media is None:
                self._set_status("Unable to update media")
                break

            self._select_media_by_id(updated_media._id, updated_media.name)
            self._set_status(f"Media updated: {updated_media.name}")
            break

        dialog.destroy()

    def _refresh_selected_media_info_box(self, info_box: Gtk.Box):
        for child in info_box.get_children():
            info_box.remove(child)

        media_id = self._get_selected_media_id()

        if not media_id:
            no_media_label = Gtk.Label(label="Please add a media")
            no_media_label.get_style_context().add_class("no-media-label")
            no_media_label.set_xalign(0)
            info_box.pack_start(no_media_label, False, False, 0)
            info_box.show_all()
            return

        media = get_media_by_id(media_id)
        if media is None:
            no_media_label = Gtk.Label(label="Please add a media")
            no_media_label.get_style_context().add_class("no-media-label")
            no_media_label.set_xalign(0)
            info_box.pack_start(no_media_label, False, False, 0)
            info_box.show_all()
            return

        is_valid = os.path.isdir(os.path.expanduser(media.path))
        icon_name = "emblem-ok-symbolic" if is_valid else "window-close-symbolic"
        icon_class = "media-valid" if is_valid else "media-invalid"
        validity_icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DND)
        validity_icon.get_style_context().add_class(icon_class)

        media_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        media_info_box.set_margin_start(6)

        name_label = Gtk.Label(label=media.name)
        name_label.set_xalign(0)
        name_label.get_style_context().add_class("selected-media-name")

        path_label = Gtk.Label(label=media.path)
        path_label.set_xalign(0)
        path_label.get_style_context().add_class("selected-media-path")

        media_info_box.pack_start(name_label, False, False, 0)
        media_info_box.pack_start(path_label, False, False, 0)

        if media.description:
            desc_label = Gtk.Label(label=media.description)
            desc_label.set_xalign(0)
            desc_label.get_style_context().add_class("selected-media-path")
            media_info_box.pack_start(desc_label, False, False, 0)

        info_box.pack_start(validity_icon, False, False, 0)
        info_box.pack_start(media_info_box, True, True, 0)
        info_box.show_all()

    def _refresh_selected_media_info_saves(self):
        self._refresh_selected_media_info_box(self.selected_media_info_box_saves)

    def _refresh_selected_media_info_simple_use(self):
        self._refresh_selected_media_info_box(self.selected_media_info_box_simple_use)

    def _on_delete_media_clicked(self, _button):
        media_id = self._get_selected_media_id()
        media_name = getattr(get_current_setting(), "selected_media_name", "")

        if not media_id:
            return

        dialog = DeleteMediaDialog(self, media_name)
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            self._set_status("Delete canceled")
            return

        delete_media_by_id(media_id)

        first_media = get_first_media()
        if first_media:
            set_selected_media(first_media._id, first_media.name)
            self._set_status(f"Media deleted. Now selected: {first_media.name}")
        else:
            set_selected_media("", "")
            self._set_status("Media deleted. No media remaining.")

        self._refresh_media_list()
        self._refresh_media_dependent_views()

    def _refresh_saves_list(self, media=None, saves: list[Save] | None = None):
        for row in self.saves_list.get_children():
            self.saves_list.remove(row)

        if media is None:
            media_id = self._get_selected_media_id()
            if not media_id:
                self._add_saves_empty_row("No media selected.")
                return

            media = get_media_by_id(media_id)

        if media is None:
            self._add_saves_empty_row("No media selected.")
            return

        if not os.path.isdir(os.path.expanduser(media.path)):
            self._add_saves_empty_row(f"Media path is unavailable: {media.path}")
            return

        if saves is None:
            saves = get_saves(media)

        if not saves:
            self._add_saves_empty_row("No saves yet. Add your first one above.")
            return

        for save in saves:
            self.saves_list.add(SaveRow(self, save, media, self._refresh_saves_list, self._set_status, self._set_status))

        self.saves_list.show_all()

    def _update_add_save_button_state(self):
        media_id = self._get_selected_media_id()

        if not media_id:
            self.add_save_button.set_sensitive(False)
            return

        media = get_media_by_id(media_id)
        if media is None:
            self.add_save_button.set_sensitive(False)
            return

        is_available = os.path.isdir(os.path.expanduser(media.path))
        self.add_save_button.set_sensitive(is_available)
        if not is_available:
            self._set_status("Media unavailable: cannot add save")

    def _add_saves_empty_row(self, message: str):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_selectable(False)

        label = Gtk.Label(label=message)
        label.set_xalign(0)
        label.get_style_context().add_class("media-empty")
        label.set_margin_top(20)
        label.set_margin_bottom(20)
        label.set_margin_start(20)
        label.set_margin_end(20)

        row.add(label)
        self.saves_list.add(row)
        self.saves_list.show_all()

    def _on_add_save_clicked(self, _button):
        media_id = self._get_selected_media_id()
        if not media_id:
            self._set_status("No media selected. Select a media first.")
            return

        media = get_media_by_id(media_id)
        if media is None:
            self._set_status("Selected media not found.")
            return

        if not os.path.isdir(os.path.expanduser(media.path)):
            self._set_status("Media unavailable: cannot add save")
            self._update_add_save_button_state()
            return

        dialog = AddSaveDialog(self, media)
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                break

            payload = dialog.get_save_data()
            if not payload:
                dialog.show_all()
                continue

            try:
                new_save = add_save(media, payload["name"], payload["local_path"], payload["target_path"])
                dialog.destroy()
                self._refresh_saves_list()
                self._set_status(f"Save added: {new_save.name}")
                return
            except ValueError as e:
                self._set_status(f"Error: {e}")
            break

        if response != Gtk.ResponseType.OK:
            self._set_status("Add save canceled")

        dialog.destroy()
