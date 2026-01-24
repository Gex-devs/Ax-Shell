from logitech_receiver import base, receiver, device
from logitech_receiver.listener import EventsListener
from logitech_receiver.base import HIDPPNotification
from fabric.core.service import Service, Signal
from fabric.utils import exec_shell_command_async

""" 
Service for handling Logitech devices

"""
class Logitech(Service):

    listener : EventsListener = None
    headsetDevice = None
    instance = None

    # TODO: Set relevant bytes
    TOGGLE_ON_BYTE = b'\x0f\xd7\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    TOGGLE_OFF_BYTE = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'


    @staticmethod
    def get_initial():
        """Singleton to get Logitech service instance."""
        if Logitech.instance is None:
            Logitech.instance = Logitech()
        return Logitech.instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupDevice()

    @Signal
    def headset_statechange(self, state:int) -> None:
        print(state)
        self.toggle_headset(state)


    def statusChange(self, hidNotification: HIDPPNotification):
        if hidNotification.data == self.TOGGLE_OFF_BYTE:
            self.headset_statechange(0)
        else:
            self.headset_statechange(1)

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

    def setupDevice(self):
        for dev in self._receivers_and_devices():
            print("Found:", dev.name)
            if dev.kind == "receiver":
                dev.add_listener(self.listener)

            if dev.name == "G535 Gaming Headset":
               self.headsetDevice = dev

        self.listener = EventsListener(self.headsetDevice, self.statusChange)
        self.listener.start()

    def toggle_headset(self, state):
        if state == 1:
            exec_shell_command_async("notify-send 'Logitech Headset Connected' 'Connected!'")
            exec_shell_command_async("pactl set-default-sink alsa_output.usb-Logitech_G535_Wireless_Gaming_Headset-00.analog-stereo")
            pass
        elif state == 0:
            exec_shell_command_async("notify-send 'Logitech Headset Disconnected' 'Disconnected!'")
            exec_shell_command_async("pactl set-default-sink alsa_output.usb-ASUSTeK_Xonar_SoundCard-00.analog-stereo")
            pass
        pass