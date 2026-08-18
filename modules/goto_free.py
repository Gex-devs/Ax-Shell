import json
from fabric.widgets.button import Button
from fabric.utils import exec_shell_command_async
from fabric.hyprland.widgets import Workspaces
from fabric.hyprland.service import Hyprland
from fabric.widgets.label import Label
import modules.icons as icons

class GotoFree(Button):
    def __init__(self, **kwargs):
        self.connection = Hyprland()
        self.icon = Label(
            name = "goto-icon",
            markup=icons.skip_forward,
            v_align="center",
            h_align="center",
            h_expand=True,
            v_expand=True,
        )
        super().__init__(
            name="goto-btn",
            child=self.icon,
            on_clicked=self.on_button_click,
            **kwargs
        )
    def get_free_id(self) -> int:
        reply = self.connection.send_command("j/workspaces").reply
        self.workspaces = json.loads(reply.decode("utf-8"))
        active_ids = [w["id"] for w in self.workspaces]
        return next(i for i in range(1,100) if i not in active_ids)
    def on_button_click(self):
        free_id = self.get_free_id()
        exec_shell_command_async(f'hyprctl dispatch "hl.dsp.focus({{workspace = {free_id}}})"')
        
        