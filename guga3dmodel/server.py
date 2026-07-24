"""guga 3D Desktop Pet -- Three.js edition with skeletal dance."""
import http.server, socketserver, json, os, sys, subprocess, time
from pathlib import Path
import urllib.parse

ROOT = Path(__file__).resolve().parent
PORT = 9875
MODEL = ROOT / "gugugaga_3d" / "zmd_EM_vrm.vrm"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/model.vrm":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(MODEL.stat().st_size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(MODEL, "rb") as f:
                self.wfile.write(f.read())
        else:
            super().do_GET()

def main():
    # Start HTTP server in background
    server = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"Server on http://127.0.0.1:{PORT}")

    # Open Chrome in app mode (frameless window)
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    chrome = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome = p
            break

    if chrome:
        subprocess.Popen([
            chrome,
            f"--app=http://127.0.0.1:{PORT}/guga3d.html",
            "--window-size=420,520",
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
        ])
        print("Chrome launched in app mode")
    else:
        print("Chrome not found. Open this URL in browser:")
        print(f"  http://127.0.0.1:{PORT}/guga3d.html")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    main()