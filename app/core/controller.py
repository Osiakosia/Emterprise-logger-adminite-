from __future__ import annotations

import threading
import time
from typing import Optional

import serial.tools.list_ports
from serial.serialutil import SerialException

from .serial_io import SerialIO
from .cctalk import try_parse_frames, decode_frame, header_name
from .state import STATE, FrameRecord
from .device_controller import DeviceController

import os
print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Controller __init__ PID={os.getpid()}", flush=True)
...
print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG][WORKER] sio.open() CALLED in controller.py:_loop", flush=True)
def start(self) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Controller.start() on PID={os.getpid()}", flush=True)
    ...


def _normalize_port(p: str | None) -> str:
    if not p:
        return ""
    p = str(p).strip()
    # "\\.\COM10" -> "COM10"
    if p.lower().startswith("\\\\.\\"):
        p = p[4:]
    return p.upper()


def _port_exists_windows(port_name: str | None) -> bool:
    want = _normalize_port(port_name)
    if not want:
        return False
    try:
        for info in serial.tools.list_ports.comports():
            if _normalize_port(getattr(info, "device", None)) == want:
                return True
    except Exception:
        # Enumeration can fail; treat as "unknown" => don't force disconnect
        return True
    return False


class Controller:
    """
    Background serial worker for ccTalk.
      - Owns SerialIO and DeviceController
      - Reconnect loop
      - RX decode -> STATE.frames
      - Updates STATE.connected + richer serial status for multi-level badge
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 0.1,
        host_address: int = 1,
        logger=None,
    ):
        self.logger = logger

        # Assign BEFORE logging
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.host_address = int(host_address)

        self.sio = SerialIO(self.port, self.baudrate, self.timeout)
        self.device = DeviceController(self.sio, logger=self.logger, host_address=self.host_address)

        self._stop = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._buf = bytearray()

        self._cfg_lock = threading.Lock()
        self._want_disconnect = False
        self._want_reconnect = True  # start tries to connect

        self._thread_running = False
        self._last_port_present = None  # type: Optional[bool]

        if self.logger:
            self.logger.info(
                "Controller init: port=%s baud=%s timeout=%s host=%s",
                self.port, self.baudrate, self.timeout, self.host_address
            )

        # publish initial status
        self._publish_serial_status(
            connected=False,
            serial_open=False,
            port_present=_port_exists_windows(self.port),
            last_error="starting",
        )

    # -------------------- public API --------------------

    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._stop.clear()
        self._rx_thread = threading.Thread(target=self._loop, daemon=True)
        self._rx_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        self._rx_thread = None
        self._thread_running = False
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.close() CALLED in controller.py:stop", flush=True)
            self.sio.close()
        except Exception:
            pass

        self._publish_serial_status(
            connected=False,
            serial_open=False,
            port_present=_port_exists_windows(self.port),
            last_error="stopped",
        )

    def request_disconnect(self) -> None:
        with self._cfg_lock:
            self._want_disconnect = True
            self._want_reconnect = False

        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.close() CALLED in controller.py:request_disconnect", flush=True)
            self.sio.close()
        except Exception:
            pass

        self._publish_serial_status(
            connected=False,
            serial_open=False,
            port_present=_port_exists_windows(self.port),
            last_error="manual disconnect",
        )

    def request_connect(self, port: str, baud: int) -> None:
        with self._cfg_lock:
            self.port = str(port)
            self.baudrate = int(baud)
            self._want_disconnect = False
            self._want_reconnect = True

        # keep STATE config in sync
        try:
            STATE.set_config(port=self.port, baud=self.baudrate)
        except Exception:
            pass

        self._publish_serial_status(
            connected=False,
            serial_open=False,
            port_present=_port_exists_windows(self.port),
            last_error="connecting",
        )

    # -------------------- internal helpers --------------------

    def _rebuild_serial(self) -> None:
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.close() CALLED in controller.py:_rebuild_serial", flush=True)
            self.sio.close()
        except Exception:
            pass
        self.sio = SerialIO(self.port, self.baudrate, self.timeout)
        self.device = DeviceController(self.sio, logger=self.logger, host_address=self.host_address)

    def _publish_serial_status(
        self,
        *,
        connected: bool,
        serial_open: bool,
        port_present: bool,
        last_error: str | None,
    ) -> None:
        """
        Multi-level badge status publisher.

        Works with both:
          - old STATE that only has set_connected()
          - new STATE that also has set_serial_status(dict)
        """

        # classic fields (existing)
        try:
            STATE.set_connected(bool(connected), last_error)
        except Exception:
            pass

        # richer status map (new)
        payload = {
            "connected": bool(connected),
            "serial_open": bool(serial_open),
            "port_present": bool(port_present),
            "thread_running": bool(self._thread_running),
            "port": self.port,
            "baud": int(self.baudrate),
            "last_error": last_error,
            "ts": time.time(),
        }

        # If your state.py implements it, great:
        if hasattr(STATE, "set_serial_status"):
            try:
                STATE.set_serial_status(payload)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _loop(self) -> None:
        self._thread_running = True
        backoff = 1.0
        last_port_check = 0.0

        while not self._stop.is_set():
            with self._cfg_lock:
                want_disc = self._want_disconnect
                want_reconn = self._want_reconnect

            # manual disconnect mode
            if want_disc:
                self._publish_serial_status(
                    connected=False,
                    serial_open=False,
                    port_present=_port_exists_windows(self.port),
                    last_error="manual disconnect",
                )
                time.sleep(0.2)
                continue

            # periodic port presence check (Windows USB unplug)
            now = time.time()
            if (now - last_port_check) >= 1.0:
                last_port_check = now
                present = _port_exists_windows(self.port)
                self._last_port_present = present

                if not present:
                    try:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.close() CALLED in controller.py:_loop (port missing)", flush=True)
                        self.sio.close()
                    except Exception:
                        pass
                    self._publish_serial_status(
                        connected=False,
                        serial_open=False,
                        port_present=False,
                        last_error=f"port missing: {self.port}",
                    )
                    time.sleep(0.5)
                    continue

            # open/reconnect if needed – SU SAUGIU TIKRINIMU
            if want_reconn or (not self.sio.is_open):
                try:
                    self._rebuild_serial()
                    # Patikra: jei po rebuild vis dar neatidarytas portas, tik tada open()!
                    if not self.sio.is_open:
                        print(
                            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.open() CALLED in controller.py:_loop",
                            flush=True)
                        self.sio.open()
                        print(
                            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.open() SUCCESS in controller.py:_loop",
                            flush=True)
                        # >>> RECONNECT flag reset tik jei open() pavyko! <<<
                        with self._cfg_lock:
                            self._want_reconnect = False
                    else:
                        print(
                            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.open() SKIPPED (already open) in controller.py:_loop",
                            flush=True)
                        # Jei portas jau atidarytas, irgi galim saugiai numušti vėliavą:
                        with self._cfg_lock:
                            self._want_reconnect = False

                    self._buf = bytearray()

                    try:
                        STATE.set_config(port=self.port, baud=self.baudrate)
                    except Exception:
                        pass

                    self._publish_serial_status(
                        connected=True,
                        serial_open=True,
                        port_present=True if self._last_port_present is None else bool(self._last_port_present),
                        last_error=None,
                    )

                    if self.logger:
                        self.logger.info("Serial opened %s @ %s", self.port, self.baudrate)

                    backoff = 1.0
                    continue

                except Exception as e:
                    print(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.open() ERROR in controller.py:_loop: {e}",
                        flush=True)
                    if self.logger:
                        self.logger.warning("Serial open failed (%s). Retrying...", e)

                    self._publish_serial_status(
                        connected=False,
                        serial_open=False,
                        port_present=_port_exists_windows(self.port),
                        last_error=str(e),
                    )

                    time.sleep(backoff)
                    backoff = min(backoff * 1.6, 10.0)
                    continue

                    if self.logger:
                        self.logger.info("Serial opened %s @ %s", self.port, self.baudrate)

                    backoff = 1.0
                    continue

                except Exception as e:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.open() ERROR in controller.py:_loop: {e}", flush=True)
                    if self.logger:
                        self.logger.warning("Serial open failed (%s). Retrying...", e)

                    self._publish_serial_status(
                        connected=False,
                        serial_open=False,
                        port_present=_port_exists_windows(self.port),
                        last_error=str(e),
                    )

                    time.sleep(backoff)
                    backoff = min(backoff * 1.6, 10.0)
                    continue

            # read loop
            try:
                chunk = self.sio.read(1024)
            except (SerialException, OSError) as e:
                if self.logger:
                    self.logger.warning("Serial error (%s). Reconnecting...", e)
                try:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.close() CALLED in controller.py:_loop (read error)", flush=True)
                    self.sio.close()
                except Exception:
                    pass

                self._publish_serial_status(
                    connected=False,
                    serial_open=False,
                    port_present=_port_exists_windows(self.port),
                    last_error=str(e),
                )

                time.sleep(backoff)
                backoff = min(backoff * 1.6, 10.0)
                continue

            if chunk:
                self._buf.extend(chunk)
                frames, self._buf = try_parse_frames(self._buf)

                for fr in frames:
                    dec = decode_frame(fr)
                    try:
                        if int(dec.src) == int(self.host_address) and int(dec.dest) != int(self.host_address):
                            if self.logger:
                                self.logger.warning("RX echo detected (ignoring): %s", fr.hex())
                            continue
                    except Exception:
                        pass

                    rec = FrameRecord(
                        ts=time.time(),
                        direction="RX",
                        addr=int(dec.src),
                        raw_hex=fr.hex(),
                        decoded={**dec.to_dict(), "header_name": header_name(dec.header)},
                    )
                    try:
                        STATE.add_frame(rec)
                        if int(dec.src) != int(self.host_address):
                            STATE.note_device(int(dec.src))
                    except Exception:
                        pass

                    if self.logger:
                        self.logger.info("RX %s", fr.hex())

            time.sleep(0.01)

        # loop shutdown
        self._thread_running = False
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] sio.close() CALLED in controller.py:_loop (shutdown)", flush=True)
            self.sio.close()
        except Exception:
            pass

        self._publish_serial_status(
            connected=False,
            serial_open=False,
            port_present=_port_exists_windows(self.port),
            last_error="stopped",
        )