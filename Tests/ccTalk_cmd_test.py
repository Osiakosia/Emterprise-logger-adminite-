import serial

def cctalk_frame(dest: int, src: int, cmd: int, data: bytes = b"") -> bytes:
    ln = len(data)
    header = bytes([dest, ln, src, cmd]) + data
    chk = (-sum(header)) & 0xFF
    return header + bytes([chk])

def hexdump(b: bytes) -> str:
    return b.hex(" ")

ser = serial.Serial("COM4", 9600, timeout=0.8)
dest, src = 5, 1

for cmd in [0xFE, 0xF6, 0xF4, 0xF2]:
    tx = cctalk_frame(dest, src, cmd)
    ser.reset_input_buffer()
    ser.write(tx); ser.flush()
    rx = ser.read(64)
    print(f"cmd=0x{cmd:02X} TX={hexdump(tx)} RX={hexdump(rx)} len={len(rx)}")

ser.close()