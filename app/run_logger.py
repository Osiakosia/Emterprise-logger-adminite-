import os
from app.api.routes import create_app

if __name__ == "__main__":
    app = create_app()

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))

    app.run(
        host=host,
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False,  # IMPORTANT: prevents double-start (serial port opens twice)
    )