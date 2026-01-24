from logitech_receiver import base, receiver, device
from logitech_receiver.listener import EventsListener
from logitech_receiver.base import HIDPPNotification
import time
import logging
import piper
logger = logging.getLogger(__name__)
logger.info('Started')

my_device = None

def status_change_callback(event : HIDPPNotification):
    print(event.data)

def _receivers_and_devices(dev_path=None):
    for dev_info in base.receivers_and_devices():
        try:
            if dev_info.isDevice:
                d = device.create_device(base, dev_info)
            else:
                d = receiver.create_receiver(base, dev_info)

            if d is not None:
                yield d
        except Exception as e:
            print("error opening", dev_info, e)

# Create and start listener

# Enumerate and attach
for dev in _receivers_and_devices():
    print("Found:", dev.name)

    if dev.kind == "receiver":
        dev.add_listener(listener)

    if dev.name == "G535 Gaming Headset":
        my_device = dev

listener = EventsListener(my_device,status_change_callback)
listener.run()
