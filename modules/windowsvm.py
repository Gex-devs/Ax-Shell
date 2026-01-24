from fabric.widgets.button import Button
from gi.repository import Gdk
from fabric.widgets.label import Label
import modules.icons as icons
from scripts.virt import VmMonitorService
import config.data as data
from fabric.widgets.box import Box
from gi.repository import Gdk, GLib, Gtk

class WindowsVm(Button):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="button-bar", **kwargs)
        self.icon = Label(name="vmstatus-icon-label", markup=icons.windows_off, v_align="center", h_align="center", h_expand=True, v_expand=True)       
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.mouse_click_event)

        vm_service = VmMonitorService("win11")

        vm_service.connect("vm-started", self.on_vm_started)
        vm_service.connect("vm-stopped", self.on_vm_stopped)

        self.children =  [Box(
            orientation="h" if not data.VERTICAL else "v",
            children=[self.icon],
        )]

        vm_service.start()


    def mouse_click_event(self, widget, event):
        
        menu = Gtk.Menu()
        menu_item = Gtk.MenuItem(label="Menu Item")
        menu_item.connect("activate", self.menu_item_activated)
        menu.append(menu_item)
        menu.show_all()

        menu.popup_at_widget(widget, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, event)
        print(f"Clicked ")
        self.emit("clicked")
        return True

    def menu_item_activated(self, widget):
        print("Menu Item Activated")
    
    def on_vm_started(service, vm_name):
        print(f"VM {vm_name} started!")

    def on_vm_stopped(service, vm_name):
        print(f"VM {vm_name} stopped!")