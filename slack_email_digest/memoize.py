import functools
import json
import threading


_locks = {}


def memoize1_to_json_file(fn):
    """Memoize a function of one string argument, storing its result in the
    given filename in JSON format.

    Thread-safe, but not multiprocess safe.

    :param fn Filename to memoize to.
    :return decorator to apply
    """

    lock = _locks.setdefault(fn, threading.Lock())

    try:
        with lock:
            cache = json.load(open(fn, 'r'))
    except (IOError, ValueError):
        cache = {}

    def decorator(f):
        @functools.wraps(f)
        def wrapped(arg):
            if arg not in cache:
                res = f(arg)
                with lock:
                    cache[arg] = res
                    json.dump(cache, open(fn, 'w'))

            return cache[arg]

        return wrapped

    return decorator
