import re
import os
import errno
import logging
from time import time
from shutil import copy
from .config import get_config

__all__ = ['Meta']


class Meta(object):
    """Handles metadata for files in cache.

    Every files in the cache have a file with the same name plus the .META extension.

    The format of the file is as follow:
    MAGIC|TIMESTAMP|EXPIRES|LAST_MODIFIED|ETAG

    * MAGIC is a letter that we change when the format of the file is modified (see META_MAGIC).
    * TIMESTAMP is the unix timestamp representing the creation date of the file.
    * EXPIRES is the number of second until the file should be verified on the origin server.
    * LAST_MODIFIED is the value of the Last-Modified header as returned by the origin server.
    # ETAG is the value of the Etag header as returned by the origin server.

    Example:
    B|1375472452|10|Wed, 23 May 2012 14:03:44 GMT|"100599a17-17db2-4c0b49a681000"
    """

    META_MAGIC = 'C'

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger('katana.meta')

    def get(self, cache):
        """Returns the metadata of a file in the cache.

        Args:
            cache (str): path to the file in the cache.

        Returns:
            A dict with the metadata:
             * timestamp (int)
             * expires (int)
             * last_modified (str)
             * etag (str)

           example:
             {
               'timestamp': 1375472436,
               'expires': 10,
               'last_modified': 'Wed, 23 May 2012 14:03:44 GMT',
               'etag': '"100599a17-17db2-4c0b49a681000"'
             }

           If the file is not found or an error occured accessing it, an empty dict is returned.
        """

        try:
            with open('%s.META' % cache, 'r') as cache_meta:
                splitted = cache_meta.read().split('|')
                if splitted[0] == self.META_MAGIC:
                    magic, timestamp, expires, last_modified, etag = splitted
                    expires = self.config['cache_default_expires'] if self.config['cache_force_expires'] else int(expires)
                    return {
                        'timestamp': int(timestamp),
                        'expires': expires,
                        'last_modified': last_modified,
                        'etag': etag,
                    }
                else:
                    self.logger.error('Meta.get wrong magic [%s] for %s', splitted[0], cache)
                    os.remove('%s.META' % cache)
        except (IOError, OSError) as exc:
            if exc.errno != errno.ENOENT:
                self.logger.error('Meta.get failed for %s: %s', cache, exc)
        return {}

    def set(self, cache, headers):
        """Sets and returns the metadata of a file in the cache.

        Args:
            cache (str): path to the file in the cache.
            headers (dict): a dict of response headers from the request to the origin server.

        Returns:
           A dict with the same format as the get() method.

           If the file is not found or an error occured accessing it, an empty dict is returned.
        """

        try:
            with open('%s.META' % cache, 'w') as cache_meta:
                timestamp = int(time())
                etag = headers.get('etag', '')
                last_modified = headers.get('last-modified', '')
                expires = self.config['cache_default_expires']
                cache_control = headers.get('cache-control', '')
                m = re.match('.*max-age=(\d+).*', cache_control if cache_control else '')
                if m:
                    expires = int(m.group(1))
                cache_meta.write('%s|%s|%s|%s|%s' % (self.META_MAGIC, timestamp, expires, last_modified, etag))
                return {
                    'timestamp': timestamp,
                    'expires': expires,
                    'last_modified': last_modified,
                    'etag': etag,
                }
        except (IOError, OSError) as exc:
            self.logger.error('Meta.set failed for %s: %s', cache, exc)
        return {}

    def copy(self, src, dst):
        try:
            copy('%s.META' % src, '%s.META' % dst)
        except (IOError, OSError) as exc:
            self.logger.error('Meta.copy from %s to %s failed: %s', src, dst, exc)
