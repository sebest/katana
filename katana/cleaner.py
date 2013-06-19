import sqlite3

import os
import logging
import fcntl
import errno
from time import time

from .config import get_config
from .ipc import IPC

CLEANER_LOCK = 'cleaner.lock'

class Cleaner(object):
    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger('katana.cleaner')

        self.cleaning = False

        self.con = sqlite3.connect(self.config['cleaner_db_path'], isolation_level=None)
        self.con.execute('pragma journal_mode=OFF')
        self.con.execute('CREATE TABLE IF NOT EXISTS cache (path text PRIMARY KEY NOT NULL, accessed integer)')

        self.ipc_push = IPC(self.config['ipc_sock_path'], 'push')
        self.ipc_pull = IPC(self.config['ipc_sock_path'], 'pull')

    def init(self):
        '''Walks in cache_dir to initialize the content of the cache.
        '''
        for dirpath, dirnames, filenames in os.walk(self.config['cache_dir']):
            for filename in filenames:
                if filename == CLEANER_LOCK or filename.endswith('.META'):
                    continue
                path = unicode('%s/%s' % (os.path.abspath(dirpath), filename), 'utf8')
                accessed = int(os.path.getatime(path))
                self.log_access(path, accessed)

    def count_items(self):
        '''Returns the number of items in the cache.
        '''
        return self.con.execute('SELECT COUNT(*) FROM cache').fetchone()[0]

    def start(self):
        '''Starts listening on IPC for cache events like CACHE IN/OUT.
        '''
        if not self.count_items():
            self.logger.info('Cleaner database %s is empty, initializing it.', self.config['cleaner_db_path'])
            self.init()
            self.logger.info('Cleaner database %s initialized with %d items.', self.config['cleaner_db_path'], self.count_items())

        last_run = 0
        while True:
            now = time()
            if last_run + self.config['clean_every'] < now:
                self.ipc_push.push('CLEANING START')
                last_run = now

            msg = self.ipc_pull.pull()
            self.logger.debug(msg)
            # TODO: commit every X path
            if msg == 'CLEANING START':
                if not self.cleaning:
                    self.cleaning = True
                    self.clean()
                else:
                    self.logger.warning('already cleaning')
            elif msg == 'CLEANING STOP':
                if self.cleaning:
                    self.cleaning = False
                else:
                    self.logger.warning('not cleaning')
            elif msg.startswith('DELETE'):
                self.delete_path(msg.split()[1], commit=True)
            elif msg.startswith('CACHE-'):
                self.log_access(msg.split()[1], commit=True)

    def delete_path(self, path, commit=True):
        try:
            lock = open(path, 'w')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError as exc:
            if exc.errno == errno.EAGAIN:
                self.logger.debug('%s already locked', path)
            elif exc.errno == errno.ENOENT:
                self.logger.warning('%s was not found', path)
                self.con.execute('DELETE FROM cache where path=?', (path,))
            else:
                self.logger.exception('error while cleaning %s', path)
        else:
            try:
                os.unlink(path + '.META')
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    self.logger.warning('%s was not found', path + '.META')
                else:
                    self.logger.exception('error while cleaning %s', path + '.META')
            try:
                os.unlink(path)
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    self.logger.warning('%s was not found', path)
                else:
                    self.logger.exception('error while cleaning %s', path)
                    return
            self.con.execute('DELETE FROM cache where path=?', (path,))
        if commit:
            self.con.commit()

    def log_access(self, path=None, accessed=None, commit=True):
        '''Log file access in the database.

        If accessed is not provided we use the current timestamp.
        '''
        if path:
            if not accessed:
                accessed = int(time())
            if not self.con.execute('UPDATE cache SET accessed=? WHERE path=?', (accessed, path)).rowcount:
                self.con.execute('INSERT INTO cache VALUES (?, ?)', (path, accessed))
        if commit:
            self.con.commit()

    def clean(self):
        '''Starts the cleaning process, removing the oldest files until the disk usage is below cache_dir_max_usage.
        '''
        self.logger.info('cleaner process starting')
        st = os.statvfs(self.config['cache_dir'])
        disk_usage = (st.f_blocks - st.f_bfree) / float(st.f_blocks) * 100
        if disk_usage > self.config['cache_dir_max_usage']:
            nb_clean = self.config['clean_batch_size']
            query = self.con.execute('SELECT path FROM cache ORDER BY accessed ASC LIMIT ?', (nb_clean,))
            for result in query:
                nb_clean -= 1
                path = str(result[0])
                self.ipc_push.push('DELETE %s' % path)
            self.ipc_push.push('CLEANING STOP')
            if not nb_clean:
                self.ipc_push.push('CLEANING START')
            else:
                self.logger.error('cleaner process ending: no more file to delete')
        elif self.cleaning:
            self.ipc_push.push('CLEANING STOP')
