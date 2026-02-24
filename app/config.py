import os

class Config:
    # Serial
    COM_PORT = os.getenv("COM_PORT", "COM4")
    BAUDRATE = int(os.getenv("BAUDRATE", "9600"))
    SER_TIMEOUT = float(os.getenv("SER_TIMEOUT", "0.1"))

    # ccTalk addressing
    HOST_ADDRESS = int(os.getenv("HOST_ADDRESS", "1"))

    # Runtime
    START_CONTROLLER = os.getenv("START_CONTROLLER", "1") == "1"