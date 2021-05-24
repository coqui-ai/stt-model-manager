"""Entry point. Run the server and open a browser pointing to it."""
import webbrowser
from threading import Thread

from .server import start_app


def main():
    print("Starting server listening on 0.0.0.0:12345...")
    thread = Thread(target=start_app)
    thread.start()
    webbrowser.open("http://localhost:12345")
    thread.join()


if __name__ == "__main__":
    main()
