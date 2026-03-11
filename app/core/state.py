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
    """
    Thread-safe shared state for UI/API.
    Controller thread is the ONLY thing that should touch serial.
    """

    def __init__(self):
        self._lock = Lock()

        # ---------- Serial / connection ----------
        self.connected: bool = False
        self.port: Optional[str] = None
        self.baud: int = 9600
        self.validate_checksum: bool = True
        self.last_error: Optional[str] = None

        # Extended serial health (for multi-level badge)
        self.serial_status: Dict[str, Any] = {
            "connected": False,
            "serial_open": False,
            "port_present": False,
            "thread_running": False,
            "port": None,
            "baud": None,
            "last_error": None,
            "ts": None,
        }

        # ---------- Frames ----------
        self.frames: List[FrameRecord] = []

        # ---------- Devices ----------
        # Configured devices (from devices.json)
        self.configured_devices: List[Dict[str, Any]] = []
        self._cfg_addr_index: Dict[int, Dict[str, Any]] = {}

        # Seen devices (discovered on the bus via RX/identify)
        self.seen_devices: List[Dict[str, Any]] = []
        self._seen_addr_index: Dict[int, Dict[str, Any]] = {}

        # Backward compat: existing code/UI expects STATE.devices + STATE._addr_index
        # We'll map those to SEEN.
        self.devices: List[Dict[str, Any]] = self.seen_devices
        self._addr_index: Dict[int, Dict[str, Any]] = self._seen_addr_index

    # ============================================================
    # CONFIG / CONNECTION
    # ============================================================

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

    def set_serial_status(self, payload: Dict[str, Any]):
        with self._lock:
            self.serial_status.update(payload)

    # ============================================================
    # FRAMES
    # ============================================================

    def add_frame(self, rec: FrameRecord, max_lines: int = 5000):
        with self._lock:
            self.frames.append(rec)
            if len(self.frames) > max_lines:
                self.frames = self.frames[-max_lines:]

    def clear_frames(self):
        with self._lock:
            self.frames = []

    # ============================================================
    # DEVICES
    # ============================================================

    def _ensure_device_defaults(self, rec: Dict[str, Any]) -> None:
        rec.setdefault("manufacturer", "")
        rec.setdefault("category", "")
        rec.setdefault("serial", "")
        rec.setdefault("sw_rev", "")
        rec.setdefault("product_text", "")
        rec.setdefault("last_identify_ts", None)

    def load_devices(self, payload: Any):
        """
        Load CONFIGURED devices (from devices.json) without overwriting SEEN devices.
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

                    rec = {"name": name, "address": addr, "type": dtype}
                    self._ensure_device_defaults(rec)
                    devices.append(rec)

            elif isinstance(payload, dict):
                for key, d in payload.items():
                    if not isinstance(d, dict) or "address" not in d:
                        continue
                    name = str(d.get("name") or key)
                    addr = int(d.get("address"))
                    dtype = str(d.get("type") or "")

                    rec = {"name": name, "address": addr, "type": dtype}
                    self._ensure_device_defaults(rec)
                    devices.append(rec)

        except Exception:
            devices = []

        devices.sort(key=lambda x: int(x.get("address", 0)))

        with self._lock:
            self.configured_devices = devices
            self._cfg_addr_index = {int(d["address"]): d for d in devices}

    def device_for_addr(self, addr: int) -> Optional[Dict[str, Any]]:
        """
        Prefer seen; fall back to configured.
        """
        a = int(addr)
        with self._lock:
            return self._seen_addr_index.get(a) or self._cfg_addr_index.get(a)

    def note_device(self, addr: int, name: Optional[str] = None, dtype: Optional[str] = None):
        a = int(addr)
        with self._lock:
            # If this address exists in configured_devices, inherit friendly name/type
            cfg = self._cfg_addr_index.get(a)
            if cfg:
                if not name:
                    name = cfg.get("name") or name
                if dtype is None or str(dtype).strip() == "":
                    dtype = cfg.get("type") or dtype

            if a in self._seen_addr_index:
                if name:
                    self._seen_addr_index[a]["name"] = str(name)
                if dtype is not None:
                    self._seen_addr_index[a]["type"] = str(dtype)

                self._ensure_device_defaults(self._seen_addr_index[a])
                return

            rec = {
                "name": str(name) if name else f"Addr {a}",
                "address": a,
                "type": str(dtype) if dtype else "",
            }
            self._ensure_device_defaults(rec)

            self.seen_devices.append(rec)
            self.seen_devices.sort(key=lambda x: int(x.get("address", 0)))
            self._seen_addr_index[a] = rec

    def note_device(self, addr: int, name: Optional[str] = None, dtype: Optional[str] = None):
        """
        Note a SEEN device (only call this when there is RX/confirmed presence).
        """
        a = int(addr)
        with self._lock:
            if a in self._seen_addr_index:
                if name:
                    self._seen_addr_index[a]["name"] = str(name)
                if dtype is not None:
                    self._seen_addr_index[a]["type"] = str(dtype)

                self._ensure_device_defaults(self._seen_addr_index[a])
                return

            rec = {
                "name": str(name) if name else f"Addr {a}",
                "address": a,
                "type": str(dtype) if dtype else "",
            }
            self._ensure_device_defaults(rec)

            self.seen_devices.append(rec)
            self.seen_devices.sort(key=lambda x: int(x.get("address", 0)))
            self._seen_addr_index[a] = rec

    def update_device_identify(self, addr: int, info: Dict[str, Any]) -> None:
        """
        Store identify fields into the SEEN device table for UI listing.
        """
        a = int(addr)
        with self._lock:
            if a not in self._seen_addr_index:
                rec = {"name": f"Addr {a}", "address": a, "type": ""}
                self._ensure_device_defaults(rec)
                self.seen_devices.append(rec)
                self.seen_devices.sort(key=lambda x: int(x.get("address", 0)))
                self._seen_addr_index[a] = rec

            rec = self._seen_addr_index[a]
            self._ensure_device_defaults(rec)

            def _s(k: str) -> str:
                v = info.get(k)
                return str(v).strip() if v is not None else ""

            rec["manufacturer"] = _s("manufacturer")
            rec["category"] = _s("category")
            rec["product_text"] = _s("product_text")
            rec["serial"] = _s("serial") or _s("serial_raw")
            rec["sw_rev"] = _s("sw_rev")
            rec["last_identify_ts"] = time.time()

    # ============================================================
    # SNAPSHOT FOR UI
    # ============================================================

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            tail = self.frames[-200:]

            rx = sum(1 for f in tail if f.direction == "RX")
            tx = sum(1 for f in tail if f.direction == "TX")

            return {
                "connected": self.connected,
                "port": self.port,
                "baud": self.baud,
                "validate_checksum": self.validate_checksum,
                "last_error": self.last_error,

                "serial": self.serial_status,

                "counts": {
                    "rx": rx,
                    "tx": tx,
                    "decode_errors": 0,
                    "devices_seen": len(self.seen_devices),
                },

                # Backward compat
                "devices": self.seen_devices,

                # NEW split lists
                "devices_configured": self.configured_devices,
                "devices_seen": self.seen_devices,

                "frames": [
                    {
                        "ts": r.ts,
                        "time": time.strftime("%H:%M:%S", time.localtime(r.ts)),
                        "direction": r.direction,
                        "from": r.addr if r.direction == "RX" else 1,
                        "to": r.addr if r.direction == "TX" else 1,
                        "raw_hex": r.raw_hex,
                        "decoded": r.decoded,
                    }
                    for r in tail
                ],
            }


STATE = AppState()