import serial, time

ser = serial.Serial("COM4", 9600, timeout=0.2)
print("OPEN", ser.is_open)

# pabandymas siųsti bet ką (čia tik patikrina, ar realiai rašo)
n = ser.write(b"\x01\x00\x01\xfe\x00")  # neteisingas cctalk frame, bet testui ok
ser.flush()
print("WROTE", n)

for _ in range(10):
    data = ser.read(1024)
    if data:
        print("RX", data.hex())
    time.sleep(0.2)

ser.close()