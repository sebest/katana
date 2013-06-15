import os
import errno
import fcntl
from contextlib import contextmanager
from time import time, sleep

@contextmanager
def wlock(filename, retry_interval=0.05):
    # returns: write, exists, fd
    try:
        with open(filename, 'rb+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError as exc:
                if exc.errno == errno.EAGAIN:
                    while True:
                        try:
                            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        except IOError as exc:
                            if exc.errno == errno.EAGAIN:
                                sleep(retry_interval)
                                continue
                            else:
                                raise
                        else:
                            yield False, True, lock
                            break
                else:
                    raise
            else:
                yield True, True, lock
    except IOError as exc:
        if exc.errno == errno.ENOENT:
            with open(filename, 'wb') as lock:
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except IOError as exc:
                        if exc.errno == errno.EAGAIN:
                            sleep(retry_interval)
                            continue
                        else:
                            raise
                    else:
                        yield True, False, lock

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
