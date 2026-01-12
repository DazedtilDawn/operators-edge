#!/usr/bin/env python3
"""
Edge Server v0.1 - Serve Proof Visualizer live at localhost

Usage:
    python3 tools/edge_server.py              # Starts server, opens browser
    python3 tools/edge_server.py --no-open    # Starts server only
    EDGE_PORT=9000 python3 tools/edge_server.py  # Custom port

Bookmark http://localhost:8080/proof_viz.html for instant access.
"""
import http.server
import socketserver
import webbrowser
import os
import sys
import urllib.parse
from pathlib import Path


PORT = int(os.getenv("EDGE_PORT", "8080"))
# Auto-refresh disabled - Story Mode uses client-side state persistence
# Manual refresh (Cmd+R / F5) when needed; playback and node positions preserved


class LiveHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler for live visualization serving."""

    def translate_path(self, path):
        """Translate URL path to filesystem path with virtual directories."""
        # Map /assets/ to tools/proof_viz_assets/ with sanitization
        if path.startswith('/assets/'):
            # Strip query and fragment
            clean_path = path.split('?', 1)[0].split('#', 1)[0]
            # Decode URL encoding
            clean_path = urllib.parse.unquote(clean_path)
            # Remove /assets/ prefix
            clean_path = clean_path.replace('/assets/', '', 1)

            base_dir = (Path(os.getcwd()) / 'tools' / 'proof_viz_assets').resolve()
            full_path = (base_dir / clean_path).resolve()

            # Ensure the resolved path stays within the assets directory
            if not str(full_path).startswith(str(base_dir)):
                return super().translate_path('/404')

            return str(full_path)
        return super().translate_path(path)

    def end_headers(self):
        # Prevent caching so manual refresh always gets latest
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        # Set correct MIME types for JS/CSS
        super().end_headers()

    def guess_type(self, path):
        """Ensure correct MIME types for assets."""
        if path.endswith('.js'):
            return 'application/javascript'
        elif path.endswith('.css'):
            return 'text/css'
        return super().guess_type(path)

    def log_message(self, format, *args):
        # Quieter logging - only show errors
        if args[1].startswith('4') or args[1].startswith('5'):
            super().log_message(format, *args)


def is_port_in_use(port):
    """Check if port is already in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def main():
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Check if already running
    if is_port_in_use(PORT):
        url = f"http://localhost:{PORT}/proof_viz.html"
        print(f"Edge Server already running at {url}")
        if "--no-open" not in sys.argv:
            webbrowser.open(url)
        return

    # Start server
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), LiveHandler) as httpd:
        url = f"http://localhost:{PORT}/proof_viz.html"
        print("=" * 60)
        print("EDGE SERVER - Proof Visualizer Live")
        print("=" * 60)
        print(f"URL: {url}")
        print("Refresh: manual (Cmd+R / F5)")
        print("Press Ctrl+C to stop")
        print("=" * 60)

        # Open browser unless --no-open
        if "--no-open" not in sys.argv:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nEdge Server stopped.")


if __name__ == "__main__":
    main()
