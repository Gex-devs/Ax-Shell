from fabric.widgets.button import Button
from gi.repository import Gdk
from fabric.widgets.label import Label
import modules.icons as icons

import config.data as data
from fabric.widgets.box import Box

class WindowsVm(Button):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="button-bar", **kwargs)
        self.icon = Label(name="download-icon-label", markup=icons.bat_full, v_align="center", h_align="center", h_expand=True, v_expand=True)       
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.mouse_click_event)


        self.children = Box(
            orientation="h" if not data.VERTICAL else "v",
            children=[self.icon],
        )


    def mouse_click_event(self, widget, event):
        print("Left Click")
        self.emit("clicked")