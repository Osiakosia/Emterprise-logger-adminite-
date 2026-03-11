from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, Tuple


class DriverError(RuntimeError):
    pass


class DriverTimeout(DriverError):
    pass


@dataclass(frozen=True)
class Step:
    header: int
    data: bytes = b""
    expected_len: Optional[int] = None
    note: str = ""
    allow_retry: bool = True
    tries: int = 2
    base_timeout: float = 0.8
    rx_timeout: float = 1.2
    delay_s: float = 0.0


class Transport(Protocol):
    def request(
        self,
        dest: int,
        header: int,
        data: bytes = b"",
        *,
        expected_len: Optional[int] = None,
        note: str = "",
        allow_retry: bool = True,
        tries: int = 2,
        base_timeout: float = 0.8,
        rx_timeout: float = 1.2,
    ) -> Tuple[int, bytes]:
        ...


class BaseDriver:
    def __init__(self, t: Transport, *, quiet: bool = True, logger=None) -> None:
        self.t = t
        self.quiet = quiet
        self.log = logger

    def run(self, dest: int, steps: Sequence[Step]) -> List[Tuple[int, bytes]]:
        out: List[Tuple[int, bytes]] = []
        for s in steps:
            rh, rd = self.t.request(
                dest,
                s.header,
                s.data,
                expected_len=s.expected_len,
                note=s.note,
                allow_retry=s.allow_retry,
                tries=s.tries,
                base_timeout=s.base_timeout,
                rx_timeout=s.rx_timeout,
            )
            out.append((rh, rd))
            if s.delay_s:
                time.sleep(s.delay_s)
        return out