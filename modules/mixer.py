import math
import json
import gi
from fabric.audio.service import Audio
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.button import Button
from gi.repository import GLib
import subprocess

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk

import config.data as data

vertical_mode = (
    True
    if data.PANEL_THEME == "Panel"
    and (
        data.BAR_POSITION in ["Left", "Right"]
        or data.PANEL_POSITION in ["Start", "End"]
    )
    else False
)


class MixerSlider(Scale):
    def __init__(self, stream, bind_label=None, label_text="", **kwargs):
        super().__init__(
            name="control-slider",
            orientation="h",
            h_expand=True,
            h_align="fill",
            has_origin=True,
            increments=(0.01, 0.1),
            style_classes=["no-icon"],
            **kwargs,
        )
        self.bind_label = bind_label
        self.label_text = label_text
        self.add_events(Gdk.EventMask.SCROLL_MASK)
        self.connect("scroll-event", self.on_scroll)
        self.stream = stream
        self._updating_from_stream = False
        self.set_value(stream.volume / 100)
        self.set_size_request(-1, 30)  # Fixed height for sliders

        self.connect("value-changed", self.on_value_changed)
        stream.connect("changed", self.on_stream_changed)
        

        # Apply appropriate style class based on stream type
        if hasattr(stream, "type"):
            if "microphone" in stream.type.lower() or "input" in stream.type.lower():
                self.add_style_class("mic")
            else:
                self.add_style_class("vol")
        else:
            # Default to volume style
            self.add_style_class("vol")

        # Set initial tooltip and muted state
        self.set_tooltip_text(f"{stream.volume:.0f}%")
        self.update_muted_state()
    def on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            _, _, dy = event.get_scroll_deltas()
            step = -0.02 if dy > 0 else 0.02
        else:
            step = 0.02 if event.direction == Gdk.ScrollDirection.UP else -0.02

        self.set_value(max(0.0, min(1.0, self.get_value() + step)))
        return True

    def on_value_changed(self, _):
        if self._updating_from_stream:
            return
        if self.stream:
            self.stream.volume = self.value * 100
            display_vol = int(self.value * 100)
            vol_str = f"{display_vol}"
            self.set_tooltip_text(vol_str)

            if self.bind_label:
                self.bind_label.set_label(f"[{vol_str}] {self.label_text}")

    def on_stream_changed(self, stream):
        self._updating_from_stream = True
        self.value = stream.volume / 100
        display_vol = int(stream.volume)
        vol_str = f"{display_vol}"
        
        self.set_tooltip_text(vol_str)
        if self.bind_label:
            self.bind_label.set_label(f"[{vol_str}] {self.label_text}")
        self.update_muted_state()
        self._updating_from_stream = False

    def update_muted_state(self):
        if self.stream.muted:
            self.add_style_class("muted")
        else:
            self.remove_style_class("muted")


