import sys
import libvirt
from gi.repository import GLib, GObject
import threading

from loguru import logger

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
        logger.info(f"[VmMonitorService] lifecycle event: dom={dom.name()} event={event} detail={detail}")
        if dom.name() != self.vm_name:
            return
        if event == libvirt.VIR_DOMAIN_EVENT_STARTED:
            logger.info(f"[VmMonitorService] emitting vm-started for {self.vm_name}")
            GLib.idle_add(self.emit, "vm-started", self.vm_name)
        elif event == libvirt.VIR_DOMAIN_EVENT_STOPPED or event == libvirt.VIR_DOMAIN_EVENT_SHUTDOWN:
            logger.info(f"[VmMonitorService] emitting vm-stopped for {self.vm_name}")
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
if __name__ == "__main__":
    # Required before opening libvirt connection for events
    libvirt.virEventRegisterDefaultImpl()

    # vm_name = sys.argv[1] if len(sys.argv) > 1 else "win11"
    vm_name = "workstation"
    print(f"Monitoring VM: '{vm_name}'... (Press Ctrl+C to stop)")

    service = VmMonitorService(vm_name)
    service.connect("vm-started", lambda _, name: print(f"🟢 SIGNAL: {name} turned ON"))
    service.connect("vm-stopped", lambda _, name: print(f"🔴 SIGNAL: {name} turned OFF"))
    
    service.start()

    # Run GLib loop to process signals
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nExiting...")
