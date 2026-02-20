from __future__ import annotations
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from app.config import CONFIG
from app.logging_setup import setup_logging
from app.core.state import STATE
from app.core.serial_io import SerialIO
from app.core.sniffer import Sniffer
from app.core.controller import DeviceController

sio = SerialIO()
sniffer = None
controller = None

def _load_devices() -> dict:
    p = Path("devices.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def create_app() -> Flask:
    global sniffer, controller

    app = Flask(__name__, static_folder="../../ui", static_url_path="/ui")
    logger = setup_logging("logs", "session.log")

    # init state
    STATE.set_config(port=CONFIG.default_port, baud=CONFIG.default_baud, validate_checksum=CONFIG.validate_checksum)
    STATE.set_devices(_load_devices())

    controller = DeviceController(sio, logger, host_address=1)

    @app.get("/")
    def root():
        return send_from_directory("ui", "index.html")

    @app.get("/ui/<path:path>")
    def ui_files(path: str):
        return send_from_directory("ui", path)

    @app.get("/api/status")
    def api_status():
        return jsonify(STATE.snapshot())

    @app.post("/api/config")
    def api_config():
        payload = request.get_json(force=True, silent=True) or {}
        validate = payload.get("validate_checksum")
        port = payload.get("port")
        baud = payload.get("baud")
        if validate is not None:
            STATE.set_config(validate_checksum=bool(validate))
        if port is not None:
            STATE.set_config(port=str(port))
        if baud is not None:
            STATE.set_config(baud=int(baud))
        return jsonify({"ok": True, "state": STATE.snapshot()})

    @app.post("/api/connect")
    def api_connect():
        global sniffer
        payload = request.get_json(force=True, silent=True) or {}
        port = payload.get("port") or STATE.port or CONFIG.default_port
        baud = int(payload.get("baud") or STATE.baud or CONFIG.default_baud)
        try:
            sio.open(port, baud, timeout=CONFIG.read_timeout_s)
            STATE.set_config(port=port, baud=baud)
            STATE.set_connected(True, error=None)
            if sniffer:
                sniffer.stop()
            sniffer = Sniffer(sio, logger, max_lines=CONFIG.max_log_lines)
            sniffer.start()
            logger.info("Connected to %s @ %s", port, baud)
            return jsonify({"ok": True, "state": STATE.snapshot()})
        except Exception as e:
            STATE.set_connected(False, error=str(e))
            logger.exception("Connect failed: %s", e)
            return jsonify({"ok": False, "error": str(e), "state": STATE.snapshot()}), 500

    @app.post("/api/disconnect")
    def api_disconnect():
        global sniffer
        try:
            if sniffer:
                sniffer.stop()
                sniffer = None
            sio.close()
            STATE.set_connected(False, error=None)
            logger.info("Disconnected")
            return jsonify({"ok": True, "state": STATE.snapshot()})
        except Exception as e:
            STATE.set_connected(False, error=str(e))
            logger.exception("Disconnect failed: %s", e)
            return jsonify({"ok": False, "error": str(e), "state": STATE.snapshot()}), 500

    @app.post("/api/send")
    def api_send():
        payload = request.get_json(force=True, silent=True) or {}
        dest = int(payload.get("dest", 2))
        header = int(payload.get("header", 254))
        data_hex = (payload.get("data_hex") or "").strip().replace(" ", "")
        data = bytes.fromhex(data_hex) if data_hex else b""
        if not sio.is_open():
            return jsonify({"ok": False, "error": "Not connected"}), 400
        try:
            out = controller.send(dest=dest, header=header, data=data)
            return jsonify({"ok": True, "tx": out, "state": STATE.snapshot()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return app
