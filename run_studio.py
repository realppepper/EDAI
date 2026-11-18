"""
Launcher for the Autonomous Analog Circuit Design Web Studio.
Starts the local HTTP server and opens the interactive web studio in your browser.
"""

import argparse
import logging
import webbrowser

from ai_analog_designer.web_studio import StudioServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    parser = argparse.ArgumentParser(description="Start the Autonomous Analog Circuit Design Interactive Web Studio.")
    parser.add_argument("--port", type=int, default=8080, help="Local port to bind server (default: 8080).")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1).")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically launch web browser.")
    args = parser.parse_args()

    server = StudioServer(port=args.port, host=args.host)
    url = server.start(blocking=False)

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    print(f"Server is listening at {url}. Press Ctrl+C to terminate.")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStudio server stopped.")

if __name__ == "__main__":
    main()
