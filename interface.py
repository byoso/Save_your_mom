import os
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, Gdk

from api import (
    add_media,
    get_medias,
    set_selected_media,
    get_current_setting,
    get_media_by_id,
    delete_media_by_id,
    get_first_media,
    get_saves,
    add_save,
    delete_save_by_id,
    rename_save,
)
from media_dialog import AddMediaDialog, DeleteMediaDialog, AddSaveDialog, DeleteSaveDialog, RenameSaveDialog

APP_TITLE = "Save Your Mom (and mine !)"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MediaRow(Gtk.ListBoxRow):
    def __init__(self, media):
        super().__init__()
        self.media = media
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

        if media.desctiption:
            description_label = Gtk.Label(label=media.desctiption)
            description_label.set_xalign(0)
            description_label.get_style_context().add_class("media-description")
            content.pack_start(description_label, False, False, 0)

        self.add(content)


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
        self.get_style_context().add_class("media-row")

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
        local_is_valid = os.path.isdir(os.path.expanduser(save.local_path))
        local_icon_name = "emblem-ok-symbolic" if local_is_valid else "window-close-symbolic"
        local_icon_class = "media-valid" if local_is_valid else "media-invalid"
        local_validity_icon = Gtk.Image.new_from_icon_name(local_icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        local_validity_icon.get_style_context().add_class(local_icon_class)
        center_group.pack_start(local_validity_icon, False, False, 0)

        pc_button = Gtk.Button()
        pc_button.set_tooltip_text(save.local_path)
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
        arrow_right.set_tooltip_text("Copy to media (coming soon)")
        arrow_right.add(Gtk.Image.new_from_icon_name("go-next-symbolic", Gtk.IconSize.BUTTON))
        arrow_right.get_style_context().add_class("save-row-arrow-right")
        arrow_right.set_sensitive(False)
        center_group.pack_start(arrow_right, False, False, 0)

        separator_label = Gtk.Label(label="•••••••")
        separator_label.get_style_context().add_class("save-row-separator")
        separator_label.set_margin_start(10)
        separator_label.set_margin_end(10)
        center_group.pack_start(separator_label, False, False, 0)

        arrow_left = Gtk.Button()
        arrow_left.set_tooltip_text("Restore from media (coming soon)")
        arrow_left.add(Gtk.Image.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.BUTTON))
        arrow_left.get_style_context().add_class("save-row-arrow-left")
        arrow_left.set_sensitive(False)
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
        # Open file explorer to local_path if it exists, otherwise show status message
        expanded_path = os.path.expanduser(path)
        if os.path.isdir(expanded_path):
            try:
                subprocess.Popen(["xdg-open", expanded_path])
            except Exception as e:
                self.on_set_status(f"Error opening file explorer: {e}")
        else:
            self.on_set_status("Path does not exist")

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

        box_simple_use = Gtk.Box()
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

        self.selected_media_info_box_saves = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.selected_media_info_box_saves.set_hexpand(True)
        self.selected_media_info_box_saves.set_margin_start(12)
        self.selected_media_info_box_saves.set_margin_end(8)
        self.selected_media_info_box_saves.get_style_context().add_class("selected-media-info")
        saves_controls_box.pack_start(self.selected_media_info_box_saves, True, True, 0)

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

        self.delete_media_button = Gtk.Button()
        self.delete_media_button.set_tooltip_text("Delete selected media")
        delete_icon = Gtk.Image.new_from_icon_name("list-remove-symbolic", Gtk.IconSize.BUTTON)
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
        self._refresh_selected_media_info()
        self._refresh_selected_media_info_saves()
        self._refresh_saves_list()
        self._update_add_save_button_state()
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

        for media in medias:
            self.media_list.add(MediaRow(media))

        self.media_list.show_all()

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

            new_media = add_media(payload["name"], payload["description"], payload["path"])
            set_selected_media(new_media._id, new_media.name)
            self._refresh_media_list()
            self._refresh_selected_media_info()
            self._refresh_selected_media_info_saves()
            self._refresh_saves_list()
            self._update_add_save_button_state()
            self._set_status(f"Media added and selected: {new_media.name}")
            break

        if response != Gtk.ResponseType.OK:
            self._set_status("Add media canceled")

        dialog.destroy()

    def _on_media_row_activated(self, _list_box, row):
        media = getattr(row, "media", None)
        if media is None:
            return

        set_selected_media(media._id, media.name)
        self._refresh_selected_media_info()
        self._refresh_selected_media_info_saves()
        self._refresh_saves_list()
        self._update_add_save_button_state()
        self._set_status(f"Selected media: {media.name}")
        print(media)

    def _on_refresh_clicked(self, _button):
        self._refresh_media_list()
        self._refresh_selected_media_info()
        self._refresh_selected_media_info_saves()
        self._refresh_saves_list()
        self._update_add_save_button_state()
        self._set_status("Media list refreshed")

    def _on_saves_refresh_clicked(self, _button):
        self._refresh_selected_media_info_saves()
        self._refresh_saves_list()
        self._update_add_save_button_state()
        self._set_status("Folders list refreshed")

    def _set_status(self, message: str):
        self.status_label.set_text(message)

    def _refresh_selected_media_info(self):
        for child in self.selected_media_info_box.get_children():
            self.selected_media_info_box.remove(child)

        setting = get_current_setting()
        media_id = getattr(setting, "selected_media_id", "")
        show_delete = False

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
                is_valid = os.path.isdir(os.path.expanduser(media.path))
                icon_name = "emblem-ok-symbolic" if is_valid else "window-close-symbolic"
                icon_class = "media-valid" if is_valid else "media-invalid"
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

                if media.desctiption:
                    desc_label = Gtk.Label(label=media.desctiption)
                    desc_label.set_xalign(0)
                    desc_label.get_style_context().add_class("selected-media-path")
                    info_box.pack_start(desc_label, False, False, 0)

                self.selected_media_info_box.pack_start(validity_icon, False, False, 0)
                self.selected_media_info_box.pack_start(info_box, True, True, 0)

        self.selected_media_info_box.show_all()
        if show_delete:
            self.delete_media_button.show_all()
        else:
            self.delete_media_button.hide()

    def _refresh_selected_media_info_saves(self):
        for child in self.selected_media_info_box_saves.get_children():
            self.selected_media_info_box_saves.remove(child)

        setting = get_current_setting()
        media_id = getattr(setting, "selected_media_id", "")

        if not media_id:
            no_media_label = Gtk.Label(label="Please add a media")
            no_media_label.get_style_context().add_class("no-media-label")
            no_media_label.set_xalign(0)
            self.selected_media_info_box_saves.pack_start(no_media_label, False, False, 0)
            self.selected_media_info_box_saves.show_all()
            return

        media = get_media_by_id(media_id)
        if media is None:
            no_media_label = Gtk.Label(label="Please add a media")
            no_media_label.get_style_context().add_class("no-media-label")
            no_media_label.set_xalign(0)
            self.selected_media_info_box_saves.pack_start(no_media_label, False, False, 0)
            self.selected_media_info_box_saves.show_all()
            return

        is_valid = os.path.isdir(os.path.expanduser(media.path))
        icon_name = "emblem-ok-symbolic" if is_valid else "window-close-symbolic"
        icon_class = "media-valid" if is_valid else "media-invalid"
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

        if media.desctiption:
            desc_label = Gtk.Label(label=media.desctiption)
            desc_label.set_xalign(0)
            desc_label.get_style_context().add_class("selected-media-path")
            info_box.pack_start(desc_label, False, False, 0)

        self.selected_media_info_box_saves.pack_start(validity_icon, False, False, 0)
        self.selected_media_info_box_saves.pack_start(info_box, True, True, 0)
        self.selected_media_info_box_saves.show_all()

    def _on_delete_media_clicked(self, _button):
        setting = get_current_setting()
        media_id = getattr(setting, "selected_media_id", "")
        media_name = getattr(setting, "selected_media_name", "")

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
        self._refresh_selected_media_info()
        self._refresh_selected_media_info_saves()
        self._refresh_saves_list()
        self._update_add_save_button_state()

    def _refresh_saves_list(self):
        for row in self.saves_list.get_children():
            self.saves_list.remove(row)

        setting = get_current_setting()
        media_id = getattr(setting, "selected_media_id", "")

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

        saves = get_saves(media)
        if not saves:
            self._add_saves_empty_row("No saves yet. Add your first one above.")
            return

        for save in saves:
            self.saves_list.add(SaveRow(self, save, media, self._refresh_saves_list, self._set_status, self._set_status))

        self.saves_list.show_all()

    def _update_add_save_button_state(self):
        setting = get_current_setting()
        media_id = getattr(setting, "selected_media_id", "")

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
        setting = get_current_setting()
        media_id = getattr(setting, "selected_media_id", "")
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
                self._refresh_saves_list()
                self._set_status(f"Save added: {new_save.name}")
            except ValueError as e:
                self._set_status(f"Error: {e}")
            break

        if response != Gtk.ResponseType.OK:
            self._set_status("Add save canceled")

        dialog.destroy()
