"""
ccTalk thesaurus dictionaries.

Contains friendly names for:
- device category IDs (DEVICE_NAMES)
- ccTalk headers (HEADERS)
- bill event codes (BILL_EVENTS)
- coin acceptor error codes (COIN_ACCEPTOR_ERRORS)

Drop this file into app/core/thesaurus.py and import it from your decoder.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Dict, Tuple



DEVICE_NAMES: Dict[int, str] = {
    0x01: "Master",
    0x02: "Coin Acceptor",
    0x03: "Coin Dispenser",
    0x04: "ccTalk Hopper",
    0x05: "ccTalk Hopper",
    0x0A: "Unknown",
    0x28: "iPRO/Recycler",
    0x32: "Unknown",
    0x50: "Dongle",
    0x82: "Unknown",
    0x83: "Unknown",
    0xA0: "Unknown",
    0xC3: "Unknown",
    0xF0: "Unknown",
}

HEADERS: Dict[int, str] = {
    0x00: "Response Message",
    0x01: "Reset device",
    0x02: "Request comms status variables",
    0x03: "Clear comms status variables",
    0x04: "Request comms revision",

    0x14: "Modify recycle current count setting",   # 20
    0x15: "Clear total count",                      # 21
    0x16: "Pump RNG",                               # 22
    0x17: "Request cipher key",                     # 23
    0x18: "Request variable setting",               # 24
    0x19: "Request variable key setting",           # 25
    0x1A: "Request total count",                    # 26
    0x1B: "Enable Recycler",                        # 27
    0x1C: "Dispense bills",                         # 28
    0x1D: "Request recycler status",                # 29
    0x1E: "Emergency stop",                         # 30
    0x1F: "Request store to cash box",              # 31
    0x20: "Modify recycle currency setting",        # 32
    0x21: "Request recycler software version",      # 33
    0x22: "Request recycle count",                  # 34
    0x23: "Modify recycle count",                   # 35
    0x24: "Request recycle current count",          # 36

    0x34: "Request Recycle Operating Mode",         # 52
    0x35: "Modify Recycle Operating Mode",          # 53
    0x36: "Request Stack Box Information",          # 54
    0x3B: "Recycle Read buffered Bill events",      # 59

    0x81: "Read barcode data",                      # 129
    0x88: "Store encryption code",                  # 136
    0x89: "Switch encryption code",                 # 137
    0x8A: "Finish firmware upgrade",                # 138
    0x8B: "Begin firmware upgrade",                 # 139
    0x8C: "Upload firmware",                        # 140
    0x8D: "Request firmware upgrade capability",    # 141

    0x91: "Request currency revision",              # 145
    0x98: "Request bill operating mode",            # 152
    0x99: "Modify bill operating mode",             # 153
    0x9A: "Route bill",                             # 154
    0x9B: "Request bill position",                  # 155
    0x9C: "Request country scaling factor",         # 156
    0x9D: "Request bill id",                        # 157
    0x9F: "Read buffered bill events",              # 159

    0xA3: "Test hopper",                            # 163
    0xA4: "Enable hopper",                          # 164
    0xA5: "Modify Variable Set",                    # 165
    0xA6: "Request hopper status",                  # 166
    0xA7: "Dispense hopper coins",                  # 167
    0xAA: "Request base year",                      # 170
    0xAC: "Emergency stop",                         # 172
    0xB2: "Request bank select",                    # 178
    0xB3: "Modify bank select",                     # 179

    0xC0: "Request build code",                     # 192
    0xC3: "Request last modification date",         # 195
    0xC4: "Request creation date",                  # 196
    0xC5: "Calculate ROM checksum",                 # 197

    0xD2: "Modify sorter paths",                    # 210
    0xD5: "Request Option flags",                   # 213
    0xD8: "Request data storage availability",      # 216
    0xD9: "Request payout high / low status",       # 217

    0xE3: "Request master inhibit status",          # 227
    0xE4: "Modify master inhibit status",           # 228
    0xE5: "Read buffered credit or error codes",    # 229
    0xE6: "Request inhibit status",                 # 230
    0xE7: "Modify inhibit status",                  # 231

    0xF1: "Request software revision",              # 241
    0xF2: "Request serial number",                  # 242
    0xF3: "Request database version",               # 243
    0xF4: "Request product code",                   # 244
    0xF5: "Request equipment category id",          # 245
    0xF6: "Request manufacturer id",                # 246
    0xF7: "Request variable set",                   # 247
    0xF9: "Request polling priority",               # 249

    0xFA: "Address Random",                         # 250
    0xFB: "Address Change",                         # 251
    0xFC: "Address Clash",                          # 252
    0xFD: "Address Poll",                           # 253
    0xFE: "Simple poll",                            # 254
    0xFF: "Factory set-up and test",                # 255,
}


class BillDenomination(IntEnum):
    Euro5 = 1
    Euro10 = 2
    Euro20 = 3
    Euro50 = 4
    Euro100 = 5
    Euro200 = 6
    Euro500 = 7



BILL_EVENTS: Dict[Tuple[int, int], str] = {
    (0, 0): "Master inhibit active",
    (0, 1): "Bill returned from escrow",
    (0, 2): "Invalid bill (validation fail)",
    (0, 3): "Invalid bill (transport problem)",
    (0, 4): "Inhibited bill (on serial)",
    (0, 5): "Inhibited bill (on DIP switches)",
    (0, 6): "Bill jammed in transport (unsafe mode)",
    (0, 7): "Bill jammed in stacker",
    (0, 8): "Bill pulled backwards",
    (0, 9): "Bill tamper",
    (0, 10): "Stacker OK",
    (0, 11): "Stacker removed",
    (0, 12): "Stacker inserted",
    (0, 13): "Stacker faulty",
    (0, 14): "Stacker full",
    (0, 15): "Stacker jammed",
    (0, 16): "Bill jammed in transport (safe mode)",
    (0, 17): "Opto fraud detected",
    (0, 18): "String fraud detected",
    (0, 19): "Anti-string mechanism faulty",
    (0, 20): "Barcode detected",
    (0, 21): "Unknown bill type stacked",
}

# BILL_EVENTS keys are stored as "a,b" strings to keep JSON pretty; convert helper below.

def bill_event_description(result_a: int, result_b: int) -> str:
    return BILL_EVENTS.get((result_a, result_b), "Unknown/Unmapped bill event")


COIN_ACCEPTOR_ERRORS: Dict[int, Dict[str, str]] = {
    0: {
        "description": "Null event (no error)",
        "rejected": "No"
    },
    1: {
        "description": "Reject coin",
        "rejected": "Yes"
    },
    2: {
        "description": "Inhibited coin",
        "rejected": "Yes"
    },
    3: {
        "description": "Multiple window",
        "rejected": "Yes"
    },
    4: {
        "description": "Wake-up timeout",
        "rejected": "Possible"
    },
    5: {
        "description": "Validation timeout",
        "rejected": "Possible"
    },
    6: {
        "description": "Credit sensor timeout",
        "rejected": "Possible"
    },
    7: {
        "description": "Sorter opto timeout",
        "rejected": "No"
    },
    8: {
        "description": "2nd close coin error",
        "rejected": "Yes"
    },
    9: {
        "description": "Accept gate not ready",
        "rejected": "Yes"
    },
    10: {
        "description": "Credit sensor not ready",
        "rejected": "Yes"
    },
    11: {
        "description": "Sorter not ready",
        "rejected": "Yes"
    },
    12: {
        "description": "Reject coin not cleared",
        "rejected": "Yes"
    },
    13: {
        "description": "Validation sensor not ready",
        "rejected": "Yes"
    },
    14: {
        "description": "Credit sensor blocked",
        "rejected": "Yes"
    },
    15: {
        "description": "Sorter opto blocked",
        "rejected": "Yes"
    },
    16: {
        "description": "Credit sequence error",
        "rejected": "No"
    },
    17: {
        "description": "Coin going backwards",
        "rejected": "No"
    },
    18: {
        "description": "Coin too fast (credit sensor)",
        "rejected": "No"
    },
    19: {
        "description": "Coin too slow (credit sensor)",
        "rejected": "No"
    },
    20: {
        "description": "C.O.S. mechanism activated",
        "rejected": "No"
    },
    21: {
        "description": "DCE opto timeout",
        "rejected": "Possible"
    },
    22: {
        "description": "DCE opto not seen",
        "rejected": "Yes"
    },
    23: {
        "description": "Credit sensor reached too early",
        "rejected": "No"
    },
    24: {
        "description": "Reject coin (sequential trip)",
        "rejected": "Yes"
    },
    25: {
        "description": "Reject slug",
        "rejected": "Yes"
    },
    26: {
        "description": "Reject sensor blocked",
        "rejected": "No"
    },
    27: {
        "description": "Games overload",
        "rejected": "No"
    },
    28: {
        "description": "Max coin meter pulses exceeded",
        "rejected": "No"
    },
    29: {
        "description": "Accept gate open not closed",
        "rejected": "No"
    },
    30: {
        "description": "Accept gate closed not open",
        "rejected": "Yes"
    },
    31: {
        "description": "Manifold opto timeout",
        "rejected": "No"
    },
    32: {
        "description": "Manifold opto blocked",
        "rejected": "Yes"
    },
    33: {
        "description": "Manifold not ready",
        "rejected": "Yes"
    },
    34: {
        "description": "Security status changed",
        "rejected": "Possible"
    },
    35: {
        "description": "Motor exception",
        "rejected": "Possible"
    },
    36: {
        "description": "Swallowed coin",
        "rejected": "No"
    },
    37: {
        "description": "Coin too fast (validation sensor)",
        "rejected": "Yes"
    },
    38: {
        "description": "Coin too slow (validation sensor)",
        "rejected": "Yes"
    },
    39: {
        "description": "Coin incorrectly sorted",
        "rejected": "No"
    },
    40: {
        "description": "External light attack",
        "rejected": "No"
    },
    253: {
        "description": "Data block request",
        "rejected": "No"
    },
    254: {
        "description": "Coin return mechanism activated",
        "rejected": "No"
    },
    255: {
        "description": "Unspecified alarm code",
        "rejected": "No"
    }
}

def coin_acceptor_error_description(code: int) -> tuple[str, str]:
    info = COIN_ACCEPTOR_ERRORS.get(int(code))
    if not info:
        return ("Unknown error", "Unknown")
    return (info["description"], info["rejected"])

