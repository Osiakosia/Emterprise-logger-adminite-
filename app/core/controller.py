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


def _normalize_port(p: str | None) -> str:
    if not p:
        return ""
    p = str(p).strip()
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
        # enumeration may fail; don't hard-disconnect
        return True
    return False


class Controller:
    """Background serial worker for ccTalk.

    Responsibilities:
      - Owns SerialIO and opens/closes it.
      - Performs reconnect loop.
      - Decodes RX frames and pushes them to STATE.
      - Provides DeviceController for TX (DeviceController uses same SerialIO).

    IMPORTANT:
      - Flask routes must NOT touch the serial port directly.
      - Use request_connect/request_disconnect to control it.
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

        if self.logger:
            self.logger.info(
                "Controller init: port=%s baud=%s timeout=%s host=%s",
                self.port,
                self.baudrate,
                self.timeout,
                self.host_address,
            )

    def start(self):
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._stop.clear()
        self._rx_thread = threading.Thread(target=self._loop, daemon=True)
        self._rx_thread.start()

    def stop(self):
        self._stop.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        self._rx_thread = None
        try:
            self.sio.close()
        except Exception:
            pass
        STATE.set_connected(False, "stopped")

    def request_disconnect(self) -> None:
        with self._cfg_lock:
            self._want_disconnect = True
            self._want_reconnect = False
        try:
            self.sio.close()
        except Exception:
            pass
        STATE.set_connected(False, "manual disconnect")

    def request_connect(self, port: str, baud: int) -> None:
        with self._cfg_lock:
            self.port = str(port)
            self.baudrate = int(baud)
            self._want_disconnect = False
            self._want_reconnect = True
        STATE.set_config(port=self.port, baud=self.baudrate)

    def _rebuild_serial(self):
        # always rebuild SerialIO to drop stale handles
        try:
            self.sio.close()
        except Exception:
            pass
        self.sio = SerialIO(self.port, self.baudrate, self.timeout)
        self.device = DeviceController(self.sio, logger=self.logger, host_address=self.host_address)

    def _loop(self):
        backoff = 1.0
        last_port_check = 0.0

        while not self._stop.is_set():
            with self._cfg_lock:
                want_disc = self._want_disconnect
                want_reconn = self._want_reconnect

            if want_disc:
                # stay idle until connect requested
                time.sleep(0.2)
                continue

            # connect if requested or not open
            if want_reconn or (not self.sio.is_open):
                try:
                    self._rebuild_serial()
                    self.sio.open()
                    self._buf = bytearray()
                    STATE.set_config(port=self.port, baud=self.baudrate)
                    STATE.set_connected(True, None)
                    with self._cfg_lock:
                        self._want_reconnect = False
                    if self.logger:
                        self.logger.info("Serial opened %s @ %s", self.port, self.baudrate)
                    backoff = 1.0
                    last_port_check = time.time()
                except Exception as e:
                    STATE.set_connected(False, str(e))
                    if self.logger:
                        self.logger.warning("Serial open failed (%s). Retrying...", e)
                    time.sleep(backoff)
                    backoff = min(backoff * 1.6, 10.0)
                    continue

            # USB unplug detection on Windows
            now = time.time()
            if (now - last_port_check) >= 1.0:
                last_port_check = now
                if not _port_exists_windows(self.port):
                    STATE.set_connected(False, f"Port removed: {self.port}")
                    if self.logger:
                        self.logger.warning("Port disappeared: %s", self.port)
                    try:
                        self.sio.close()
                    except Exception:
                        pass
                    time.sleep(0.3)
                    continue

            # RX
            try:
                chunk = self.sio.read(1024)
            except (SerialException, OSError) as e:
                STATE.set_connected(False, str(e))
                if self.logger:
                    self.logger.warning("Serial error (%s). Reconnecting...", e)
                try:
                    self.sio.close()
                except Exception:
                    pass
                time.sleep(backoff)
                backoff = min(backoff * 1.6, 10.0)
                continue

            if chunk:
                self._buf.extend(chunk)
                frames, self._buf = try_parse_frames(self._buf)

                for fr in frames:
                    dec = decode_frame(fr)
                    rec = FrameRecord(
                        ts=time.time(),
                        direction="RX",
                        addr=int(dec.src),
                        raw_hex=fr.hex(),
                        decoded={**dec.to_dict(), "header_name": header_name(dec.header)},
                    )
                    STATE.add_frame(rec)
                    if self.logger:
                        self.logger.info("RX %s", fr.hex())

            time.sleep(0.01)

        try:
            self.sio.close()
        except Exception:
            pass
