from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

# Optional thesaurus dictionaries (friendly names)
try:
    from .thesaurus import DEVICE_NAMES as TH_DEVICE_NAMES, HEADERS as TH_HEADERS
except Exception:
    TH_DEVICE_NAMES = {}
    TH_HEADERS = {}

def checksum_cctalk(data: bytes) -> int:
    # ccTalk uses 8-bit checksum so that sum(all bytes) % 256 == 0
    return (-sum(data)) & 0xFF

def build_frame(dest: int, src: int, header: int, data: bytes) -> bytes:
    length = len(data)
    body = bytes([dest, length, src, header]) + data
    csum = checksum_cctalk(body)
    return body + bytes([csum])

def validate_frame(frame: bytes) -> bool:
    return (sum(frame) & 0xFF) == 0

@dataclass
class DecodedFrame:
    dest: int
    length: int
    src: int
    header: int
    data: bytes
    checksum: int
    valid: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dest": self.dest,
            "dest_name": device_name(self.dest),
            "len": self.length,
            "src": self.src,
            "src_name": device_name(self.src),
            "header": self.header,
            "header_name": header_name(self.header),
            "data_hex": self.data.hex(),
            "checksum": self.checksum,
            "valid_checksum": self.valid,
        }

def try_parse_frames(buffer: bytearray) -> Tuple[List[bytes], bytearray]:
    # ccTalk: [dest][len][src][header][data...][checksum]
    frames: List[bytes] = []
    i = 0
    while True:
        if len(buffer) - i < 5:
            break
        dest = buffer[i]
        length = buffer[i+1]
        total = 5 + length
        if len(buffer) - i < total:
            break
        frame = bytes(buffer[i:i+total])
        frames.append(frame)
        i += total
    remainder = buffer[i:]
    return frames, bytearray(remainder)

def decode_frame(frame: bytes) -> DecodedFrame:
    dest = frame[0]
    length = frame[1]
    src = frame[2]
    header = frame[3]
    data = frame[4:4+length]
    checksum = frame[4+length]
    valid = validate_frame(frame)
    return DecodedFrame(dest, length, src, header, data, checksum, valid)

HEADER_NAMES = {
    254: "Simple poll",
    241: "Request software revision",
    242: "Request serial number",
    244: "Request manufacturer id",
    245: "Request equipment category id",
    246: "Request product code",
    247: "Request database version",
    248: "Request status",
    253: "Reset device",
    53:  "Payout by value",
}

def header_name(header: int) -> str:
    # Prefer thesaurus if present
    if TH_HEADERS:
        return TH_HEADERS.get(header, HEADER_NAMES.get(header, f"0x{header:02X}"))
    return HEADER_NAMES.get(header, f"0x{header:02X}")

def device_name(addr: int) -> str:
    if TH_DEVICE_NAMES:
        return TH_DEVICE_NAMES.get(addr, f"0x{addr:02X}")
    return f"0x{addr:02X}"

