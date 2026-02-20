from __future__ import annotations
import time
import threading
from typing import Optional
from .serial_io import SerialIO
from .cctalk import try_parse_frames, decode_frame, header_name
from .state import STATE, FrameRecord

class Sniffer(threading.Thread):
    def __init__(self, sio: SerialIO, logger, max_lines: int = 5000):
        super().__init__(daemon=True)
        self.sio = sio
        self.logger = logger
        self.max_lines = max_lines
        self._stop = threading.Event()
        self._buf = bytearray()

    def stop(self):
        self._stop.set()

    def run(self):
        self.logger.info("Sniffer thread started")
        while not self._stop.is_set():
            try:
                chunk = self.sio.read_available()
                if chunk:
                    self._buf.extend(chunk)
                    frames, self._buf = try_parse_frames(self._buf)
                    for fr in frames:
                        dec = decode_frame(fr)
                        if STATE.validate_checksum and not dec.valid:
                            decoded = {"error": "bad_checksum", **dec.to_dict(), "header_name": header_name(dec.header)}
                        else:
                            decoded = {**dec.to_dict(), "header_name": header_name(dec.header)}
                        rec = FrameRecord(ts=time.time(), direction="RX", addr=dec.src, raw_hex=fr.hex(), decoded=decoded)
                        STATE.add_frame(rec, self.max_lines)
                        self.logger.info("RX %s", fr.hex())
                else:
                    time.sleep(0.01)
            except Exception as e:
                STATE.set_connected(False, error=str(e))
                self.logger.exception("Sniffer error: %s", e)
                time.sleep(0.2)
        self.logger.info("Sniffer thread stopped")
