# # -*- coding: utf-8 -*-
# """
# Alberichi coin acceptor ccTalk Python driver (single-file)
#
# Defaults for your setup:
# - Port: COM4
# - Baudrate: 9600
# - Device address: 2
# - Host address: 1
#
# Install:
#     pip install pyserial
#
# Examples:
#     python devices\alberichi_cctalk_driver.py --info
#     python devices\alberichi_cctalk_driver.py --status
#     python devices\alberichi_cctalk_driver.py --enum-coins
#     python devices\alberichi_cctalk_driver.py --events --credit
#     python devices\alberichi_cctalk_driver.py --autotest
# """
#
# from __future__ import annotations
#
# import argparse
# import time
# from dataclasses import dataclass
# from typing import Dict, List, Optional, Tuple
#
# try:
#     import serial  # type: ignore
# except ImportError as e:
#     raise SystemExit("pyserial not installed. Run: pip install pyserial") from e
#
#
# def _u8(x: int) -> int:
#     return x & 0xFF
#
#
# def cctalk_checksum(frame_wo_checksum: bytes) -> int:
#     s = sum(frame_wo_checksum) & 0xFF
#     return _u8((-s) & 0xFF)
#
#
# def build_frame(dest: int, src: int, header: int, data: bytes = b"") -> bytes:
#     length = len(data)
#     base = bytes([_u8(dest), _u8(length), _u8(src), _u8(header)]) + data
#     return base + bytes([cctalk_checksum(base)])
#
#
# def verify_frame(frame: bytes) -> bool:
#     return len(frame) >= 5 and ((sum(frame) & 0xFF) == 0)
#
#
# def parse_frame(frame: bytes) -> Tuple[int, int, int, int, bytes]:
#     if len(frame) < 5:
#         raise ValueError("Frame too short")
#     if not verify_frame(frame):
#         raise ValueError("Bad checksum")
#     dest = frame[0]
#     length = frame[1]
#     src = frame[2]
#     header = frame[3]
#     data = frame[4:4 + length]
#     if len(data) != length:
#         raise ValueError("Length mismatch")
#     return dest, length, src, header, data
#
#
# class CCTalkSerial:
#     """ccTalk over serial with 1-wire echo filtering."""
#
#     def __init__(
#         self,
#         port: str = None,
#         baudrate: int = 9600,
#         timeout: float = 0.4,
#         write_timeout: float = 0.4,
#         serial_handle=None  # <-- naujas parametras!
#     ) -> None:
#         import serial
#         if serial_handle is not None:
#             self.ser = serial_handle          # Priima išorinį jau atidarytą handlerį
#         elif port is not None:
#             self.ser = serial.Serial(
#                 port=port,
#                 baudrate=baudrate,
#                 bytesize=serial.EIGHTBITS,
#                 parity=serial.PARITY_NONE,
#                 stopbits=serial.STOPBITS_ONE,
#                 timeout=timeout,
#                 write_timeout=write_timeout,
#             )
#         else:
#             raise ValueError("Turi nurodyti port arba serial_handle!")
#
#     def close(self) -> None:
#         try:
#             self.ser.close()
#         except Exception:
#             pass
#
#     def write_frame(self, frame: bytes) -> None:
#         self.ser.write(frame)
#         self.ser.flush()
#
#     def _read_exact(self, n: int) -> bytes:
#         buf = bytearray()
#         while len(buf) < n:
#             chunk = self.ser.read(n - len(buf))
#             if not chunk:
#                 break
#             buf.extend(chunk)
#         return bytes(buf)
#
#     def read_frame(self) -> Optional[bytes]:
#         hdr = self._read_exact(4)
#         if len(hdr) < 4:
#             return None
#         length = hdr[1]
#         rest = self._read_exact(length + 1)
#         if len(rest) < length + 1:
#             return None
#         return hdr + rest
#
#     def request(
#         self,
#         dest: int,
#         src: int,
#         header: int,
#         data: bytes = b"",
#         *,
#         retries: int = 2,
#         response_window: float = 0.5,
#         max_frames: int = 10,
#         debug: bool = False,
#     ) -> Tuple[Optional[bytes], Optional[Tuple[int, int, int, int, bytes]]]:
#         tx = build_frame(dest=dest, src=src, header=header, data=data)
#         expect_dest = _u8(src)
#         expect_src = _u8(dest)
#
#         for attempt in range(retries + 1):
#             try:
#                 self.ser.reset_input_buffer()
#                 self.write_frame(tx)
#
#                 if debug:
#                     print(f"[cctalk] TX: {tx.hex(' ')}")
#
#                 deadline = time.time() + response_window
#                 seen = 0
#
#                 while time.time() < deadline and seen < max_frames:
#                     rx = self.read_frame()
#                     if rx is None:
#                         continue
#
#                     seen += 1
#
#                     if debug:
#                         print(f"[cctalk] RX: {rx.hex(' ')}")
#
#                     # Ignore own echo on 1-wire bus
#                     if rx == tx:
#                         continue
#
#                     try:
#                         parsed = parse_frame(rx)
#                     except Exception:
#                         continue
#
#                     r_dest, _, r_src, _, _ = parsed
#                     if r_dest == expect_dest and r_src == expect_src:
#                         return rx, parsed
#
#                 if debug:
#                     print(f"[cctalk] timeout (attempt {attempt + 1})")
#                 time.sleep(0.05)
#
#             except Exception as e:
#                 if debug:
#                     print(f"[cctalk] error: {e} (attempt {attempt + 1})")
#                 time.sleep(0.05)
#
#         return None, None
#
#
# HDR_SIMPLE_POLL = 254
# HDR_REQUEST_MANUFACTURER_ID = 246
# HDR_REQUEST_PRODUCT_CODE = 245
# HDR_REQUEST_SOFTWARE_REVISION = 241
# HDR_REQUEST_SERIAL_NUMBER = 242
# HDR_RESET_DEVICE = 1
#
# HDR_REQUEST_STATUS = 248
# HDR_READ_BUFFERED_CREDIT_OR_ERROR_CODES = 229
# HDR_MODIFY_INHIBIT_STATUS = 231
# HDR_REQUEST_INHIBIT_STATUS = 230
# HDR_MODIFY_MASTER_INHIBIT_STATUS = 228
# HDR_REQUEST_COIN_ID = 184
#
# ERROR_CODES = {
#     1: "Reject coin",
#     2: "Coin inhibit active",
#     3: "Multiple coin detect",
#     4: "Coin sensor blocked",
#     5: "Coin jam",
#     6: "Fraud attempt",
#     7: "Coin too fast",
#     8: "Coin too slow",
#     9: "Diameter error",
#     10: "Thickness error",
# }
#
#
# @dataclass
# class DeviceInfo:
#     manufacturer: Optional[str] = None
#     product: Optional[str] = None
#     software: Optional[str] = None
#     serial_dec: Optional[str] = None
#
#
# @dataclass
# class BufferedEvent:
#     counter: int
#     coin_code: int
#     dir_or_error: int
#
#     def is_null(self) -> bool:
#         return self.coin_code == 0 and self.dir_or_error == 0
#
#     def is_error(self) -> bool:
#         return self.coin_code == 0 and self.dir_or_error != 0
#
#     def coin_position(self) -> Optional[int]:
#         return None if self.coin_code == 0 else self.coin_code
#
#
# class AlberichiCoinAcceptor:
#     def __init__(
#         self,
#         transport: CCTalkSerial,
#         addr: int = 2,
#         host_addr: int = 1,
#         debug: bool = False,
#     ) -> None:
#         self.t = transport
#         self.dev = _u8(addr)
#         self.host = _u8(host_addr)
#         self.debug = debug
#
#     def _cmd(self, header: int, data: bytes = b"", retries: int = 2):
#         return self.t.request(
#             self.dev,
#             self.host,
#             header,
#             data,
#             retries=retries,
#             debug=self.debug,
#         )
#
#     def simple_poll(self) -> bool:
#         _, p = self._cmd(HDR_SIMPLE_POLL)
#         return p is not None
#
#     def reset(self) -> bool:
#         _, p = self._cmd(HDR_RESET_DEVICE)
#         return p is not None
#
#     @staticmethod
#     def _ascii(data: bytes) -> str:
#         return data.decode("ascii", errors="replace").rstrip("\x00 ")
#
#     def read_device_info(self) -> DeviceInfo:
#         info = DeviceInfo()
#
#         _, p = self._cmd(HDR_REQUEST_MANUFACTURER_ID)
#         if p:
#             info.manufacturer = self._ascii(p[4])
#
#         _, p = self._cmd(HDR_REQUEST_PRODUCT_CODE)
#         if p:
#             info.product = self._ascii(p[4])
#
#         _, p = self._cmd(HDR_REQUEST_SOFTWARE_REVISION)
#         if p:
#             info.software = self._ascii(p[4])
#
#         _, p = self._cmd(HDR_REQUEST_SERIAL_NUMBER)
#         if p:
#             raw = p[4]
#             info.serial_dec = str(int.from_bytes(raw, byteorder="big", signed=False)) if raw else None
#
#         return info
#
#     def read_status(self) -> None:
#         _, p = self._cmd(HDR_REQUEST_STATUS)
#
#         if not p:
#             print("Status read failed")
#             return
#
#         data = p[4]
#         status = data[0] if data else None
#
#         print("")
#         print("------ DEVICE STATUS ------")
#         if status is None:
#             print("Status : no data")
#         elif status == 0:
#             print("Status : OK")
#         else:
#             msg = ERROR_CODES.get(status, "Unknown status/error")
#             print(f"Status : {msg} (code={status})")
#         print("---------------------------")
#
#     def enable_master(self, enabled: bool = True) -> bool:
#         data = bytes([0x01 if enabled else 0x00])
#         _, p = self._cmd(HDR_MODIFY_MASTER_INHIBIT_STATUS, data=data)
#         return p is not None
#
#     def modify_inhibit_status(self, mask1: int = 0xFF, mask2: int = 0xFF) -> bool:
#         data = bytes([_u8(mask1), _u8(mask2)])
#         _, p = self._cmd(HDR_MODIFY_INHIBIT_STATUS, data=data)
#         return p is not None
#
#     def read_coin_id(self, position: int) -> Optional[str]:
#         _, p = self._cmd(HDR_REQUEST_COIN_ID, data=bytes([_u8(position)]))
#         if not p:
#             return None
#         s = self._ascii(p[4])
#         return s if s else None
#
#     def enumerate_coin_table(self, max_positions: int = 16) -> List[Tuple[int, str]]:
#         out: List[Tuple[int, str]] = []
#         for pos in range(1, max_positions + 1):
#             cid = self.read_coin_id(pos)
#             if cid and cid.strip("\x00 "):
#                 out.append((pos, cid))
#         return out
#
#     @staticmethod
#     def coin_id_to_value_cents(coin_id: str) -> Optional[int]:
#         digits = ""
#         for ch in coin_id:
#             if ch.isdigit():
#                 digits += ch
#             elif digits:
#                 break
#         return int(digits) if digits else None
#
#     def read_buffered_events_raw(self) -> bytes:
#         _, p = self._cmd(HDR_READ_BUFFERED_CREDIT_OR_ERROR_CODES)
#         return p[4] if p else b""
#
#     def decode_buffered_events(self, payload: bytes) -> List[BufferedEvent]:
#         if not payload:
#             return []
#         counter = payload[0]
#         pairs = payload[1:]
#         out: List[BufferedEvent] = []
#         for i in range(0, min(len(pairs), 10), 2):
#             a = pairs[i]
#             b = pairs[i + 1] if i + 1 < len(pairs) else 0
#             out.append(BufferedEvent(counter=counter, coin_code=a, dir_or_error=b))
#         return out
#
#     def read_buffered_events(self) -> List[BufferedEvent]:
#         return self.decode_buffered_events(self.read_buffered_events_raw())
#
#
# def fmt_info(info: DeviceInfo) -> str:
#     lines = []
#     lines.append("")
#     lines.append("------ DEVICE INFO ------")
#     if info.manufacturer:
#         lines.append(f"Manufacturer : {info.manufacturer}")
#     if info.product:
#         lines.append(f"Product      : {info.product}")
#     if info.software:
#         lines.append(f"Software     : {info.software}")
#     if info.serial_dec:
#         lines.append(f"Serial       : {info.serial_dec}")
#     lines.append("-------------------------")
#     return "\n".join(lines)
#
#
# def main(argv: Optional[List[str]] = None) -> int:
#     ap = argparse.ArgumentParser(description="Alberichi ccTalk driver (single file)")
#     ap.add_argument("--port", default="COM4")
#     ap.add_argument("--baud", type=int, default=9600)
#     ap.add_argument("--addr", type=int, default=2)
#     ap.add_argument("--host", type=int, default=1)
#     ap.add_argument("--debug", action="store_true")
#
#     ap.add_argument("--info", action="store_true")
#     ap.add_argument("--status", action="store_true")
#     ap.add_argument("--reset", action="store_true")
#     ap.add_argument("--enable-master", action="store_true")
#     ap.add_argument("--enable-all", action="store_true")
#     ap.add_argument("--disable-all", action="store_true")
#
#     ap.add_argument("--enum-coins", action="store_true")
#     ap.add_argument("--max-positions", type=int, default=16)
#
#     ap.add_argument("--events", action="store_true")
#     ap.add_argument("--credit", action="store_true")
#     ap.add_argument("--poll-interval", type=float, default=0.3)
#
#     ap.add_argument(
#         "--autotest",
#         action="store_true",
#         help="Run full automatic test (info + status + coin table + enable + events + credit)",
#     )
#
#     args = ap.parse_args(argv)
#
#     if args.autotest:
#         args.info = True
#         args.status = True
#         args.enum_coins = True
#         args.enable_master = True
#         args.enable_all = True
#         args.events = True
#         args.credit = True
#
#     t = CCTalkSerial(port=args.port, baudrate=args.baud, timeout=0.4)
#     dev = AlberichiCoinAcceptor(t, device_addr=args.addr, host_addr=args.host, debug=args.debug)
#
#     try:
#         if not dev.simple_poll():
#             print("No response to simple poll. Check wiring/port/baud/address.")
#             return 2
#
#         if args.reset:
#             print("Reset:", "OK" if dev.reset() else "Failed")
#             time.sleep(1.0)
#
#         if args.enable_master:
#             print("Enable master inhibit:", "OK" if dev.enable_master(True) else "Failed")
#
#         if args.enable_all:
#             print("Enable all channels:", "OK" if dev.modify_inhibit_status(0xFF, 0xFF) else "Failed")
#
#         if args.disable_all:
#             print("Disable all channels:", "OK" if dev.modify_inhibit_status(0x00, 0x00) else "Failed")
#
#         if args.info:
#             print(fmt_info(dev.read_device_info()))
#
#         if args.status:
#             dev.read_status()
#
#         pos_to_cents: Dict[int, int] = {}
#         if args.enum_coins or args.credit:
#             table = dev.enumerate_coin_table(args.max_positions)
#             if table:
#                 print("------ COIN TABLE -------")
#                 for pos, cid in table:
#                     cents = dev.coin_id_to_value_cents(cid)
#                     if cents is not None:
#                         pos_to_cents[pos] = cents
#                         print(f"Pos {pos:>2} : {cid}  ->  {cents/100:.2f} EUR")
#                     else:
#                         print(f"Pos {pos:>2} : {cid}")
#                 print("-------------------------")
#             else:
#                 print("No coin IDs returned (header 184).")
#
#         if args.events:
#             print("Polling events... (Ctrl+C to stop)")
#             last_counter: Optional[int] = None
#             total_cents = 0
#
#             while True:
#                 evs = dev.read_buffered_events()
#                 if evs:
#                     counter = evs[0].counter
#                     if last_counter is None:
#                         last_counter = counter
#
#                     delta = (counter - last_counter) & 0xFF
#                     if delta:
#                         new_events = evs[: min(delta, 5)]
#                         for ev in new_events:
#                             if ev.is_error():
#                                 code = ev.dir_or_error
#                                 msg = ERROR_CODES.get(code, "Unknown error")
#                                 print(f"[ERROR] {msg} (code={code})")
#                                 continue
#
#                             pos = ev.coin_position()
#                             if pos is None:
#                                 continue
#
#                             if pos in pos_to_cents:
#                                 value = pos_to_cents[pos] / 100.0
#                                 print(f"COIN INSERTED -> {value:.2f} EUR")
#                                 if args.credit:
#                                     total_cents += pos_to_cents[pos]
#                                     print(f"TOTAL CREDIT -> {total_cents/100:.2f} EUR\n")
#                             else:
#                                 print(f"COIN INSERTED -> position {pos}")
#
#                         last_counter = counter
#
#                 time.sleep(max(0.05, args.poll_interval))
#
#         return 0
#
#     except KeyboardInterrupt:
#         print("\nStopped.")
#         return 0
#     finally:
#         t.close()
#
#
# if __name__ == "__main__":
#     raise SystemExit(main())