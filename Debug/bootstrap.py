import os
from app.core.controller import Controller
from app.core.state import STATE

print(f"BOOTSTRAP: PID={os.getpid()} PPID={os.getppid()}", flush=True)
print("BOOTSTRAP: Starting controller", flush=True)

from app.drivers.transport import ControllerTransport

# ---------- 1. Sukuriamas vienas Controller (serial workeris) ----------
controller = Controller(
    port="COM4",
    baudrate=9600,
    timeout=0.1,
    host_address=1,
    logger=None
)

# ---------- 1a. Daugiau JOKIO open() čia! Viską tvarko controller.start/_loop ----------
controller.start()

# ---------- 2. Sukuriami ControllerTransport adapteriai kiekvienam draiveriui ----------
acceptor_transport = ControllerTransport(
    controller=controller,
    state=STATE,
    host_address=controller.host_address,
)

hopper_transport = ControllerTransport(
    controller=controller,
    state=STATE,
    host_address=controller.host_address,
)

recycler_transport = ControllerTransport(
    controller=controller,
    state=STATE,
    host_address=controller.host_address,
)

# ... Šituos adapterius naudoji draiveriams (acceptor, hopper, t.t.) ...