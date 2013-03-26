META_MAGIC = 'B'

import re
import os
import errno
import logging
from time import time
from .config import get_config


class Meta(object):

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger('katana.meta')

    def get(self, cache):
        try:
            with open('%s.meta' % cache, 'r') as cache_meta:
                splitted = cache_meta.read().split('|')
                if splitted[0] == META_MAGIC:
                    magic, timestamp, expires, last_modified, etag = splitted
                    return {
                        'timestamp': int(timestamp),
                        'expires': int(expires),
                        'last_modified': last_modified,
                        'etag': etag,
                    }
                else:
                    self.logger.error('Meta.get wrong magic [%s] for %s', splitted[0], cache)
                    os.remove('%s.meta' % cache)
        except (IOError, OSError) as exc:
            if exc.errno != errno.ENOENT:
                self.logger.error('Meta.get failed for %s: %s', cache, exc)
        return {}

    def set(self, cache, headers):
        try:
            with open('%s.meta' % cache, 'w') as cache_meta:
                timestamp = int(time())
                etag = headers.get('etag', '')
                last_modified = headers.get('last-modified', '')
                expires = self.config['cache_default_expires']
                if not self.config['cache_force_expires']:
                    m = re.match('.*max-age=(\d+).*', headers.get('cache-control', ''))
                    if m:
                        expires = int(m.group(1))
                cache_meta.write('%s|%s|%s|%s|%s' % (META_MAGIC, timestamp, expires, last_modified, etag))
                return {
                    'timestamp': timestamp,
                    'expires': expires,
                    'last_modified': last_modified,
                    'etag': etag,
                }
        except (IOError, OSError) as exc:
            self.logger.error('Meta.set failed for %s: %s', cache, exc)
        return {}
