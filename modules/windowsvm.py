import modules.icons as icons
import config.data as data
import libvirt
from loguru import logger
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.utils import exec_shell_command_async
from gi.repository import Gdk, GLib, Gtk
from scripts.virt import VmMonitorService

libvirt.virEventRegisterDefaultImpl()

# Hardcoded VM name — change this to match your VM in `virsh list --all`
VM_NAME = "vm1"


class WindowsVm(EventBox):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="vm-indicator", **kwargs)
        self.vm_name = VM_NAME

        self.icon = Label(
            name="vmstatus-icon-label",
            markup=icons.windows_off,
            v_align="center", h_align="center",
            h_expand=True, v_expand=True,
        )

        self.icon_btn = Button(
            name="vmstatus-icon-btn",
            child=self.icon,
        )
        self.icon_btn.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.icon_btn.connect("button-press-event", self._on_button_press)
        self.add(self.icon_btn)

        self.vm_service = VmMonitorService(self.vm_name)
        self.vm_service.connect("vm-started", self.on_vm_started)
        self.vm_service.connect("vm-stopped", self.on_vm_stopped)

        self.show_all()

        GLib.idle_add(self.vm_service.start)

        self.update_icon_status()

    def update_icon_status(self):
        """Query libvirt for current active status of self.vm_name and set icon."""
        if self.vm_service.is_vm_running(self.vm_name):
            self.icon.set_markup(icons.windows_on)
        else:
            self.icon.set_markup(icons.windows_off)

    def _on_button_press(self, widget, event):
        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            # Placeholder for future double-click action
            exec_shell_command_async("kitty")
            return True
        elif event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            self._show_context_menu(widget, event)
            return True
        return False

    def _show_context_menu(self, widget, event):
        menu = Gtk.Menu()

        start_item = Gtk.MenuItem(label="Start VM")
        start_item.connect("activate", self._on_start_clicked)
        menu.append(start_item)

        stop_item = Gtk.MenuItem(label="Stop VM")
        stop_item.connect("activate", self._on_stop_clicked)
        menu.append(stop_item)

        reboot_item = Gtk.MenuItem(label="Reboot VM")
        reboot_item.connect("activate", self._on_force_reboot_clicked)
        menu.append(reboot_item)

        force_stop_item = Gtk.MenuItem(label="Force Stop VM")
        force_stop_item.connect("activate", self._on_force_stop_clicked)
        menu.append(force_stop_item)

        menu.show_all()
        menu.popup_at_widget(widget, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, event)

    def _on_start_clicked(self, _):
        cmd = f"virsh -c qemu:///system start {self.vm_name}"
        logger.info(f"[WindowsVm] Start VM clicked, running: {cmd}")
        exec_shell_command_async(cmd, lambda output: logger.info(f"[WindowsVm] start output: {output!r}"))

    def _on_stop_clicked(self, _):
        cmd = f"virsh -c qemu:///system shutdown {self.vm_name}"
        logger.info(f"[WindowsVm] Stop VM clicked, running: {cmd}")
        exec_shell_command_async(cmd, lambda output: logger.info(f"[WindowsVm] stop output: {output!r}"))

    def _on_force_stop_clicked(self, _):
        cmd = f"virsh -c qemu:///system destroy {self.vm_name}"
        logger.info(f"[WindowsVm] Force stop VM clicked, running: {cmd}")
        exec_shell_command_async(cmd, lambda output: logger.info(f"[WindowsVm] force stop output: {output!r}"))

    def _on_force_reboot_clicked(self, _):
        cmd = f"virsh -c qemu:///system reboot {self.vm_name}"
        logger.info(f"[WindowsVm] Force reboot VM clicked, running: {cmd}")
        exec_shell_command_async(cmd, lambda output: logger.info(f"[WindowsVm] reboot output: {output!r}"))

    def on_vm_started(self, service, vm_name):
        logger.info(f"[WindowsVm] vm-started signal received for {vm_name}")
        if vm_name == self.vm_name:
            self.icon.set_markup(icons.windows_on)

    def on_vm_stopped(self, service, vm_name):
        logger.info(f"[WindowsVm] vm-stopped signal received for {vm_name}")
        if vm_name == self.vm_name:
            self.icon.set_markup(icons.windows_off)