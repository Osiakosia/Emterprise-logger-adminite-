# app/core/device_controller.py
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .serial_io import SerialIO
from .cctalk import build_frame, decode_frame, header_name
from .state import STATE, FrameRecord


class DeviceController:
    """
    High-level ccTalk sender.
    Writes TX frames to serial and logs them into STATE.
    """

    def __init__(self, sio: SerialIO, logger=None, host_address: int = 1):
        self.sio = sio
        self.logger = logger
        self.host_address = int(host_address)

    def send(self, dest: int, header: int, data: bytes = b"") -> Dict[str, Any]:
        frame = build_frame(dest=int(dest), src=self.host_address, header=int(header), data=data)

        # TX to wire
        self.sio.write(frame)

        # Store TX in STATE
        dec = decode_frame(frame)
        rec = FrameRecord(
            ts=time.time(),
            direction="TX",
            addr=int(dest),
            raw_hex=frame.hex(),
            decoded={**dec.to_dict(), "header_name": header_name(dec.header)},
        )
        STATE.add_frame(rec)
        # update devices table
        STATE.note_device(int(dest))

        if self.logger:
            self.logger.info("TX %s", frame.hex())

        return rec.decoded

    # Common helpers
    def simple_poll(self, dest: int):
        return self.send(dest, 254)

    def request_status(self, dest: int):
        return self.send(dest, 248)

    def request_software_revision(self, dest: int):
        return self.send(dest, 241)

    def payout_by_value(self, dest: int, value: int):
        if not (0 <= int(value) <= 65535):
            raise ValueError("value must be 0..65535")
        v = int(value)
        data = bytes([v & 0xFF, (v >> 8) & 0xFF])
        return self.send(dest, 53, data)