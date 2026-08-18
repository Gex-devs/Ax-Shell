import modules.icons as icons
import config.data as data
import libvirt
from loguru import logger
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.utils import exec_shell_command_async
from gi.repository import Gdk, GLib, Gtk
from scripts.virt import VmMonitorService


libvirt.virEventRegisterDefaultImpl()

class WindowsVm(EventBox):
    def __init__(self, **kwargs) -> None:
        conn = libvirt.open('qemu:///system')
        try:
            available_vms = [domain.name() for domain in conn.listAllDomains(0)]
        finally:
            conn.close()
        super().__init__(name="vm-indicator", **kwargs)
        
        # Default to first available VM or empty string
        self.vm_name = available_vms[0] if available_vms else "win11"
        print(f"[Available vm's] {available_vms}")

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
        self.icon_btn.connect("button-press-event", lambda widget, event: self._toggle_menu(event))
        self.vm_service = VmMonitorService(self.vm_name)
        self.vm_service.connect("vm-started", self.on_vm_started)
        self.vm_service.connect("vm-stopped", self.on_vm_stopped)

        self.vm_radio_buttons = []
        first_radio = None
        for vm in available_vms:
            radio = Gtk.RadioButton.new_with_label_from_widget(first_radio, vm)
            radio.set_mode(False)
            radio.get_style_context().add_class("vm-radio-item")
            radio.connect("toggled", self._on_vm_radio_toggled, vm)
            if first_radio is None:
                first_radio = radio
                radio.set_active(True)
            self.vm_radio_buttons.append(radio)

        self.menu_box_left = Box(
            name="vm-name-menu",
            orientation="h",
            children=self.vm_radio_buttons
        )
        
        self.menu_box_right = Box(
            name="vm-command-menu",
            orientation="h",
            children=[
                Button(name="vm-menu-item", child=Label(markup=f"{icons.play}"), on_clicked=self._on_start_clicked),
                Button(name="vm-menu-item", child=Label(markup=f"{icons.reboot}"), on_clicked=self._on_force_reboot_clicked),
                Button(name="vm-menu-item", child=Label(markup=f"{icons.stop}"), on_clicked=self._on_stop_clicked),
                Button(name="vm-menu-item", child=Label(markup=f"{icons.trash}"), on_clicked=self._on_force_stop_clicked),
            ],
        )
        
        self.details_revealer_right = Revealer(
            name="vmstatus-revealer",
            transition_type="slide-right",
            transition_duration=250,
            child=self.menu_box_right,
            reveal_child=False,
        )
        
        self.details_revealer_left = Revealer(
            name="vmname-revealer",
            transition_type="slide-left",
            transition_duration=250,
            child=self.menu_box_left,
            reveal_child=False,
        )

        self.inner_box = Box(
            name="vm-box",
            orientation="h" if not data.VERTICAL else "v",
            children=[self.details_revealer_left, self.icon_btn, self.details_revealer_right],
        )
        self.add(self.inner_box)
        
        self.show_all()

        GLib.idle_add(self.vm_service.start)
        
        self.update_icon_status()

    def update_icon_status(self):
        """Query libvirt for current active status of self.vm_name and set icon."""
        if self.vm_service.is_vm_running(self.vm_name):
            self.icon.set_markup(icons.windows_on)
        else:
            self.icon.set_markup(icons.windows_off)

    def _on_vm_radio_toggled(self, radio, vm_name):
        if radio.get_active():
            self._assign_vm(vm_name)

    def _assign_vm(self, vm_name):
        logger.info(f"[WindowsVm] switching active VM to {vm_name}")
        self.vm_name = vm_name
        self.update_icon_status()

    def _toggle_menu(self,event):
        """Toggles the revealers open or closed when the widget is clicked."""
        if event.type == Gdk.EventType._2BUTTON_PRESS: 
            if event.button == 1:
                exec_shell_command_async("kitty")
                return True
         
        elif event.button == 3:
                current_state = self.details_revealer_right.get_reveal_child()
                new_state = not current_state
                
                self.details_revealer_right.set_reveal_child(new_state)
                self.details_revealer_left.set_reveal_child(new_state)
                logger.info(f"[WindowsVm] Menu clicked, state is now: {'revealed' if new_state else 'hidden'}")
                return True
        return False

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