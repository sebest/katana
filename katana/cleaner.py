import os
import errno
import logging
import fcntl
from time import time, sleep

from .config import get_config


class Cleaner(object):

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger('katana.cleaner')

    def clean(self, dry=False):
        try:
            cleaner_lock = open(self.config['cache_dir'] + '/cleaner.lock', 'w')
            fcntl.flock(cleaner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            cleaner_lock.write('%s\n' % os.getpid())
        except (IOError, OSError) as exc:
            if exc.errno == errno.EAGAIN:
                self.logger.debug('cleaner already running')
            else:
                self.logger.exception('error while acquiring cleaner lock')
        else:
            clean_older_than = self.config['clean_older_than']
            self.logger.info('cleaner process starting')
            while True:
                st = os.statvfs(self.config['cache_dir'])
                disk_usage = (st.f_blocks - st.f_bfree) / float(st.f_blocks) * 100
                if disk_usage < self.config['cache_dir_max_usage']:
                    self.logger.info('cleaner process ending')
                    break
                now = time()
                for dirpath, dirnames, filenames in os.walk(self.config['cache_dir']):
                    for filename in filenames:
                        filepath = dirpath + '/' + filename
                        atime = os.path.getatime(filepath)
                        age = (now - atime) / 3600.
                        if age > clean_older_than:
                            lock = open(filepath, 'w')
                            try:
                                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except IOError as exc:
                                if exc.errno == errno.EAGAIN:
                                    self.logger.debug('%s already locked', filepath)
                                else:
                                    self.logger.exception('error while cleaning %s', filepath)
                            else:
                                if not dry:
                                    os.unlink(filepath)
                                self.logger.info('cleaned %s : %fh old', filepath, age)
                clean_older_than -= 1
                if clean_older_than < 0:
                    self.logger.error('no more file to clean')
                    break
            cleaner_lock.close()

    def start(self):
        while True:
            self.clean(self.config['clean_dry'])
            sleep(self.config['clean_every'] * 3600)

