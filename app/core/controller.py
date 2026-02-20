from __future__ import annotations
import time
from typing import Optional, Dict, Any
from .serial_io import SerialIO
from .cctalk import build_frame, decode_frame, header_name
from .state import STATE, FrameRecord

class DeviceController:
    def __init__(self, sio: SerialIO, logger, host_address: int = 1):
        self.sio = sio
        self.logger = logger
        self.host_address = host_address

    def send(self, dest: int, header: int, data: bytes = b"") -> Dict[str, Any]:
        frame = build_frame(dest=dest, src=self.host_address, header=header, data=data)
        self.sio.write(frame)
        dec = decode_frame(frame)
        rec = FrameRecord(ts=time.time(), direction="TX", addr=dest, raw_hex=frame.hex(),
                          decoded={**dec.to_dict(), "header_name": header_name(dec.header)})
        STATE.add_frame(rec)
        self.logger.info("TX %s", frame.hex())
        return rec.decoded

    # High-level helpers for common devices
    def simple_poll(self, dest: int):
        return self.send(dest, 254)

    def request_status(self, dest: int):
        return self.send(dest, 248)

    def request_software_revision(self, dest: int):
        return self.send(dest, 241)

    def payout_by_value(self, dest: int, value: int):
        # value in lowest currency unit (e.g. cents)
        if not (0 <= value <= 65535):
            raise ValueError("value must be 0..65535")
        data = bytes([value & 0xFF, (value >> 8) & 0xFF])
        return self.send(dest, 53, data)
