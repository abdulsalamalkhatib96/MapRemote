"""Private mitmdump entry point for the bundled interpreter."""
import os
import threading
import time

from mitmproxy.tools.main import mitmdump


def watch_controller(expected_pid):
    """The bundled launcher execs Python, so its parent is the controller.
    Never signal unrelated processes. Exit this engine if it is orphaned.
    """
    while os.getppid() == expected_pid:
        time.sleep(.25)
    os._exit(0)


if __name__ == "__main__":
    controller = os.environ.get("MAPREMOTE_CONTROLLER_PID")
    if controller is not None:
        expected = int(controller)
        if expected <= 1 or os.getppid() != expected:
            raise SystemExit("MapRemote controller is no longer running.")
        threading.Thread(target=watch_controller, args=(expected,), daemon=True).start()
    mitmdump()
