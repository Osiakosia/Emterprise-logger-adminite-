from __future__ import annotations
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional, Dict, Any, List
import time

@dataclass
class FrameRecord:
    ts: float
    direction: str  # "RX" or "TX"
    addr: int
    raw_hex: str
    decoded: Dict[str, Any] = field(default_factory=dict)

class AppState:
    def __init__(self):
        self._lock = Lock()
        self.connected: bool = False
        self.port: Optional[str] = None
        self.baud: int = 9600
        self.validate_checksum: bool = True
        self.last_error: Optional[str] = None
        self.frames: List[FrameRecord] = []
        self.device_map: Dict[str, Dict[str, Any]] = {}

    def set_config(self, *, port: Optional[str]=None, baud: Optional[int]=None, validate_checksum: Optional[bool]=None):
        with self._lock:
            if port is not None: self.port = port
            if baud is not None: self.baud = int(baud)
            if validate_checksum is not None: self.validate_checksum = bool(validate_checksum)

    def set_connected(self, connected: bool, error: Optional[str]=None):
        with self._lock:
            self.connected = connected
            self.last_error = error

    def set_devices(self, devices: Dict[str, Dict[str, Any]]):
        with self._lock:
            self.device_map = devices

    def add_frame(self, rec: FrameRecord, max_lines: int = 5000):
        with self._lock:
            self.frames.append(rec)
            if len(self.frames) > max_lines:
                self.frames = self.frames[-max_lines:]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connected": self.connected,
                "port": self.port,
                "baud": self.baud,
                "validate_checksum": self.validate_checksum,
                "last_error": self.last_error,
                "devices": self.device_map,
                "frames": [
                    {
                        "ts": r.ts,
                        "time": time.strftime("%H:%M:%S", time.localtime(r.ts)),
                        "direction": r.direction,
                        "addr": r.addr,
                        "raw_hex": r.raw_hex,
                        "decoded": r.decoded,
                    } for r in self.frames[-200:]  # UI window
                ]
            }

STATE = AppState()
