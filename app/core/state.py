# app/core/state.py
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
    """
    Global in-memory state for UI + API.
    - Thread-safe
    - Stores last N frames
    - Stores devices loaded from devices.json (list format)
    """

    def __init__(self):
        self._lock = Lock()

        self.connected: bool = False
        self.port: Optional[str] = None
        self.baud: int = 9600
        self.validate_checksum: bool = True
        self.last_error: Optional[str] = None

        # address(int) -> {"name":..., "address":..., "type":...}
        self.devices_by_addr: Dict[int, Dict[str, Any]] = {}

        self.frames: List[FrameRecord] = []

    def set_config(self, *, port: Optional[str] = None, baud: Optional[int] = None,
                   validate_checksum: Optional[bool] = None):
        with self._lock:
            if port is not None:
                self.port = str(port)
            if baud is not None:
                self.baud = int(baud)
            if validate_checksum is not None:
                self.validate_checksum = bool(validate_checksum)

    def set_connected(self, connected: bool, error: Optional[str] = None):
        with self._lock:
            self.connected = bool(connected)
            self.last_error = error

    def load_devices(self, devices_json: Dict[str, Any]) -> None:
        """
        Expects:
        {
          "devices": [
            { "name": "...", "address": 2, "type": "..." }
          ]
        }
        """
        by_addr: Dict[int, Dict[str, Any]] = {}
        for d in (devices_json or {}).get("devices", []):
            try:
                addr = int(d.get("address"))
            except Exception:
                continue
            by_addr[addr] = {
                "name": str(d.get("name", f"Addr {addr}")),
                "address": addr,
                "type": str(d.get("type", "")),
            }
        with self._lock:
            self.devices_by_addr = by_addr

    def resolve_device_name(self, addr: int) -> str:
        d = self.devices_by_addr.get(int(addr))
        if not d:
            return f"Addr {addr}"
        return f'{d.get("name", "Device")} ({addr})'

    def devices_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self.devices_by_addr[k] for k in sorted(self.devices_by_addr.keys())]

    def add_frame(self, rec: FrameRecord, max_lines: int = 5000):
        with self._lock:
            self.frames.append(rec)
            if len(self.frames) > max_lines:
                self.frames = self.frames[-max_lines:]

    def clear_frames(self):
        with self._lock:
            self.frames = []

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connected": self.connected,
                "port": self.port,
                "baud": self.baud,
                "validate_checksum": self.validate_checksum,
                "last_error": self.last_error,
                "devices": [self.devices_by_addr[k] for k in sorted(self.devices_by_addr.keys())],
                "frames": [
                    {
                        "ts": r.ts,
                        "time": time.strftime("%H:%M:%S", time.localtime(r.ts)),
                        "direction": r.direction,
                        "addr": r.addr,
                        "device_name": self.resolve_device_name(r.addr),
                        "raw_hex": r.raw_hex,
                        "decoded": r.decoded,
                    }
                    for r in self.frames[-200:]
                ],
            }


STATE = AppState()
