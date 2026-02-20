from dataclasses import dataclass

@dataclass
class AppConfig:
    default_port: str = "COM4"
    default_baud: int = 9600
    read_timeout_s: float = 0.05
    validate_checksum: bool = True
    max_log_lines: int = 5000

CONFIG = AppConfig()
