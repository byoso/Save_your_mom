import threading
import itertools
import sys

from typing import Callable, Any

def spinner(stop_event):
    for c in itertools.cycle("-\\|/"):
        if stop_event.is_set():
            break
        sys.stdout.write(f"\r{c}")
        sys.stdout.flush()
        stop_event.wait(0.1)
    sys.stdout.write("\r")


def run_with_spinner(long_run_func: Callable[..., Any], *args, **kwargs):
    """Run a long-running function with a spinner in the console.
    Args:
        long_run_func: The long-running function to execute.
        *args: Positional arguments to pass to the long-running function.
        **kwargs: Keyword arguments to pass to the long-running function.
    """
    stop = threading.Event()

    t = threading.Thread(target=spinner, args=(stop,), daemon=True)
    t.start()

    try:
        result = long_run_func(*args, **kwargs)
    finally:
        stop.set()
        t.join()
    return result
