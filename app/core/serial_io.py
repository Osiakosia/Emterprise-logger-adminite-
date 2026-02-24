# app/core/serial_io.py
from __future__ import annotations

import threading
from typing import Optional

import serial
from serial.serialutil import SerialException


class SerialIO:
    """
    Serial wrapper for ccTalk.

    Does NOT open automatically; call open().
    Thread-safe read/write.
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.1, **_ignored):
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)

        self._lock = threading.Lock()
        self._ser: Optional[serial.Serial] = None

    @property
    def is_open(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def open(self) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                return

            port = self.port
            # Windows: COM10+ may need \\.\COM10
            if isinstance(port, str) and port.upper().startswith("COM"):
                try:
                    n = int(port[3:])
                    if n >= 10 and not port.startswith("\\\\.\\"):
                        port = "\\\\.\\" + port
                except ValueError:
                    pass

            self._ser = serial.Serial(
                port,
                self.baudrate,
                timeout=self.timeout,
                write_timeout=1,
            )
            try:
                self._ser.reset_input_buffer()
                self._ser.reset_output_buffer()
            except Exception:
                pass

    def probe(self) -> None:
        """Touch underlying handle; raises if unplugged/stale.""" 
        with self._lock:
            if not (self._ser and self._ser.is_open):
                raise SerialException("Serial not open")
            try:
                _ = self._ser.in_waiting
            except Exception:
                self.close()
                raise

    def close(self) -> None:
        with self._lock:
            if self._ser:
                try:
                    if self._ser.is_open:
                        self._ser.close()
                finally:
                    self._ser = None

    def read(self, n: int = 1024) -> bytes:
        with self._lock:
            if not (self._ser and self._ser.is_open):
                return b""
            try:
                return self._ser.read(n)
            except SerialException:
                self.close()
                raise

    def write(self, data: bytes) -> int:
        with self._lock:
            if not (self._ser and self._ser.is_open):
                return 0
            try:
                return self._ser.write(data)
            except SerialException:
                self.close()
                raise
