# ccTalk Recycler Logger/Controller (Enterprise)

## What this is
A small Flask + pySerial project that:
- Connects to a serial port (e.g. USB Serial Port COM4)
- Logs TX/RX ccTalk frames to `logs/session.log`
- Shows live frames in a browser UI (auto-refresh)
- Lets you toggle checksum validation (strict vs raw sniffing)
- Lets you send ccTalk commands to specific device addresses (acceptor / hopper / recycler)

## Run in PyCharm
1. Open the project folder in PyCharm.
2. Create a venv and install requirements:
   - `pip install -r requirements.txt`
3. Run:
   - `python run_logger.py`
4. Open:
   - http://127.0.0.1:5000

## Notes
- ccTalk is usually 9600 8N1 (device dependent).
- With USB-RS232 you may need a proper interface/wiring to your ccTalk bus.
- Edit `devices.json` to match your real addresses.
