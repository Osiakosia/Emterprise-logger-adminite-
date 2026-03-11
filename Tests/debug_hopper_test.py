from app.core.state import STATE
from app.core.controller import Controller
from app.drivers.transport import ControllerTransport
from app.drivers.devices.hopper import autodetect_hopper

controller = Controller(port=STATE.port, baudrate=STATE.baud, timeout=0.1, host_address=1, logger=None)
controller.start()

t = ControllerTransport(controller=controller, state=STATE, host_address=1)
dev, info = autodetect_hopper(t, [5], quiet=True)
print(info)

res = dev.payout(1, reset_before_payout=True)
print(res)