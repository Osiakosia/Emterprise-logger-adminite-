from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.drivers.base import BaseDriver, DriverError, DriverTimeout, Transport

print("LOADED: app.drivers.devices.hopper")


class HopperPayoutError(DriverError):
    pass


def hexsp(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def is_ascii_printable(data: bytes) -> bool:
    if not data:
        return True
    printable = 0
    for ch in data:
        if ch in (9, 10, 13) or (32 <= ch <= 126):
            printable += 1
    return (printable / max(1, len(data))) >= 0.85


def as_text_or_hex(data: bytes) -> str:
    if not data:
        return ""
    if is_ascii_printable(data):
        return data.decode("ascii", errors="replace").strip("\x00\r\n ")
    return hexsp(data)


def u24_le_to_int(b: bytes) -> int:
    if len(b) < 3:
        raise ValueError("Need 3 bytes for u24")
    return b[0] | (b[1] << 8) | (b[2] << 16)


@dataclass
class A6Status:
    EC: int
    remaining: int
    paid: int
    unpaid: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "EC": self.EC,
            "remaining": self.remaining,
            "paid": self.paid,
            "unpaid": self.unpaid,
        }


class HopperDeviceBase(BaseDriver):
    # Common headers
    HDR_POLL = 0xFE
    HDR_RESET = 0x01
    HDR_MANUFACTURER = 0xF6
    HDR_CATEGORY = 0xF5
    HDR_PRODUCT_TEXT = 0xF4
    HDR_TOKEN3 = 0xF2
    HDR_SERIAL = 0xF1
    HDR_SOFTWARE_REV = 0xD9
    HDR_BUILD = 0xC0

    # Hopper headers
    HDR_ENABLE = 0xA4
    HDR_TEST = 0xA3
    HDR_STATUS = 0xA6
    HDR_DISPENSE = 0xA7
    HDR_DISPENSE_COUNT = 0xA8

    # MoneyControls extras
    HDR_CIPHER = 0xA0

    def __init__(self, t: Transport, addr: int, *, quiet: bool = True, logger=None):
        super().__init__(t, quiet=quiet, logger=logger)
        self.addr = int(addr)
        self.vendor_guess = "unknown"

    def _new_result(self, coins: int) -> Dict[str, Any]:
        return {
            "ok": False,
            "vendor_guess": self.vendor_guess,
            "addr": self.addr,
            "requested_coins": coins,
        }

    def _tx(
        self,
        header: int,
        data: bytes = b"",
        *,
        expected_len: Optional[int] = None,
        note: str = "",
        allow_retry: bool = True,
        tries: int = 2,
        base_timeout: float = 0.8,
        rx_timeout: float = 1.2,
        lock_timeout_s: Optional[float] = None,
    ) -> Tuple[int, bytes]:
        return self.t.request(
            self.addr,
            header,
            data,
            expected_len=expected_len,
            note=note,
            allow_retry=allow_retry,
            tries=tries,
            base_timeout=base_timeout,
            rx_timeout=rx_timeout,
            lock_timeout_s=lock_timeout_s,
        )

    def poll(self) -> None:
        self._tx(self.HDR_POLL, b"", expected_len=0, note="poll", tries=2, base_timeout=0.6, rx_timeout=0.6)

    def reset(self) -> None:
        # best-effort
        try:
            self._tx(self.HDR_RESET, b"", expected_len=0, note="reset", allow_retry=False, rx_timeout=1.0)
        except Exception:
            pass

    def request_a6(self) -> A6Status:
        _, d = self._tx(self.HDR_STATUS, b"", expected_len=4, note="A6", tries=2, base_timeout=0.8)
        return A6Status(d[0], d[1], d[2], d[3])

    def request_a8_raw(self) -> bytes:
        # A8 grįžta 3 baitai (u24 little-endian) šiame hopperyje – fiksuojam ilgį.
        _, d = self._tx(self.HDR_DISPENSE_COUNT, b"", expected_len=3, note="A8", tries=2, base_timeout=0.9)
        return d

    def identify_common(self, *, lock_timeout_s: Optional[float] = None) -> Dict[str, Any]:
        info: Dict[str, Any] = {"addr": self.addr, "vendor_guess": self.vendor_guess}

        def safe_text(h: int, note: str) -> str:
            try:
                _, d = self._tx(
                    h,
                    b"",
                    expected_len=None,
                    note=note,
                    tries=2,
                    base_timeout=0.9,
                    lock_timeout_s=lock_timeout_s,
                )
                return as_text_or_hex(d)
            except Exception:
                return ""

        info["manufacturer"] = safe_text(self.HDR_MANUFACTURER, "F6")
        info["category"] = safe_text(self.HDR_CATEGORY, "F5")
        info["product_text"] = safe_text(self.HDR_PRODUCT_TEXT, "F4")

        try:
            _, d = self._tx(
                self.HDR_TOKEN3,
                b"",
                expected_len=None,
                note="F2",
                tries=2,
                base_timeout=0.9,
                lock_timeout_s=lock_timeout_s,
            )
            info["token3_hex"] = hexsp(d[:3])
        except Exception:
            info["token3_hex"] = ""

        info["serial_raw"] = safe_text(self.HDR_SERIAL, "F1")
        info["sw_rev"] = safe_text(self.HDR_SOFTWARE_REV, "D9")
        info["build"] = safe_text(self.HDR_BUILD, "C0")

        try:
            _, d = self._tx(
                self.HDR_TEST,
                b"",
                expected_len=None,
                note="A3",
                tries=2,
                base_timeout=0.9,
                lock_timeout_s=lock_timeout_s,
            )
            info["test_raw"] = hexsp(d)
        except Exception:
            info["test_raw"] = ""

        # A6/A8 su timeout (ne per request_a6/request_a8_raw, nes jos nepriima lock_timeout_s)
        try:
            _, d = self._tx(
                self.HDR_STATUS,
                b"",
                expected_len=4,
                note="A6",
                tries=2,
                base_timeout=0.8,
                lock_timeout_s=lock_timeout_s,
            )
            info["a6"] = A6Status(d[0], d[1], d[2], d[3]).as_dict()
        except Exception:
            info["a6"] = {}

        try:
            _, d = self._tx(
                self.HDR_DISPENSE_COUNT,
                b"",
                expected_len=3,
                note="A8",
                tries=2,
                base_timeout=0.9,
                lock_timeout_s=lock_timeout_s,
            )
            info["a8_raw_hex"] = hexsp(d)
            if len(d) >= 3:
                info["a8_u24"] = u24_le_to_int(d[:3])
        except Exception:
            info["a8_raw_hex"] = ""

        return info

    def payout(self, coins: int, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError


class AlbericiHopper(HopperDeviceBase):
    def enable_payout(self) -> None:
        self._tx(self.HDR_ENABLE, bytes([0xA5]), expected_len=0, note="A4(A5)", tries=2, base_timeout=1.0)

    def dispense(self, coins: int) -> Tuple[int, bytes]:
        _, token = self._tx(self.HDR_TOKEN3, b"", expected_len=None, note="F2(token3)")
        payload = token[:3] + bytes([coins & 0xFF])
        return self._tx(
            self.HDR_DISPENSE,
            payload,
            expected_len=None,
            note="A7(token+N)",
            allow_retry=False,
            rx_timeout=2.0,
        )

    def a8_counter(self) -> int:
        d = self.request_a8_raw()
        return u24_le_to_int(d[:3]) if len(d) >= 3 else 0

    def payout(
        self,
        coins: int,
        *,
        reset_before_payout: bool = False,  # default: NO RESET
        a6_poll_interval: float = 0.08,
        a6_timeout: float = 30.0,
    ) -> Dict[str, Any]:
        res = self._new_result(coins)
        res["mode"] = "alberici_token3+N"
        try:
            if reset_before_payout:
                self.reset()
                time.sleep(0.2)
                self.poll()

            self.enable_payout()

            before_a8 = self.a8_counter()
            res["before_a8"] = before_a8

            st0 = self.request_a6()
            res["a6_before"] = st0.as_dict()

            if st0.remaining != 0:
                deadline = time.time() + a6_timeout
                last = st0
                while time.time() < deadline:
                    st = self.request_a6()
                    last = st
                    if st.remaining == 0:
                        break
                    time.sleep(a6_poll_interval)
                if last.remaining != 0:
                    raise DriverTimeout("Guard: payout still active before dispense")

            rh, rd = self.dispense(coins)
            res["reply_hdr"] = rh
            res["reply_data"] = hexsp(rd)

            if rh == 0x05:
                raise HopperPayoutError("A7 rejected (0x05 NAK)")

            deadline = time.time() + a6_timeout
            last_print: Optional[Tuple[int, int, int]] = None
            while True:
                if time.time() > deadline:
                    raise DriverTimeout("Timeout waiting payout completion (A6)")
                st = self.request_a6()
                triple = (st.remaining, st.paid, st.unpaid)
                if triple != last_print:
                    last_print = triple
                    if self.quiet:
                        print(f"A6 change: EC={st.EC} remaining={st.remaining} paid={st.paid} unpaid={st.unpaid}")
                if st.remaining == 0:
                    if st.unpaid != 0:
                        raise HopperPayoutError(f"Payout finished but unpaid={st.unpaid}")
                    break
                time.sleep(a6_poll_interval)

            after_a8 = self.a8_counter()
            res["after_a8"] = after_a8
            res["delta_a8"] = after_a8 - before_a8
            if res["delta_a8"] < coins:
                raise HopperPayoutError(f"A8 confirm failed: delta_a8={res['delta_a8']} expected>={coins}")

            res["ok"] = True
            return res
        except Exception as e:
            res["ok"] = False
            res["error"] = str(e)
            try:
                res["a6_last"] = self.request_a6().as_dict()
            except Exception:
                pass
            return res


class MoneyControlsHopper(HopperDeviceBase):
    def enable_payout(self) -> None:
        self._tx(self.HDR_ENABLE, bytes([0xA5]), expected_len=0, note="A4(A5)", tries=2, base_timeout=1.0)

    def request_cipher(self) -> bytes:
        _, d = self._tx(self.HDR_CIPHER, b"", expected_len=8, note="A0", tries=2, base_timeout=1.0)
        return d

    def a8_counter(self) -> int:
        d = self.request_a8_raw()
        if len(d) >= 3:
            return d[1] | (d[2] << 8)
        return 0

    def dispense(self, coins: int) -> Tuple[int, bytes]:
        payload = (b"\x00" * 8) + bytes([coins & 0xFF])
        return self._tx(
            self.HDR_DISPENSE,
            payload,
            expected_len=None,
            note="A7(8x00+N)",
            allow_retry=False,
            rx_timeout=2.0,
        )

    def payout(
        self,
        coins: int,
        *,
        reset_before_payout: bool = False,  # default: NO RESET
        a6_poll_interval: float = 0.10,
        a6_timeout: float = 30.0,
    ) -> Dict[str, Any]:
        res = self._new_result(coins)
        res["mode"] = "moneycontrols_8zeros+N"
        try:
            if reset_before_payout:
                self.reset()
                time.sleep(0.25)
                self.poll()

            self.enable_payout()

            before_a8 = self.a8_counter()
            res["before_a8"] = before_a8

            st0 = self.request_a6()
            res["a6_before"] = st0.as_dict()

            if st0.remaining != 0:
                deadline = time.time() + a6_timeout
                last = st0
                while time.time() < deadline:
                    st = self.request_a6()
                    last = st
                    if st.remaining == 0:
                        break
                    time.sleep(a6_poll_interval)
                if last.remaining != 0:
                    raise DriverTimeout("Guard: payout still active before dispense")

            try:
                cipher = self.request_cipher()
                res["cipher_hex"] = hexsp(cipher)
            except Exception as e:
                res["cipher_error"] = str(e)

            rh, rd = self.dispense(coins)
            res["reply_hdr"] = rh
            res["reply_data"] = hexsp(rd)
            if rh == 0x05:
                raise HopperPayoutError("A7 rejected (0x05 NAK)")

            deadline = time.time() + a6_timeout
            last_print: Optional[Tuple[int, int, int]] = None
            while True:
                if time.time() > deadline:
                    raise DriverTimeout("Timeout waiting payout completion (A6)")
                st = self.request_a6()
                triple = (st.remaining, st.paid, st.unpaid)
                if triple != last_print:
                    last_print = triple
                    if self.quiet:
                        print(f"A6 change: EC={st.EC} remaining={st.remaining} paid={st.paid} unpaid={st.unpaid}")
                if st.remaining == 0:
                    if st.unpaid != 0:
                        raise HopperPayoutError(f"Payout finished but unpaid={st.unpaid}")
                    break
                time.sleep(a6_poll_interval)

            after_a8 = self.a8_counter()
            res["after_a8"] = after_a8
            res["delta_a8"] = after_a8 - before_a8
            if res["delta_a8"] < coins:
                raise HopperPayoutError(f"A8 confirm failed: delta_a8={res['delta_a8']} expected>={coins}")

            res["ok"] = True
            return res
        except Exception as e:
            res["ok"] = False
            res["error"] = str(e)
            try:
                res["a6_last"] = self.request_a6().as_dict()
            except Exception:
                pass
            return res


def autodetect_hopper(
    t: Transport,
    scan_addrs: List[int],
    *,
    quiet: bool = True,
    lock_timeout_s: Optional[float] = None,
) -> Tuple[HopperDeviceBase, Dict[str, Any]]:
    last_errors: List[str] = []
    last_timeout: Optional[DriverTimeout] = None  # NEW

    for addr in scan_addrs:
        try:
            try:
                t.request(
                    addr,
                    0xFE,
                    b"",
                    expected_len=None,
                    note="poll_scan",
                    tries=1,
                    base_timeout=0.25,
                    rx_timeout=0.25,
                    lock_timeout_s=lock_timeout_s,
                )
            except Exception:
                pass

            base = HopperDeviceBase(t, addr, quiet=quiet)
            info = base.identify_common(lock_timeout_s=lock_timeout_s)

            man_txt = (info.get("manufacturer") or "").strip()
            prod_txt = (info.get("product_text") or "").strip()
            if not man_txt and not prod_txt:
                raise DriverTimeout(f"Device busy or no identify response dest={addr}")

            man = man_txt.lower()
            prod = prod_txt.lower()

            if ("money controls" in man) or ("sch2" in prod) or ("mk2" in prod) or ("compact" in prod):
                dev = MoneyControlsHopper(t, addr, quiet=quiet)
                dev.vendor_guess = "moneycontrols"
                info["vendor_guess"] = "moneycontrols"
                return dev, info

            if ("azkoyen" in man) or ("azk" in man):
                dev = AlbericiHopper(t, addr, quiet=quiet)
                dev.vendor_guess = "azkoyen"
                info["vendor_guess"] = "azkoyen"
                return dev, info

            if ("alberici" in man) or ("hoppertwo" in prod) or ("cctalk" in prod and "hopper" in prod):
                dev = AlbericiHopper(t, addr, quiet=quiet)
                dev.vendor_guess = "alberici"
                info["vendor_guess"] = "alberici"
                return dev, info

            last_errors.append(f"addr={addr}: unknown vendor man='{man_txt}' prod='{prod_txt}'")

        except DriverTimeout as e:
            last_timeout = e
            last_errors.append(f"addr={addr}: {e}")
            continue
        except Exception as e:
            last_errors.append(f"addr={addr}: {e}")
            continue

    # If the most recent failure was a timeout/busy, bubble it up so API can return 409.
    if last_timeout is not None:
        raise last_timeout

    raise DriverError(
        "Hopper autodetect failed. Tried " + ", ".join(map(str, scan_addrs))
        + (f". Last: {last_errors[-1]}" if last_errors else "")
    )