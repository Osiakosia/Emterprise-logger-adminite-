from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.drivers.base import DriverTimeout



def _field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_cctalk_raw_hex(raw_hex: str) -> Optional[Tuple[int, int, int, bytes]]:
    """
    Parse ccTalk packet from hex string:
      [dest][len][src][header][data...][checksum]
    Returns (dest, src, header, data_bytes) or None.
    """
    if not raw_hex:
        return None
    hx = str(raw_hex).replace(" ", "").strip()
    if not hx:
        return None
    try:
        b = bytes.fromhex(hx)
    except Exception:
        return None

    if len(b) < 5:
        return None

    dest = b[0]
    ln = b[1]
    src = b[2]
    header = b[3]

    # Ensure declared payload fits (excluding checksum byte at end)
    if 4 + ln > len(b) - 1:
        return None

    data = b[4 : 4 + ln]
    return dest, src, header, data


class ControllerTransport:
    """
    Transport that sends through controller.device.send(...) and reads RX frames from state.frames.

    Key features:
    - Parses decoded data if present; otherwise falls back to parsing raw_hex as ccTalk frame.
    - Filters by:
        * RX direction
        * source device address (addr)
        * destination host address (from raw_hex)
        * expected_len (optional)
        * expected_resp_header (optional)
    - Uses min_ts guard to avoid consuming stale RX frames.
    - Uses a per-device-address lock to ensure only one outstanding request/response per dest.
    """

    def __init__(self, *, controller, state, host_address: int, poll_interval_s: float = 0.01) -> None:
        self.controller = controller
        self.state = state
        self.host_address = int(host_address)
        self.poll_interval_s = float(poll_interval_s)

        self._stash: List[Any] = []

        # Per-destination address locking (prevents concurrent RX mixing)
        self._locks_guard = threading.Lock()
        self._addr_locks: Dict[int, threading.RLock] = {}

    def _lock_for(self, dest: int) -> threading.RLock:
        d = int(dest)
        with self._locks_guard:
            lk = self._addr_locks.get(d)
            if lk is None:
                lk = threading.RLock()
                self._addr_locks[d] = lk
            return lk

    def _frames(self) -> List[Any]:
        return list(getattr(self.state, "frames", []) or [])

    def _is_rx(self, f: Any) -> bool:
        return str(_field(f, "direction", "")).upper() == "RX"

    def _rx_src_addr(self, f: Any) -> Optional[int]:
        a = _field(f, "addr", None)
        if a is not None:
            return int(a)
        a = _field(f, "from", None) or _field(f, "src", None) or _field(f, "src_addr", None)
        return int(a) if a is not None else None

    def _rx_dest_addr(self, f: Any) -> Optional[int]:
        raw_hex = _field(f, "raw_hex", "")
        parsed = _parse_cctalk_raw_hex(raw_hex)
        if parsed is not None:
            dest, _src, _hdr, _data = parsed
            return int(dest)

        a = _field(f, "to", None) or _field(f, "dest", None) or _field(f, "dest_addr", None)
        return int(a) if a is not None else None

    def _rx_header_and_data(self, f: Any) -> Optional[Tuple[int, bytes, int]]:
        decoded = _field(f, "decoded", None)

        if isinstance(decoded, dict) and decoded:
            hdr = _field(decoded, "header", None)
            if hdr is None:
                hdr = _field(decoded, "cmd", None)

            data_hex = _field(decoded, "data_hex", "") or _field(decoded, "payload_hex", "")
            if data_hex:
                try:
                    data = bytes.fromhex(str(data_hex).replace(" ", "").strip())
                except Exception:
                    data = b""
            else:
                data = b""

            ln = _field(decoded, "len", None)
            if ln is None:
                ln = len(data)

            return int(hdr or 0), data, int(ln)

        raw_hex = _field(f, "raw_hex", "")
        parsed = _parse_cctalk_raw_hex(raw_hex)
        if parsed is None:
            return None
        _dest, _src, header, data = parsed
        return int(header), data, len(data)

    def _matches(
        self,
        f: Any,
        *,
        dev_addr: int,
        expected_len: Optional[int],
        expected_resp_header: Optional[int],
    ) -> Optional[Tuple[int, bytes]]:
        if not self._is_rx(f):
            return None

        if self._rx_src_addr(f) != dev_addr:
            return None

        rd = self._rx_dest_addr(f)
        if rd is not None and rd != self.host_address:
            return None

        info = self._rx_header_and_data(f)
        if info is None:
            return None
        rh, data, ln = info

        if expected_resp_header is not None and rh != expected_resp_header:
            return None

        if expected_len is not None and ln != expected_len:
            return None

        return rh, data

    def _try_take_from_stash(
        self,
        dev_addr: int,
        expected_len: Optional[int],
        expected_resp_header: Optional[int],
        *,
        min_ts: Optional[float],
    ) -> Optional[Tuple[int, bytes]]:
        # newest -> oldest
        for i in range(len(self._stash) - 1, -1, -1):
            f = self._stash[i]

            if min_ts is not None:
                fts = _field(f, "ts", None)
                try:
                    if fts is not None and float(fts) <= float(min_ts):
                        continue
                except Exception:
                    pass

            got = self._matches(
                f,
                dev_addr=dev_addr,
                expected_len=expected_len,
                expected_resp_header=expected_resp_header,
            )
            if got is not None:
                self._stash.pop(i)
                return got

        return None

    def _request_once(
        self,
        dest: int,
        header: int,
        data: bytes,
        *,
        expected_len: Optional[int],
        expected_resp_header: Optional[int],
        timeout: float,
        note: str = "",
    ) -> Tuple[int, bytes]:
        """
        One TX->RX transaction.
        Sends via controller.device.send() and waits for matching RX frame in STATE.frames.

        Matching rules are implemented in _matches().
        """
        # Guard against consuming old frames
        min_ts = time.time()

        # Best-effort: if controller is disconnected, fail fast
        if getattr(self.state, "connected", True) is False:
            raise DriverTimeout(f"Serial disconnected (dest={dest} note={note!r})")

        # Send (this should also add a TX FrameRecord into STATE in your DeviceController)
        try:
            self.controller.device.send(int(dest), int(header), data or b"")
        except Exception as e:
            raise DriverTimeout(f"TX failed dest={dest} hdr=0x{header:02X} note={note!r}: {e}")

        deadline = min_ts + float(timeout)

        # First, try stash (in case we already buffered a late RX)
        got = self._try_take_from_stash(
            int(dest),
            expected_len=expected_len,
            expected_resp_header=expected_resp_header,
            min_ts=min_ts,
        )
        if got is not None:
            return got

        # Poll STATE.frames until timeout
        while time.time() < deadline:
            frames = self._frames()

            # newest -> oldest: we want the most recent matching RX
            for i in range(len(frames) - 1, -1, -1):
                f = frames[i]

                # only consider frames that are newer than min_ts
                fts = _field(f, "ts", None)
                try:
                    if fts is not None and float(fts) <= float(min_ts):
                        continue
                except Exception:
                    # if ts is not parseable, don't filter it out
                    pass

                # If it's a match - return immediately
                got = self._matches(
                    f,
                    dev_addr=int(dest),
                    expected_len=expected_len,
                    expected_resp_header=expected_resp_header,
                )
                if got is not None:
                    return got

                # Otherwise: if it's RX from same device to our host, stash it
                # so another request can consume it later.
                if self._is_rx(f) and self._rx_src_addr(f) == int(dest):
                    rd = self._rx_dest_addr(f)
                    if rd is None or rd == self.host_address:
                        self._stash.append(f)
                        if len(self._stash) > 500:
                            self._stash = self._stash[-500:]

            time.sleep(self.poll_interval_s)

        raise DriverTimeout(
            f"Timeout waiting RX dest={dest} hdr=0x{header:02X} "
            f"expected_len={expected_len} expected_resp_header={expected_resp_header} note={note!r}"
        )

    def request(
            self,
            dest: int,
            header: int,
            data: bytes = b"",
            *,
            expected_len: Optional[int] = None,
            expected_resp_header: Optional[int] = None,
            note: str = "",
            allow_retry: bool = True,
            tries: int = 2,
            base_timeout: float = 0.8,
            rx_timeout: float = 1.2,
            lock_timeout_s: Optional[float] = None,  # NEW
    ) -> Tuple[int, bytes]:
        lk = self._lock_for(dest)

        # Acquire per-dest lock (optionally with timeout)
        if lock_timeout_s is None:
            lk.acquire()
            acquired = True
        else:
            acquired = lk.acquire(timeout=float(lock_timeout_s))

        if not acquired:
            # Use DriverTimeout for now; API layer will convert to HTTP 409.
            raise DriverTimeout(f"Device busy dest={dest} lock_timeout_s={lock_timeout_s} note={note!r}")

        try:
            last_err: Optional[Exception] = None
            ntries = tries if allow_retry else 1

            for attempt in range(1, ntries + 1):
                try:
                    timeout = (base_timeout * attempt) if allow_retry else rx_timeout
                    return self._request_once(
                        int(dest),
                        int(header),
                        data or b"",
                        expected_len=expected_len,
                        expected_resp_header=expected_resp_header,
                        timeout=timeout,
                        note=note,
                    )
                except Exception as e:
                    last_err = e
                    time.sleep(0.05)

            assert last_err is not None
            raise last_err
        finally:
            lk.release()