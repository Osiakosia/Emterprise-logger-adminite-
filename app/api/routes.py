# app/api/routes.py
from __future__ import annotations

import json
import os
from flask import Flask, jsonify, request, send_from_directory
from serial.serialutil import SerialException

from app.core.state import STATE
from app.core.controller import Controller
from app.logging_setup import setup_logging


def create_app() -> Flask:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    ui_dir = os.path.join(base_dir, 'ui')

    app = Flask(__name__, static_folder=ui_dir, static_url_path='/ui')

    logger = setup_logging()
    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

    com_port = os.getenv('COM_PORT', 'COM4')
    baudrate = int(os.getenv('BAUDRATE', '9600'))
    ser_timeout = float(os.getenv('SER_TIMEOUT', '0.1'))
    host_address = int(os.getenv('HOST_ADDRESS', '1'))

    devices_path = os.path.join(base_dir, 'devices.json')
    if os.path.exists(devices_path):
        try:
            with open(devices_path, 'r', encoding='utf-8') as f:
                STATE.load_devices(json.load(f))
        except Exception as e:
            logger.warning('Failed to load devices.json: %s', e)

    STATE.set_config(port=com_port, baud=baudrate, validate_checksum=STATE.validate_checksum)

    controller = Controller(
        port=com_port,
        baudrate=baudrate,
        timeout=ser_timeout,
        host_address=host_address,
        logger=logger,
    )
    controller.start()

    @app.get('/')
    def ui_index():
        return send_from_directory(ui_dir, 'index.html')

    @app.get('/pages/<path:path>')
    def ui_pages(path: str):
        return send_from_directory(os.path.join(ui_dir, 'pages'), path)

    @app.get('/api/status')
    def api_status():
        return jsonify(STATE.snapshot())

    @app.route('/api/config', methods=['GET', 'POST'])
    def api_config():
        if request.method == 'GET':
            return jsonify({
                'port': STATE.port,
                'baud': STATE.baud,
                'validate_checksum': STATE.validate_checksum,
            })

        data = request.get_json(silent=True) or {}
        port = data.get('port')
        baud = data.get('baud')
        validate = data.get('validate_checksum')

        STATE.set_config(port=port, baud=baud, validate_checksum=validate)

        try:
            controller.request_connect(STATE.port or com_port, STATE.baud or baudrate)
            return jsonify({'ok': True, 'applied': STATE.snapshot()})
        except Exception as e:
            STATE.set_connected(False, str(e))
            return jsonify({'ok': False, 'error': str(e), 'applied': STATE.snapshot()}), 500

    @app.post('/api/connect')
    def api_connect():
        data = request.get_json(silent=True) or {}
        port = (data.get('port') or STATE.port or com_port)
        baud = int(data.get('baud') or STATE.baud or baudrate)

        STATE.set_config(port=port, baud=baud)

        try:
            controller.request_connect(port, baud)
            return jsonify({'ok': True, 'status': STATE.snapshot()})
        except Exception as e:
            STATE.set_connected(False, str(e))
            return jsonify({'ok': False, 'error': str(e), 'status': STATE.snapshot()}), 500

    @app.post('/api/disconnect')
    def api_disconnect():
        controller.request_disconnect()
        return jsonify({'ok': True, 'status': STATE.snapshot()})

    @app.post('/api/clear_log')
    def api_clear_log():
        STATE.clear_frames()
        return jsonify({'ok': True})

    @app.post('/api/send')
    def api_send():
        data = request.get_json(silent=True) or {}

        try:
            dest = int(data.get('dest'))
        except Exception:
            return jsonify({'ok': False, 'error': 'dest must be integer'}), 400

        try:
            header = int(data.get('header', 254))
        except Exception:
            return jsonify({'ok': False, 'error': 'header must be integer'}), 400

        payload_hex = (data.get('data_hex') or '').strip()
        try:
            payload = bytes.fromhex(payload_hex) if payload_hex else b''
        except Exception:
            return jsonify({'ok': False, 'error': 'data_hex must be hex string'}), 400

        if not STATE.connected:
            return jsonify({'ok': False, 'error': STATE.last_error or 'Serial disconnected'}), 400

        try:
            out = controller.device.send(dest, header, payload)
            return jsonify({'ok': True, 'tx': out})
        except (SerialException, OSError) as e:
            STATE.set_connected(False, str(e))
            try:
                controller.sio.close()
            except Exception:
                pass
            return jsonify({'ok': False, 'error': str(e)}), 500
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    return app
