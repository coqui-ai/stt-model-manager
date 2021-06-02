"""Entry point. Run the server and open a browser pointing to it."""
import webbrowser
from threading import Thread

from .server import get_server_hostport, start_app


def main():
    thread = Thread(target=start_app, daemon=True)
    thread.start()
    host, port = get_server_hostport()
    addr = f"http://{host}:{port}"
    print(f"Started server listening on {addr} ...")
    webbrowser.open(addr)
    thread.join()


if __name__ == "__main__":
    main()
