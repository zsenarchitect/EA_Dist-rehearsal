"""Entry point: python -m ai_assistant"""
import argparse
import webbrowser
from .server import run_server


def main():
    parser = argparse.ArgumentParser(description="EnneadTab AI Assistant")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the browser on startup")
    args = parser.parse_args()

    if not args.no_browser:
        import threading
        threading.Timer(1.0, webbrowser.open,
                        args=[f"http://localhost:{args.port}"]).start()

    run_server(args.port)


if __name__ == "__main__":
    main()
