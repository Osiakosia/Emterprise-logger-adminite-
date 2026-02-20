import os
from app.api.routes import create_app

if __name__ == "__main__":
    # Default: http://127.0.0.1:5000
    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=True, threaded=True)
