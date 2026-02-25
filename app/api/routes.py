from __future__ import annotations

import json
import os
import logging
from flask import jsonify
from app.core.thesaurus import HEADERS

from flask import Flask, jsonify, request, send_from_directory
from serial.serialutil import SerialException

from app.core.state import STATE
from app.core.controller import Controller
from app.logging_setup import setup_logging


def _should_start_thread() -> bool:
    # In Flask debug/reload mode, the module is imported twice.
    # Start background threads ONLY in the reloader child process.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return True
    # If FLASK_DEBUG is set, Werkzeug will run a reloader -> don't start in parent.
    if os.environ.get("FLASK_DEBUG") in ("1", "true", "True"):
        return False
    return True


def _load_devices_json(path: str, logger) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        STATE.load_devices(payload)
        if logger:
            logger.info("Loaded devices from %s (%d entries)", path, len(STATE.devices))
    except Exception as e:
        if logger:
            logger.warning("Failed to load devices.json: %s", e)


def create_app() -> Flask:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ui_dir = os.path.join(base_dir, "ui")

    app = Flask(__name__, static_folder=ui_dir, static_url_path="/ui")

    logger = setup_logging()
    # silence HTTP access logs (GET /api/status 200, etc.)
    # logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

    # defaults
    com_port = os.getenv("COM_PORT", "COM4")
    baudrate = int(os.getenv("BAUDRATE", "9600"))
    ser_timeout = float(os.getenv("SER_TIMEOUT", "0.1"))
    host_address = int(os.getenv("HOST_ADDRESS", "1"))

    # devices
    _load_devices_json(os.path.join(base_dir, "devices.json"), logger)

    # state config
    STATE.set_config(port=com_port, baud=baudrate, validate_checksum=STATE.validate_checksum)

    # controller (single instance per process)
    controller = Controller(
        port=com_port,
        baudrate=baudrate,
        timeout=ser_timeout,
        host_address=host_address,
        logger=logger,
    )

    if _should_start_thread():
        controller.start()

    # ---------- UI ----------
    @app.get("/")
    def ui_index():
        return send_from_directory(ui_dir, "index.html")

    @app.get("/pages/<path:path>")
    def ui_pages(path: str):
        return send_from_directory(os.path.join(ui_dir, "pages"), path)

    # ---------- API ----------
    @app.get("/api/status")
    def api_status():
        return jsonify(STATE.snapshot())

    @app.get("/api/devices")
    def api_devices():
        return jsonify({"devices": STATE.devices})

    @app.get("/api/headers")
    def api_headers():
        """
        Return ccTalk header list for UI auto button generation (from app.core.thesaurus.HEADERS).
        """
        data = [{"header": int(k), "name": str(v)} for k, v in HEADERS.items()]
        data.sort(key=lambda x: x["header"])
        return jsonify({"ok": True, "headers": data})

    @app.route("/api/config", methods=["GET", "POST"])
    def api_config():
        if request.method == "GET":
            return jsonify({
                "port": STATE.port,
                "baud": STATE.baud,
                "validate_checksum": STATE.validate_checksum,
            })

        data = request.get_json(silent=True) or {}
        port = data.get("port")
        baud = data.get("baud")
        validate = data.get("validate_checksum")
        reconnect = bool(data.get("reconnect", False))

        STATE.set_config(port=port, baud=baud, validate_checksum=validate)

        # IMPORTANT: do NOT auto reconnect unless explicitly requested.
        # This prevents "blinking" when UI polls /api/config.
        if reconnect:
            controller.request_connect(STATE.port or com_port, STATE.baud or baudrate)

        return jsonify({"ok": True, "applied": STATE.snapshot()})

    @app.post("/api/connect")
    def api_connect():
        data = request.get_json(silent=True) or {}
        port = (data.get("port") or STATE.port or com_port)
        baud = int(data.get("baud") or STATE.baud or baudrate)

        STATE.set_config(port=port, baud=baud)
        controller.request_connect(port, baud)
        return jsonify({"ok": True, "status": STATE.snapshot()})

    @app.post("/api/disconnect")
    def api_disconnect():
        controller.request_disconnect()
        return jsonify({"ok": True, "status": STATE.snapshot()})

    @app.post("/api/clear_log")
    def api_clear_log():
        STATE.clear_frames()
        return jsonify({"ok": True})

    @app.post("/api/send")
    def api_send():
        data = request.get_json(silent=True) or {}

        try:
            dest = int(data.get("dest"))
        except Exception:
            return jsonify({"ok": False, "error": "dest must be integer"}), 400

        try:
            header = int(data.get("header", 254))
        except Exception:
            return jsonify({"ok": False, "error": "header must be integer"}), 400

        payload_hex = (data.get("data_hex") or "").strip()
        try:
            payload = bytes.fromhex(payload_hex) if payload_hex else b""
        except Exception:
            return jsonify({"ok": False, "error": "data_hex must be hex string"}), 400

        if not STATE.connected:
            return jsonify({"ok": False, "error": STATE.last_error or "Serial disconnected"}), 400

        try:
            out = controller.device.send(dest, header, payload)
            return jsonify({"ok": True, "tx": out})
        except (SerialException, OSError) as e:
            STATE.set_connected(False, str(e))
            try:
                controller.sio.close()
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 500
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500



    return app
