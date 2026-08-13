import modules.icons as icons
import config.data as data
import libvirt
from loguru import logger
from sys import stdout
from fabric.widgets.button import Button
from gi.repository import Gdk
from fabric.widgets.label import Label
from scripts.virt import VmMonitorService
from fabric.widgets.box import Box
from gi.repository import Gdk, GLib, Gtk
from fabric.utils import exec_shell_command_async

libvirt.virEventRegisterDefaultImpl()

class WindowsVm(Button):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="vm-indicator", **kwargs)
        self.icon = Label(name="vmstatus-icon-label", markup=icons.windows_off, v_align="center", h_align="center", h_expand=True, v_expand=True)       
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.mouse_click_event)
        self.vm_name = "vm1"
        self.vm_service = VmMonitorService(self.vm_name)
        self.vm_service.connect("vm-started", self.on_vm_started)
        self.vm_service.connect("vm-stopped", self.on_vm_stopped)

        self.add(Box(
            orientation="h" if not data.VERTICAL else "v",
            children=[self.icon],
        ))

        GLib.idle_add(self.vm_service.start)


    def mouse_click_event(self, widget, event):
        logger.info(f"[WindowsVm] mouse_click_event fired, button={event.button}")
        if event.button == 3:
            menu = Gtk.Menu()
            
            start_item = Gtk.MenuItem(label="Start VM")
            start_item.connect("activate", self._on_start_clicked)
            menu.append(start_item)
            stop_item = Gtk.MenuItem(label="Stop VM")
            stop_item.connect("activate", self._on_stop_clicked)
            menu.append(stop_item)
            
            menu.show_all()
            menu.popup_at_widget(widget, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, event)
            return True
        return False

    def start_session(self, widget):
       print("Starting Windows VM...")

    def _on_start_clicked(self, _):
        cmd = f"virsh -c qemu:///system start {self.vm_name}"
        logger.info(f"[WindowsVm] Start VM clicked, running:{cmd}")
        exec_shell_command_async(cmd, lambda output: logger.info(f"[WindowsVm] start output: {output!r}"))

    def _on_stop_clicked(self, _):
        cmd = f"virsh -c qemu:///system shutdown {self.vm_name}"
        logger.info(f"[WindowsVm] Start VM clicked, running:{cmd}")
        exec_shell_command_async(cmd, lambda output: logger.info(f"[WindowsVm] start output: {output!r}"))
        
    def on_vm_started(self, service, vm_name):
        logger.info(f"[WindowsVm] vm-started signal received for {vm_name}")
        self.icon.set_markup(f'<span foreground="#50fa7b">{icons.windows_off}</span>')
        
    def on_vm_stopped(self, service, vm_name):
        logger.info(f"[WindowsVm] vm-stopped signal received for {vm_name}")
        self.icon.set_markup(icons.windows_off)