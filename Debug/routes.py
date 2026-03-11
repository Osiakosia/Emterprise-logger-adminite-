from __future__ import annotations

import json
import time
import os
from flask import Flask, jsonify, request, send_from_directory
from serial.serialutil import SerialException

from app.core.thesaurus import HEADERS
from app.core.state import STATE
from app.core.controller import Controller
from app.logging_setup import setup_logging
from app.drivers.base import DriverTimeout  # jei dar nėra
from app.drivers.devices.hopper import autodetect_hopper
from app.drivers.base import DriverTimeout, DriverError

from flask import Flask, request, Response
from app.bootstrap import acceptor_transport, hopper_transport, recycler_transport
# from app.drivers.devices.coin_acceptor import AlberichiCoinAcceptor
from app.drivers.devices.hopper import AlbericiHopper
# from app.drivers.devices.recycler import Recycler  # Kai tik turėsi šį draiverį

# acceptor = AlberichiCoinAcceptor(acceptor_transport, addr=2)
hopper = AlbericiHopper(hopper_transport, addr=3)
# recycler = Recycler(recycler_transport, addr=40)


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

    def _frame_to_dict(fr):
        if isinstance(fr, dict):
            return fr
        d = getattr(fr, "__dict__", None)
        return d if isinstance(d, dict) else {}

    def _last_frame_ts() -> float:
        frames = list(getattr(STATE, "frames", []) or [])
        if not frames:
            return 0.0
        f = _frame_to_dict(frames[-1])
        return _to_float_ts(f.get("ts"))

    def _saw_rx_from_addr(frames, addr, min_ts) -> bool:
        """
        Returns True if frames contain an RX from addr with ts >= min_ts.
        (Pure helper if you already have a frames list.)
        """
        for f in frames or []:
            try:
                if str(f.get("direction", "")).upper() != "RX":
                    continue
                if int(f.get("addr")) != int(addr):
                    continue
                ts = f.get("ts")
                if ts is None:
                    return True
                if float(ts) >= float(min_ts):
                    return True
            except Exception:
                continue
        return False

    def _frame_src_addr(f) -> int | None:
        # support both snapshot formats
        for key in ("addr", "from", "src"):
            v = f.get(key)
            if v is None:
                continue
            try:
                return int(v)
            except Exception:
                pass
        return None

    def _wait_rx_from_addr(addr: int, min_ts: float, timeout_s: float):
        t0 = time.time()
        while (time.time() - t0) < float(timeout_s):
            frames = list(getattr(STATE, "frames", []) or [])

            best = None
            for fr in frames[-400:]:
                f = _frame_to_dict(fr)
                try:
                    if str(f.get("direction", "")).strip().upper() != "RX":
                        continue
                    src = f.get("from")
                    if src is None:
                        src = f.get("addr")
                    if src is None or int(src) != int(addr):
                        continue

                    ts = _to_float_ts(f.get("ts"))
                    if ts < float(min_ts):
                        continue

                    best = f
                except Exception:
                    continue

            if best:
                return best

            time.sleep(0.02)

        return None

    def _request_and_get_rx(dest: int, header: int, payload: bytes = b"", timeout_s: float = 0.7):
        """
        Send ccTalk request and return RX frame dict.
        Use wall-clock time to avoid mixing responses between sequential requests.
        """
        min_ts = time.time()  # <-- vietoj _last_frame_ts()
        controller.device.send(int(dest), int(header), payload)
        return _wait_rx_from_addr(int(dest), min_ts, timeout_s)

    def _rx_data_to_text(rx_frame: dict) -> str:
        dec = (rx_frame or {}).get("decoded") or {}
        hx = dec.get("data_hex") if isinstance(dec, dict) else ""
        hx = (hx or "").strip()
        if not hx:
            return ""
        try:
            return bytes.fromhex(hx).decode("ascii", errors="ignore").strip("\x00").strip()
        except Exception:
            return hx

    def _to_float_ts(v) -> float:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).strip().replace(",", "."))
        except Exception:
            return 0.0

    # ---------- DRIVER JOBS (async) ----------
    # Keep imports inside create_app() to avoid circular imports.
    from app.drivers.jobs import JobManager
    from app.drivers.transport import ControllerTransport

    jobs = JobManager()
    hopper_transport = ControllerTransport(controller=controller, state=STATE, host_address=host_address)

    #------------Debug Frames------------

    @app.get("/api/debug/frames_tail")
    def api_debug_frames_tail():
        n = int(request.args.get("n", 20))
        frames = list(getattr(STATE, "frames", []) or [])
        tail = frames[-n:]

        def as_dict(f):
            if isinstance(f, dict):
                return f
            # FrameRecord -> pabandom ištraukt __dict__ (jei dataclass / normal class)
            d = getattr(f, "__dict__", None)
            if isinstance(d, dict):
                return d
            # fallback: string repr
            return {"repr": repr(f)}

        return jsonify({"ok": True, "count": len(frames), "tail": [as_dict(x) for x in tail]})

    # ---------- UI ----------
    @app.get("/")
    def ui_index():
        return send_from_directory(ui_dir, "index.html")

    @app.get("/pages/<path:path>")
    def ui_pages(path: str):
        return send_from_directory(os.path.join(ui_dir, "pages"), path)

    @app.post("/api/driver/hopper/a8")
    def api_driver_hopper_a8():
        data = request.get_json(silent=True) or {}
        dest = int(data.get("dest", 5))
        dev, _info = autodetect_hopper(hopper_transport, [dest], quiet=True)

        # Tiesioginis A8 request
        rh, raw = dev._tx(dev.HDR_DISPENSE_COUNT, b"", expected_len=None, note="A8_direct")

        out = {
            "ok": True,
            "dest": dest,
            "rx_header": rh,
            "a8_raw_hex": " ".join(f"{b:02x}" for b in raw),
            "a8_u24": (raw[0] | (raw[1] << 8) | (raw[2] << 16)) if len(raw) >= 3 else None,
            "len": len(raw),
        }
        return jsonify(out)

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

    from flask import jsonify
    from app.bootstrap import controller

    @app.route('/api/controller/status')
    def controller_status():
        is_open = controller.sio.is_open
        thread_running = getattr(controller, '_thread_running', False)
        port = controller.port
        baud = controller.baudrate

        return jsonify({
            "port": port,
            "baudrate": baud,
            "is_open": is_open,
            "thread_running": thread_running
        })

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

    @app.post("/api/identify")
    def api_identify():
        data = request.get_json(silent=True) or {}

        try:
            dest = int(data.get("dest"))
        except Exception:
            return jsonify({"ok": False, "error": "dest must be integer"}), 400

        if not STATE.connected:
            return jsonify({"ok": False, "error": STATE.last_error or "Serial disconnected"}), 400

        try:
            rx_poll = _request_and_get_rx(dest, 254, b"", timeout_s=0.6)
            if not rx_poll:
                return jsonify({"ok": True, "dest": dest, "active": False, "identify": {}, "method": "poll"}), 200

            info = {}

            # manufacturer
            rx = _request_and_get_rx(dest, 246, b"", timeout_s=0.8)
            if rx:
                info["manufacturer"] = _rx_data_to_text(rx)

            # category
            rx = _request_and_get_rx(dest, 245, b"", timeout_s=0.8)
            if rx:
                info["category"] = _rx_data_to_text(rx)

            # product
            rx = _request_and_get_rx(dest, 244, b"", timeout_s=0.8)
            if rx:
                info["product_text"] = _rx_data_to_text(rx)

            # serial -> IMPORTANT: keep raw hex so UI always shows something
            # serial (242): keep raw hex + decoded decimal
            rx = _request_and_get_rx(dest, 242, b"", timeout_s=0.8)
            if rx:
                dec = rx.get("decoded") or {}
                if isinstance(dec, dict):
                    hx = (dec.get("data_hex") or "").strip()
                    if hx:
                        info["serial_raw"] = hx  # pvz. "020f1d"
                        try:
                            b = bytes.fromhex(hx)
                            if len(b) == 3:
                                # u24 little-endian -> decimal
                                serial_num = b[0] | (b[1] << 8) | (b[2] << 16)
                                info["serial"] = str(serial_num)  # pvz. "1904386"
                            else:
                                # fallback: if not 3 bytes, decode little-endian anyway
                                info["serial"] = str(int.from_bytes(b, "little", signed=False))
                        except Exception:
                            # worst case: still show raw
                            info["serial"] = hx

            # software rev (241) -> show "major.minor" if 2 bytes
            rx = _request_and_get_rx(dest, 241, b"", timeout_s=0.8)
            if rx:
                dec = rx.get("decoded") or {}
                if isinstance(dec, dict):
                    hx = (dec.get("data_hex") or "").strip()
                    if hx:
                        try:
                            b = bytes.fromhex(hx)
                            if len(b) == 2:
                                info["sw_rev"] = f"{b[0]}.{b[1]}"
                            else:
                                info["sw_rev"] = hx
                        except Exception:
                            info["sw_rev"] = hx

            if info:
                STATE.update_device_identify(dest, info)

            return jsonify({"ok": True, "dest": dest, "active": True, "identify": info, "method": "cctalk_id"}), 200

        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    # ---------- JOBS API ----------
    @app.get("/api/jobs/<job_id>")
    def api_jobs_get(job_id: str):
        job = jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "job not found"}), 404
        return jsonify({"ok": True, "job": jobs.to_dict(job)})

    @app.post("/api/jobs/<job_id>/cancel")
    def api_jobs_cancel(job_id: str):
        ok = jobs.cancel(job_id)
        if not ok:
            return jsonify({"ok": False, "error": "job not found"}), 404
        job = jobs.get(job_id)
        return jsonify({"ok": True, "job": jobs.to_dict(job)})

    # ---------- HOPPER DRIVER API ----------
    @app.post("/api/driver/hopper/identify")
    def api_driver_hopper_identify():
        data = request.get_json(silent=True) or {}
        if data.get("dest") is None:
            return jsonify({"ok": False, "error": "dest is required"}), 400

        dest = int(data["dest"])

        try:
            dev, info = autodetect_hopper(
                hopper_transport,
                [dest],
                quiet=True,
                lock_timeout_s=1.0,
            )

            # NEW: cache identify info for Devices page
            try:
                STATE.update_device_identify(dest, info)
            except Exception:
                pass

            return jsonify({"ok": True, "device_addr": dev.addr, "info": info})

        except DriverTimeout as e:
            return jsonify({"ok": False, "error": "device busy", "detail": str(e)}), 409

        except DriverError as e:
            return jsonify({"ok": False, "error": "identify failed", "detail": str(e)}), 502
    @app.post("/api/driver/hopper/payout_async")
    def api_driver_hopper_payout_async():
        data = request.get_json(silent=True) or {}

        if data.get("dest") is None:
            return jsonify({"ok": False, "error": "dest is required"}), 400

        dest = int(data["dest"])
        coins = int(data.get("coins", 10))
        reset_before = bool(data.get("reset_before_payout", False))  # <-- buvo True
        quiet = bool(data.get("quiet", True))

        job = jobs.create(
            kind="hopper_payout",
            meta={
                "dest": dest,
                "coins": coins,
                "reset_before_payout": reset_before,
            },
        )

        def work(cancelled, update):
            update(0.05, f"autodetect dest={dest}")
            dev, info = autodetect_hopper(hopper_transport, [dest], quiet=quiet)

            if cancelled():
                return {"canceled": True, "stage": "after_autodetect", "info": info}

            update(0.15, f"payout_start vendor={info.get('vendor_guess')}")
            res = dev.payout(coins, reset_before_payout=reset_before)

            update(0.95, "payout_done")
            return {"info": info, "result": res}

        jobs.run_background(job, work)
        return jsonify({"ok": True, "job_id": job.id})

    # ---------- ACCEPTOR DRIVER API ----------

    def fmt_info(info):
        lines = []
        lines.append("")
        lines.append("------ DEVICE INFO ------")
        if info.manufacturer:
            lines.append(f"Manufacturer : {info.manufacturer}")
        if info.product:
            lines.append(f"Product      : {info.product}")
        if info.software:
            lines.append(f"Software     : {info.software}")
        if info.serial_dec:
            lines.append(f"Serial       : {info.serial_dec}")
        lines.append("-------------------------")
        return "\n".join(lines)

    # from app.drivers.devices.coin_acceptor import AlberichiCoinAcceptor

    # @app.route('/api/acceptor')
    # def acceptor_cmd():
    #     # Apsauga: porto check ir aiški žinutė!
    #     if not hasattr(controller, "device") or controller.device is None:
    #         return Response("Coin acceptor not available: serial not connected", status=503)
    #
    #     acceptor = AlberichiCoinAcceptor(acceptor_transport, addr=2)
    #     action = request.args.get("action")
    #
    #     if action == "info":
    #         info = acceptor.read_device_info()
    #         # Gali perdaryti į tau reikalingą tekstą/formatą
    #         return Response(f"\n".join([f"{k}: {v}" for k, v in info.items()]), mimetype="text/plain")
    #
    #     elif action == "status":
    #         # Užfiksuojam print'us ir gražinam tekstą kaip status
    #         from io import StringIO
    #         import sys
    #         oldstdout = sys.stdout
    #         sys.stdout = mystdout = StringIO()
    #         acceptor.read_status()
    #         sys.stdout = oldstdout
    #         return Response(mystdout.getvalue(), mimetype="text/plain")
    #
    #     elif action == "events":
    #         events = acceptor.read_buffered_events()
    #         lines = ["------ COIN EVENTS ------"]
    #         for ev in events:
    #             if ev["coin_code"] == 0 and ev["dir_or_error"] != 0:
    #                 lines.append(f"[ERROR] code={ev['dir_or_error']}")
    #             elif ev["coin_code"] != 0:
    #                 lines.append(f"COIN POS: {ev['coin_code']} CODE: {ev['dir_or_error']}")
    #         return Response("\n".join(lines) if lines else "No events.", mimetype="text/plain")
    #
    #     elif action == "autotest":
    #         info_lines = []
    #         info = acceptor.read_device_info()
    #         info_lines.append("DEVICE INFO:")
    #         info_lines += [f"{k}: {v}" for k, v in info.items()]
    #         from io import StringIO
    #         import sys
    #         oldstdout = sys.stdout
    #         sys.stdout = mystdout = StringIO()
    #         acceptor.read_status()
    #         sys.stdout = oldstdout
    #         events = acceptor.read_buffered_events()
    #         event_lines = []
    #         for ev in events:
    #             if ev["coin_code"] == 0 and ev["dir_or_error"] != 0:
    #                 event_lines.append(f"[ERROR] code={ev['dir_or_error']}")
    #             elif ev["coin_code"] != 0:
    #                 event_lines.append(f"COIN POS: {ev['coin_code']} CODE: {ev['dir_or_error']}")
    #         result = "\n".join(info_lines + [mystdout.getvalue()] + event_lines)
    #         return Response(result, mimetype="text/plain")
    #
    #     else:
    #         return Response("Unknown action", status=400)
            # ---------- RAW SEND ----------
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

        no_wait = bool(data.get("no_wait", True))

        if not STATE.connected:
            return jsonify({"ok": False, "error": STATE.last_error or "Serial disconnected"}), 400

        try:
            if no_wait:
                if hasattr(controller.device, "write_frame"):
                    out = controller.device.write_frame(dest, header, payload)
                elif hasattr(controller.device, "send_no_wait"):
                    out = controller.device.send_no_wait(dest, header, payload)
                else:
                    out = controller.device.send(dest, header, payload)
                return jsonify({"ok": True, "tx": out, "no_wait": True})

            min_ts = _last_frame_ts()
            out = controller.device.send(dest, header, payload)

            got_rx = False
            try:
                if int(header) == 254:
                    rx = _wait_rx_from_addr(dest, min_ts, timeout_s=0.4)
                    got_rx = rx is not None
            except Exception:
                got_rx = False

            return jsonify({"ok": True, "tx": out, "no_wait": False, "got_rx": got_rx})

        except (SerialException, OSError) as e:
            STATE.set_connected(False, str(e))
            try:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG][API] sio.close() CALLED in routes.py:api_send",
                      flush=True)
                controller.sio.close()
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 500
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/scan")
    def api_scan():
        data = request.get_json(silent=True) or {}

        try:
            start = int(data.get("start", 1))
            end = int(data.get("end", 50))
        except Exception:
            return jsonify({"ok": False, "error": "start/end must be integers"}), 400

        # sanity
        start = max(1, start)
        end = min(50, end)
        if end < start:
            return jsonify({"ok": False, "error": "end must be >= start"}), 400

        if not STATE.connected:
            return jsonify({"ok": False, "error": STATE.last_error or "Serial disconnected"}), 400

        found = []
        try:
            for addr in range(start, end + 1):
                # Use wall-clock time to prevent mixing responses
                min_ts = time.time()
                controller.device.send(int(addr), 254, b"")  # poll
                rx = _wait_rx_from_addr(int(addr), min_ts, timeout_s=0.25)
                if not rx:
                    continue

                found.append(int(addr))

            return jsonify({"ok": True, "found": found, "count": len(found)}), 200

        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    return app