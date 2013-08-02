from gevent import monkey; monkey.patch_all()

import os
import re
import errno
import urllib2
import logging
import logging.config
from time import time
from datetime import datetime

from . import __version__
from .config import get_config
from .resizer import resize
from .httpwhohas import HttpWhoHas
from .utils import Timer, wlock
from .meta import Meta
from .ipc import IPC


USER_AGENT = 'Katana/%s' % __version__


class Server(object):

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger('katana.server')

        self.meta = Meta()
        self.ipc = IPC(self.config['ipc_sock_path'])

        self.hws = HttpWhoHas(proxy=self.config['proxy'], timeout=self.config['origin_timeout'], user_agent=USER_AGENT)
        for name, conf in self.config['origin_mapping'].items():
            self.hws.set_cluster(name, conf['ips'], conf.get('headers'))

    def _get_cache(self, cache):
        if os.path.exists(cache):
            if os.path.getsize(cache):
                self.ipc.push('CACHE-OUT %s' % cache)
                return cache
            else:
                os.unlink(cache)
        return None

    def get_file(self, origin, cache):
        try:
            os.makedirs(os.path.dirname(cache))
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.ENOENT):
                raise

        with wlock(cache) as (write, exists, cache_fd):
            meta = self.meta.get(cache)
            if write and 'expires' in meta:
                # If we have expires info in meta we check if we need to update (write) or not
                if time() > (meta['timestamp'] + meta['expires']):
                    self.logger.debug('%s expired', cache)
                else:
                    write = False
                    self.logger.debug('%s not expired', cache)
            if write:
                self.logger.debug('resolving %s', origin)
                info = self.hws.resolve(origin, etag=meta.get('etag'), last_modified=meta.get('last_modified'))
                if info:
                    url = info['url']
                    if not info['modified']:
                        self.logger.debug('url=%s not modified', url)
                        self.ipc.push('CACHE-OUT %s' % cache)
                        headers = {
                            'etag': meta.get('etag'),
                            'last-modified': meta.get('last_modified'),
                            'cache-control': info['headers'].get('cache-control'),
                            }
                        return cache, self.meta.set(cache, headers), False
                    headers = {'User-Agent': USER_AGENT}
                    if info['host']:
                        headers['Host'] = info['host']
                    try:
                        req = urllib2.Request(url, headers=headers)
                        resp = urllib2.urlopen(req, timeout=self.config['origin_fetch_timeout'])
                    except (urllib2.HTTPError, urllib2.URLError) as exc:
                        self.logger.error('fetching url=%s error: %s', url, exc)
                    except Exception as exc:
                        self.logger.exception('fetching url=%s failed', url)
                    else:
                        meta = self.meta.set(cache, dict(resp.headers))
                        while True:
                            chunk = resp.read(self.config['chunk_size'])
                            if not chunk:
                                break
                            cache_fd.write(chunk)
                        self.logger.debug('fetched %s to %s', url, cache)
                        self.ipc.push('CACHE-IN %s' % cache)
                        return cache, meta, True
                else:
                    self.logger.debug('%s not found on origin', cache)

            elif self._get_cache(cache):
                self.logger.debug('%s found in cache as %s', origin, cache)
                return cache, meta, False

        return None, {}, False

    def get_image_resized(self, image_src, cache, width, height, fit, quality, force_update):
        with wlock(cache) as (write, exists, cache_fd):
            if write and (force_update or not exists):
                if not resize(image_src, cache, width, height, fit, quality):
                    return None

            if self._get_cache(cache):
                return cache

        return None

    def resize(self, values):
        width = values.get('width')
        width = int(width) if width else 0
        width = min(width, self.config['thumb_max_width'])

        height = values.get('height')
        height = int(height) if height else 0
        height = min(height, self.config['thumb_max_height'])

        quality = values.get('quality')
        quality = int(quality) if quality else self.config['thumb_default_quality']
        quality = max(1, min(quality, self.config['thumb_max_quality']))

        fit = True if values.get('fit') else False

        values.update({
            'width': width,
            'height': height,
            'fit': '1' if fit else '0',
            'quality': quality,
            })

        origin = self.config['resize_origin'].format(**values)
        cache = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_source'].format(**values))
        image_src, meta, modified = self.get_file(origin, cache)
        if image_src:
            cache = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_resized'].format(**values))
            return self.get_image_resized(image_src, cache, width, height, fit, quality, modified), meta, modified
        return None, meta, modified

    def proxy(self, values):
        origin = self.config['proxy_origin'].format(**values)
        cache = '%s%s' % (self.config['cache_dir'], self.config['proxy_cache_path'].format(**values))
        return self.get_file(origin, cache)

    def app(self, environ, start_response):
        timer = Timer()

        if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
            start_response('405 Invalid Method', [])
            return []

        image_dst = None
        for action in ('resize', 'proxy'):
            regex = self.config['%s_url_re' % action]
            if regex:
                match = re.match(regex, environ['PATH_INFO'])
                if match:
                    image_dst, meta, modified = getattr(self, action)(match.groupdict())
                    if image_dst:
                        headers = [('Content-Type', 'image/jpeg'), ('X-Response-Time', str(timer)),]
                        if meta.get('etag'):
                            headers.append(('ETag', meta['etag']))
                        elif meta.get('last_modified'):
                            headers.append(('Last-Modified', meta['last_modified']))
                        expires = self.config['external_expires'] or meta.get('expires')
                        if expires and 'timestamp' in meta:
                            timestamp_expires = meta['timestamp'] + expires
                            max_age = timestamp_expires - time()
                            headers.append(('Expires', datetime.utcfromtimestamp(timestamp_expires).strftime("%a, %d %b %Y %H:%M:%S GMT")))
                            headers.append(('Cache-Control', 'max-age=%d' % max_age))
                        if self.config['accel_redirect']:
                            accel_redirect = self.config['accel_redirect_path'] + image_dst[len(self.config['cache_dir']):]
                            headers.append(('X-Accel-Redirect', accel_redirect))
                            start_response('200 OK', headers)
                            return []
                        else:
                            start_response('200 OK', headers)
                            image = open(image_dst, 'rb')
                            try:
                                return environ['wsgi.file_wrapper'](image, self.config['chunk_size'])
                            except KeyError:
                                return  iter(lambda: image.read(self.config['chunk_size']), '')
                    break

        start_response('404 Not Found', [('X-Response-Time', str(timer))])
        return []

