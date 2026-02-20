import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logging(log_dir: str = "logs", filename: str = "session.log") -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cctalk")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if reloaded by Flask
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    fh = RotatingFileHandler(Path(log_dir) / filename, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger
