import os
import errno
import fcntl
from contextlib import contextmanager
from time import time, sleep

@contextmanager
def wlock(filename):
    try:
        with open(filename, 'rb+') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except IOError as exc:
                    if exc.errno == errno.EAGAIN:
                        sleep(0.05)
                        continue
                    else:
                        raise
                else:
                    yield False, lock
                    break
    except IOError as exc:
        if exc.errno == errno.ENOENT:
            with open(filename, 'wb') as lock:
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except IOError as exc:
                        if exc.errno == errno.EAGAIN:
                            sleep(0.05)
                            continue
                        else:
                            raise
                    else:
                        yield True, lock

                        if os.path.exists(filename):
                            if not lock.closed:
                                lock.seek(0, 2)
                                if not lock.tell():
                                    os.unlink(filename)
                            elif not os.path.getsize(filename):
                                os.unlink(filename)
                        break
        else:
            raise


class Timer:
    def __init__(self):
        self.start = time()

    def __str__(self):
        return '%.3f ms' % ((time() - self.start) * 1000)
