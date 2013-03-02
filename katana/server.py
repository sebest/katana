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

USER_AGENT = 'Katana/%s' % __version__
META_MAGIC = 'B'

class Server(object):

    def __init__(self):
        self.config = get_config()
        logging.config.dictConfig(self.config['logging'])
        self.slog = logging.getLogger('katana.server')

        if self.config['cache_force_expires']:
            self.config['external_expires'] = max(self.config['external_expires'], self.config['cache_default_expires'])

        self.hws = HttpWhoHas(proxy=self.config['proxy'], timeout=self.config['origin_timeout'], user_agent=USER_AGENT)
        for name, conf in self.config['origin_mapping'].items():
            self.hws.set_cluster(name, conf['ips'], conf.get('headers'))

    def get_meta(self, cache):
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
                    self.slog.error('get_meta wrong magic [%s] for %s', splitted[0], cache)
                    os.remove('%s.meta' % cache)
        except (IOError, OSError) as exc:
            if exc.errno != errno.ENOENT:
                self.slog.error('get_meta failed for %s: %s', cache, exc)
        return {}

    def set_meta(self, cache, headers):
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
            self.slog.error('set_meta failed for %s: %s', cache, exc)
        return {}

    def _get_cache(self, cache):
        if os.path.exists(cache):
            if os.path.getsize(cache):
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

        with wlock(cache) as (write, cache_fd):
            meta = self.get_meta(cache)
            if 'expires' in meta:
                if time() > (meta['timestamp'] + meta['expires']):
                    write = True
            if write or not meta:
                self.slog.debug('write lock: resolving %s', origin)
                info = self.hws.resolve(origin, etag=meta.get('etag'), last_modified=meta.get('last_modified'))
                if info:
                    url = info['url']
                    if not info['modified']:
                        self.slog.debug('url=%s not modified', url)
                        return cache, self.set_meta(cache, info['headers']), False
                    headers = {'User-Agent': USER_AGENT}
                    if info['host']:
                        headers['Host'] = info['host']
                    try:
                        req = urllib2.Request(url, headers=headers)
                        resp = urllib2.urlopen(req, timeout=self.config['origin_fetch_timeout'])
                    except (urllib2.HTTPError, urllib2.URLError) as exc:
                        self.slog.error('fetching url=%s error: %s', url, exc)
                    except Exception as exc:
                        self.slog.exception('fetching url=%s failed', url)
                    else:
                        meta = self.set_meta(cache, dict(resp.headers))
                        while True:
                            chunk = resp.read(self.config['chunk_size'])
                            if not chunk:
                                break
                            cache_fd.write(chunk)
                        self.slog.debug('fetched %s to %s', url, cache)
                        return cache, meta, True
                else:
                    self.slog.debug('%s not found on origin', cache)

            elif self._get_cache(cache):
                self.slog.debug('read lock: %s found in cache as %s', origin, cache)
                return cache, meta, False

        return None, {}, False

    def get_image_resized(self, image_src, cache, width, height, fit, quality, force_update):
        with wlock(cache) as (write, cache_fd):
            if write or force_update:
                if not resize(image_src, cache, width, height, fit, quality):
                    return None

            if self._get_cache(cache):
                return cache

        return None

    def resize(self, values):
        width = values.get('width')
        if width:
            width = int(width)
        else:
            width = 0
        if width > self.config['thumb_max_width']:
            width = self.config['thumb_max_width']

        height = values.get('height')
        if height:
            height = int(height)
        else:
            height = 0
        if height > self.config['thumb_max_height']:
            height = self.config['thumb_max_height']

        quality = values.get('quality')
        if quality:
            quality = int(quality)
        else:
            quality = self.config['thumb_default_quality']
        if quality > self.config['thumb_max_quality']:
            quality = self.config['thumb_max_quality']
        elif quality == 0:
            quality = 1

        fit = True if values.get('fit') else False

        if width == height == 0:
            return None

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
                        if expires:
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
                            image = open(image_dst, 'rb')
                            try:
                                start_response('200 OK', headers)
                                return environ['wsgi.file_wrapper'](image, self.config['chunk_size'])
                            except KeyError:
                                start_response('200 OK', headers)
                                return  iter(lambda: image.read(self.config['chunk_size']), '')
                    break

        start_response('404 Not Found', [('X-Response-Time', str(timer))])
        return ''

def create_app():
    return Server().app
