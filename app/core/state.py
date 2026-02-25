from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional
import time


@dataclass
class FrameRecord:
    ts: float
    direction: str  # "RX" or "TX"
    addr: int
    raw_hex: str
    decoded: Dict[str, Any] = field(default_factory=dict)


class AppState:
    """Thread-safe shared state for UI/API.

    Notes:
      - Controller thread is the ONLY thing that should touch the serial port.
      - Flask endpoints only read/modify STATE and signal controller.
    """

    def __init__(self):
        self._lock = Lock()

        # connection
        self.connected: bool = False
        self.port: Optional[str] = None
        self.baud: int = 9600
        self.validate_checksum: bool = True
        self.last_error: Optional[str] = None

        # frames
        self.frames: List[FrameRecord] = []

        # devices
        # internal canonical list: [{name,address,type}, ...]
        self.devices: List[Dict[str, Any]] = []
        # addr -> device dict
        self._addr_index: Dict[int, Dict[str, Any]] = {}

    # ---------- config / connection ----------
    def set_config(
        self,
        *,
        port: Optional[str] = None,
        baud: Optional[int] = None,
        validate_checksum: Optional[bool] = None,
    ):
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

    # ---------- frames ----------
    def add_frame(self, rec: FrameRecord, max_lines: int = 5000):
        with self._lock:
            self.frames.append(rec)
            if len(self.frames) > max_lines:
                self.frames = self.frames[-max_lines:]

    def clear_frames(self):
        with self._lock:
            self.frames = []

    # ---------- devices ----------
    def load_devices(self, payload: Any):
        """Accepts either:

        1) {"devices": [{"name":..., "address":..., "type":...}, ...]}
        2) {"some_key": {"address": 2, "type": "..."}, ...}  (old format)

        Produces a stable list, indexed by address.
        """
        devices: List[Dict[str, Any]] = []

        try:
            if isinstance(payload, dict) and isinstance(payload.get("devices"), list):
                for d in payload["devices"]:
                    if not isinstance(d, dict):
                        continue
                    name = str(d.get("name") or "Device")
                    addr = int(d.get("address"))
                    dtype = str(d.get("type") or "")
                    devices.append({"name": name, "address": addr, "type": dtype})
            elif isinstance(payload, dict):
                # old format mapping; beware duplicate keys like "hopper".
                for key, d in payload.items():
                    if not isinstance(d, dict) or "address" not in d:
                        continue
                    name = str(d.get("name") or key)
                    addr = int(d.get("address"))
                    dtype = str(d.get("type") or "")
                    devices.append({"name": name, "address": addr, "type": dtype})
        except Exception:
            devices = []

        # stable ordering
        devices.sort(key=lambda x: int(x.get("address", 0)))

        with self._lock:
            self.devices = devices
            self._addr_index = {int(d["address"]): d for d in devices if "address" in d}

    def device_for_addr(self, addr: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._addr_index.get(int(addr))

    def device_label(self, addr: int) -> str:
        d = self.device_for_addr(addr)
        if not d:
            return f"Addr {addr}"
        name = d.get("name") or f"Addr {addr}"
        dtype = d.get("type")
        if dtype and dtype != name:
            return f"{name} ({dtype})"
        return str(name)

    def note_device(self, addr: int, name: Optional[str] = None, dtype: Optional[str] =              None) -> None:
        """
        Ensure a device entry exists for an address.
        Safe to call on TX/RX even if devices were not loaded from config.
        """
        a = int(addr)
        with self._lock:
            if a in self._addr_index:
                # optionally enrich existing record
                if name:
                    self._addr_index[a]["name"] = str(name)
                if dtype is not None:
                    self._addr_index[a]["type"] = str(dtype)
                return

            rec = {
                "name": str(name) if name else f"Addr {a}",
                "address": a,
                "type": str(dtype) if dtype else "",
            }
            self.devices.append(rec)
            self.devices.sort(key=lambda x: int(x.get("address", 0)))
            self._addr_index[a] = rec

            # ---------- snapshot ----------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            # last 200 for UI
            tail = self.frames[-200:]
            return {
                "connected": self.connected,
                "port": self.port,
                "baud": self.baud,
                "validate_checksum": self.validate_checksum,
                "last_error": self.last_error,
                "devices": self.devices,
                "frames": [
                    {
                        "ts": r.ts,
                        "time": time.strftime("%H:%M:%S", time.localtime(r.ts)),
                        "direction": r.direction,
                        "addr": r.addr,
                        "device": (self._addr_index.get(int(r.addr)) or {}).get("name"),
                        "raw_hex": r.raw_hex,
                        "decoded": r.decoded,
                    }
                    for r in tail
                ],
            }


STATE = AppState()
