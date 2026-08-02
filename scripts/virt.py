import libvirt
from gi.repository import GLib, GObject
import threading

class VmMonitorService(GObject.GObject):
    __gsignals__ = {
        "vm-started": (GObject.SIGNAL_RUN_LAST, None, (str,)),
        "vm-stopped": (GObject.SIGNAL_RUN_LAST, None, (str,))
    }

    def __init__(self, vm_name: str):
        super().__init__()
        self.vm_name = vm_name
        self.conn = libvirt.open("qemu:///system")
        if self.conn is None:
            raise RuntimeError("Failed to connect to libvirt")

    def _lifecycle_callback(self, conn, dom, event, detail, opaque):
        if dom.name() != self.vm_name:
            return
        if event == libvirt.VIR_DOMAIN_EVENT_STARTED:
            GLib.idle_add(self.emit, "vm-started", self.vm_name)
        elif event == libvirt.VIR_DOMAIN_EVENT_STOPPED or event == libvirt.VIR_DOMAIN_EVENT_SHUTDOWN:
            GLib.idle_add(self.emit, "vm-stopped", self.vm_name)

    def start(self):
        """Start monitoring in a background thread."""
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        print("Started vm monitoring service")
        self.conn.domainEventRegisterAny(
            None,
            libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
            self._lifecycle_callback,
            None
        )
        while True:
            libvirt.virEventRunDefaultImpl()