class MixerSection(Box):
    def __init__(self, title, is_outputs, audio_service, **kwargs):
        super().__init__(
            name="mixer-section",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=False,  # Prevent vertical stretching
        )
        self.is_outputs = is_outputs
        self.audio = audio_service
        self.header_box = Box(
            name="mixer-section-header",
            orientation="h",
            spacing=8,
            h_expand=True,
        )
        self.title_label = Label(
            name="mixer-section-title",
            label=title,
            h_expand=True,
            h_align="start",
        )
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.content_box = Box(
            name="mixer-content",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=False,
        )
        self.stack.add_named(self.content_box, "streams")

        self.devices_box = Box(orientation="v", spacing=4)
        self.stack.add_named(self.devices_box, "devices")

        self.is_devices_tab = False
        self.tab_btn = Button(
            label="Devices",
            on_clicked=self.toggle_tab
        )
        self.header_box.add(self.title_label)
        self.header_box.add(self.tab_btn)

        self.add(self.header_box)
        self.add(self.stack)

    def toggle_tab(self, btn):
        self.is_devices_tab = not self.is_devices_tab
        if self.is_devices_tab:
            self.stack.set_visible_child_name("devices")
            btn.set_label("Streams")
        else:
            self.stack.set_visible_child_name("streams")
            btn.set_label("Devices")
    def update_devices(self):
        for child in self.devices_box.get_children():
            self.devices_box.remove(child)
        devices = self.audio.speakers if self.is_outputs else self.audio.microphones
        active = self.audio.speaker if self.is_outputs else self.audio.microphone
        for dev in devices:
            is_active = (active and dev == active)
            text = f"🟢 {dev.description}" if is_active else f"🔴 {dev.description}"
            btn_label = Label(
                label=text,
                h_align="start",
                h_expand=True,
                ellipsization="end",
                max_chars_width=45
            )
            btn = Button(
                child=btn_label,
                on_clicked=self.make_set_default_callback(dev),
                h_align="fill",
                h_expand=True,
            )
            self.devices_box.add(btn)
        self.devices_box.show_all()
    def make_set_default_callback(self, dev):
        def callback(btn):
            if self.is_outputs:
                GLib.spawn_command_line_async(f"pactl set-default-sink {dev.name}")
            else:
                GLib.spawn_command_line_async(f"pactl set-default-source {dev.name}")
        return callback
    def app_routing_button(self, stream, devices):
        # 1. Use GTK's native MenuButton (designed exactly for this)
        btn = Gtk.MenuButton()
        btn.set_halign(Gtk.Align.END)
        btn.set_tooltip_text("Route Audio")
        
        # Add your down-arrow label to the button
        arrow_label = Label(label="⏷")
        btn.add(arrow_label)
        
        # 2. Use a native GTK Dropdown Menu instead of a Popover
        menu = Gtk.Menu()
        menu.set_halign(Gtk.Align.END)
        for dev in devices:
            # 3. Create a native MenuItem (these automatically align left and style beautifully)
            item = Gtk.MenuItem(label=dev.description)
            
            def on_click(menu_item, d=dev, s=stream):
                app_name = getattr(s, "name", getattr(s, "description", "Unknown"))
                real_stream_id = None
                
                try:
                    cmd = ["pactl", "-f", "json", "list", "sink-inputs" if self.is_outputs else "source-outputs"]
                    output = subprocess.check_output(cmd, text=True)
                    streams_json = json.loads(output)
                    
                    for stream_data in streams_json:
                        props = stream_data.get("properties", {})
                        pactl_app_name = props.get("application.name") or props.get("media.name") or ""
                        if app_name.lower() in pactl_app_name.lower() or pactl_app_name.lower() in app_name.lower():
                            real_stream_id = stream_data.get("index")
                            break
                except Exception as e:
                    print(f"Failed to query pactl for stream ID: {e}")

                if real_stream_id is None:
                    print(f"Could not find a pactl stream ID for '{app_name}'.")
                    return

                target_id = None
                try:
                    pactl_cmd = ["pactl", "list", "short", "sinks" if self.is_outputs else "sources"]
                    output = subprocess.check_output(pactl_cmd, text=True)
                    
                    for line in output.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2 and parts[1] == d.name:
                            target_id = parts[0]
                            break
                except Exception as e:
                    print(f"Failed to query pactl for device ID: {e}")

                if target_id is None:
                    print(f"pactl could not find a valid device ID matching '{d.name}'.")
                    return

                try:
                    if self.is_outputs:
                        command = ["pactl", "move-sink-input", str(real_stream_id), str(target_id)]
                    else:
                        command = ["pactl", "move-source-output", str(real_stream_id), str(target_id)]
                    
                    subprocess.run(command, capture_output=True, text=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to route audio: {e.stderr}")
                
                # No popdown() needed; menus auto-close on Wayland/GTK!

            # Note: MenuItems use the "activate" signal, not "clicked"
            item.connect("activate", on_click)
            menu.append(item)

        menu.show_all()
        
        # 4. Bind the menu to the button. GTK natively handles alignment and Wayland surfaces.
        btn.set_popup(menu)
        
        return btn
    
    def update_streams(self, streams):
        # 1. Generate a list of unique names for the current streams
        current_stream_ids = [getattr(s, "name", s.description) for s in streams]
        
        # 2. If the apps/streams haven't changed, skip rebuilding the UI
        if getattr(self, "_active_stream_ids", None) == current_stream_ids:
            self.update_devices() # Ensure active device indicators still update
            return
            
        self._active_stream_ids = current_stream_ids
        for child in self.content_box.get_children():
            self.content_box.remove(child)
        for stream in streams:
            is_app = hasattr(stream, "type") and "application" in stream.type.lower()
            label_text = stream.description
            if hasattr(stream, "type") and "application" in stream.type.lower():
                label_text = getattr(stream, "name", stream.description)

            stream_container = Box(
                orientation="v",
                spacing=4,
                h_expand=True,
                v_expand=False,  # Prevent vertical stretching
            )
            header_box = Box(orientation="h", spacing=4, h_expand=True)
            label = Label(
                name="mixer-stream-label",
                label=f"[{math.ceil(stream.volume)}%] {label_text}",
                h_expand=True,
                h_align="start",
                v_align="center",
                ellipsization="end",
                max_chars_width=45,
                height_request=20,  # Fixed height for labels
            )
            header_box.add(label)
            if is_app:
                devices = self.audio.speakers if self.is_outputs else self.audio.microphones
                routing_btn = self.app_routing_button(stream, devices)
                header_box.add(routing_btn)
            slider = MixerSlider(stream, bind_label=label, label_text=label_text)

            stream_container.add(header_box)
            stream_container.add(slider)
            self.content_box.add(stream_container)

        self.content_box.show_all()
        self.update_devices()


class Mixer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="mixer",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,  # Allow Mixer to expand to parent height
        )

        try:
            self.audio = Audio()
        except Exception as e:
            error_label = Label(
                label=f"Audio service unavailable: {str(e)}",
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True,
            )
            self.add(error_label)
            return

        self.main_container = Box(
            orientation="h" if not vertical_mode else "v",
            spacing=8,
            h_expand=True,
            v_expand=True,  # Allow main_container to expand
        )
        self.main_container.set_homogeneous(True)  # Equal sizing for outputs and inputs

        # ScrolledWindow for Outputs
        self.outputs_scrolled = ScrolledWindow(
            name="outputs-scrolled",
            h_expand=True,
            v_expand=False,  # Prevent vertical expansion
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,  # Vertical scrollbar when needed
            hscrollbar_policy=Gtk.PolicyType.NEVER,      # Disable horizontal scrollbar
        )
        self.outputs_section = MixerSection("Outputs", True, self.audio)
        self.outputs_scrolled.add(self.outputs_section)
        self.outputs_scrolled.set_size_request(-1, 150)  # Fixed height of 150px
        self.outputs_scrolled.set_max_content_height(150)  # Enforce max height
        
        # ScrolledWindow for Inputs
        self.inputs_scrolled = ScrolledWindow(
            name="inputs-scrolled",
            h_expand=True,
            v_expand=False,  # Prevent vertical expansion
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,  # Vertical scrollbar when needed
            hscrollbar_policy=Gtk.PolicyType.NEVER,      # Disable horizontal scrollbar
        )
        self.inputs_section = MixerSection("Inputs", False, self.audio)
        self.inputs_scrolled.add(self.inputs_section)
        self.inputs_scrolled.set_size_request(-1, 150)  # Fixed height of 150px
        self.inputs_scrolled.set_max_content_height(150)  # Enforce max height

        self.main_container.add(self.outputs_scrolled)
        self.main_container.add(self.inputs_scrolled)

        self.add(self.main_container)
        self.set_size_request(-1, 300)  # Optional: Set total height to 300px (150px per section)

        self.audio.connect("changed", self.on_audio_changed)
        self.audio.connect("stream-added", self.on_audio_changed)
        self.audio.connect("stream-removed", self.on_audio_changed)

        self.update_mixer()
        self.show_all()

    def on_audio_changed(self, *args):
        self.update_mixer()

    def update_mixer(self):
        outputs = []
        inputs = []

        if self.audio.speaker:
            outputs.append(self.audio.speaker)
        outputs.extend(self.audio.applications)

        if self.audio.microphone:
            inputs.append(self.audio.microphone)
        inputs.extend(self.audio.recorders)

        self.outputs_section.update_streams(outputs)
        self.inputs_section.update_streams(inputs)
