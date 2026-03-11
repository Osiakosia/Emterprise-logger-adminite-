import time
import serial

def cctalk_frame(dest: int, src: int, cmd: int, data: bytes = b"") -> bytes:
    ln = len(data)
    header = bytes([dest, ln, src, cmd]) + data
    chk = (-sum(header)) & 0xFF
    return header + bytes([chk])

def hexdump(b: bytes) -> str:
    return b.hex(" ")

ser = serial.Serial("COM4", 9600, timeout=0.5)
print("OPEN", ser.is_open)

dest = 5
src = 1

tx = cctalk_frame(dest, src, 0xFE, b"")  # simple poll
print("TX", hexdump(tx))

ser.reset_input_buffer()
ser.write(tx)
ser.flush()

# CCtalk atsakymas irgi frame; pabandome perskaityti iki 64 bytes
rx = ser.read(64)
print("RX", hexdump(rx), "len=", len(rx))

ser.close()