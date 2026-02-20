from __future__ import annotations
import serial
from typing import Optional

class SerialIO:
    def __init__(self):
        self.ser: Optional[serial.Serial] = None

    def open(self, port: str, baud: int, timeout: float = 0.05):
        self.close()
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        # ccTalk is single-wire TTL in many devices; with USB-RS232 adapters you usually need
        # proper wiring/level shifting. This is just the host side.

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def is_open(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def write(self, data: bytes):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial not open")
        self.ser.write(data)

    def read(self, n: int = 1) -> bytes:
        if not self.ser or not self.ser.is_open:
            return b""
        return self.ser.read(n)

    def read_available(self) -> bytes:
        if not self.ser or not self.ser.is_open:
            return b""
        n = self.ser.in_waiting
        if n:
            return self.ser.read(n)
        return b""
