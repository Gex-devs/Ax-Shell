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
    def __init__(self, stream, **kwargs):
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

    def on_value_changed(self, _):
        if self._updating_from_stream:
            return
        if self.stream:
            self.stream.volume = self.value * 100
            self.set_tooltip_text(f"{self.value * 100:.0f}%")

    def on_stream_changed(self, stream):
        self._updating_from_stream = True
        self.value = stream.volume / 100
        self.set_tooltip_text(f"{stream.volume:.0f}%")
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
        btn = Button(label="⏷", h_align="end", tooltip_text="Route Audio")
        popover = Gtk.Popover()
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"popover contents {background-color: black; background-image:none;}")
        popover.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        vbox = Box(orientation="v", spacing=4)
        for dev in devices:
            item_btn = Button(
                label=dev.description,
                ellipsization="end",
                max_chars_width=30,
                h_expand=True,
            )
            def on_click(b, d=dev, s=stream):
                print("\n" + "="*50)
                print("1. ROUTING REQUEST INITIATED")
                
                # Use Fabric's stream name (e.g., "Spotify") to search pactl
                app_name = getattr(s, "name", getattr(s, "description", "Unknown"))
                print(f"   -> Looking for App Name: {app_name}")
                print(f"   -> Target Device Name: {d.name}")
                print("-" * 50)

                # 1. Query pactl for the REAL Stream ID (Sink-Input Index)
                print("2. QUERYING PACTL FOR EXACT STREAM ID")
                real_stream_id = None
                try:
                    # Ask pactl for a clean JSON list of all active streams
                    cmd = ["pactl", "-f", "json", "list", "sink-inputs" if self.is_outputs else "source-outputs"]
                    print(f"   -> Executing: {' '.join(cmd)}")
                    
                    output = subprocess.check_output(cmd, text=True)
                    streams_json = json.loads(output)
                    
                    for stream_data in streams_json:
                        # pactl hides the app name in the properties dictionary
                        props = stream_data.get("properties", {})
                        pactl_app_name = props.get("application.name") or props.get("media.name") or ""
                        
                        print(f"      - Checking pactl stream: ID {stream_data.get('index')} | App: '{pactl_app_name}'")
                        
                        # Match the names
                        if app_name.lower() in pactl_app_name.lower() or pactl_app_name.lower() in app_name.lower():
                            real_stream_id = stream_data.get("index")
                            print(f"   -> [SUCCESS] Matched Fabric app name to pactl stream ID: {real_stream_id}")
                            break
                except Exception as e:
                    print(f"   -> [ERROR] Failed to query pactl for stream ID: {e}")

                if real_stream_id is None:
                    print(f"   -> [ERROR] Could not find a pactl stream ID for '{app_name}'. Aborting.")
                    print("="*50 + "\n")
                    popover.popdown()
                    return

                # 2. Query pactl for the REAL Target Device ID
                print("-" * 50)
                print("3. QUERYING PACTL FOR EXACT TARGET DEVICE ID")
                target_id = None
                try:
                    pactl_cmd = ["pactl", "list", "short", "sinks" if self.is_outputs else "sources"]
                    output = subprocess.check_output(pactl_cmd, text=True)
                    
                    for line in output.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2 and parts[1] == d.name:
                            target_id = parts[0]
                            print(f"   -> [SUCCESS] Matched Fabric device name to pactl ID: {target_id}")
                            break
                except Exception as e:
                    print(f"   -> [ERROR] Failed to query pactl for device ID: {e}")

                if target_id is None:
                    print(f"   -> [ERROR] pactl could not find a valid device ID matching '{d.name}'. Aborting.")
                    print("="*50 + "\n")
                    popover.popdown()
                    return

                # 3. Route the audio using ONLY verified numeric IDs from pactl
                print("-" * 50)
                print("4. EXECUTING AUDIO ROUTE COMMAND")
                try:
                    if self.is_outputs:
                        command = ["pactl", "move-sink-input", str(real_stream_id), str(target_id)]
                    else:
                        command = ["pactl", "move-source-output", str(real_stream_id), str(target_id)]
                    
                    print(f"   -> Running command: {' '.join(command)}")
                    subprocess.run(command, capture_output=True, text=True, check=True)
                    print("   -> [SUCCESS] Routing command executed without errors! Audio moved.")
                except subprocess.CalledProcessError as e:
                    print(f"   -> [ERROR] Failed to route audio.")
                    print(f"   -> pactl stderr: {e.stderr}")
                
                print("="*50 + "\n")
                popover.popdown()   
            item_btn.connect("clicked", on_click)
            vbox.add(item_btn)
        popover.add(vbox)
        popover.set_relative_to(btn)
        vbox.show_all()
        btn.connect("clicked", lambda b: popover.popup())
        return btn
    
    def update_streams(self, streams):
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
                label=f"[{math.ceil(stream.volume)}%] {stream.description}",
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
            slider = MixerSlider(stream)

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
