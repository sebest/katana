from gevent import monkey; monkey.patch_all()

import os
import re
import errno
import urllib2
import logging
from time import time, strptime, mktime
from datetime import datetime

from . import __version__
from .config import get_config
from .resizer import resize
from .httpwhohas import HttpWhoHas
from .utils import Timer, wlock
from .meta import Meta
from .ipc import IPC


USER_AGENT = 'Katana/%s' % __version__

def date_to_ts(date):
    return mktime(strptime(date, "%a, %d %b %Y %H:%M:%S %Z"))

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
                expires = meta['expires']
                if isinstance(self.config['external_expires'], int):
                    expires = min(self.config['external_expires'], expires)
                if time() > (meta['timestamp'] + expires):
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
                        return cache, self.meta.set(cache, headers)
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
                        return cache, meta
                else:
                    self.logger.debug('%s not found on origin', cache)

            elif self._get_cache(cache):
                self.logger.debug('%s found in cache as %s', origin, cache)
                return cache, meta

        return None, {}

    def get_image_resized(self, image_src, cache, width, height, fit, quality, meta_src):
        if not image_src and not self.config['not_found_as_200']:
            return None, {}

        with wlock(cache) as (write, exists, cache_fd):
            if image_src and write and (not exists or self.meta.get(cache) != meta_src):
                if not resize(image_src, cache, width, height, fit, quality):
                    return None, {}
                self.meta.copy(image_src, cache)
            elif write and not exists:
                if not resize(self.config['not_found_source'], cache, width, height, fit, quality):
                    return None, {}

            if self._get_cache(cache):
                return cache, meta_src

        return None, {}

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
        cache_source = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_source'].format(**values))
        image_src, meta = self.get_file(origin, cache_source)

        cache_resized = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_resized'].format(**values))
        image_resized, meta = self.get_image_resized(image_src, cache_resized, width, height, fit, quality, meta)
        return image_resized, meta

    def proxy(self, values):
        origin = self.config['proxy_origin'].format(**values)
        cache = '%s%s' % (self.config['cache_dir'], self.config['proxy_cache_path'].format(**values))
        image, meta = self.get_file(origin, cache)
        if not image and self.config['not_found_as_200']:
            image = self.config['not_found_source']
        return image, meta

    def app(self, environ, start_response):
        timer = Timer()

        request_method = environ['REQUEST_METHOD']
        if request_method not in ('GET', 'HEAD'):
            start_response('405 Invalid Method', [])
            return []

        client_etag = environ.get('HTTP_IF_NONE_MATCH')
        if environ.get('HTTP_IF_MODIFIED_SINCE'):
            client_modified_ts = date_to_ts(environ['HTTP_IF_MODIFIED_SINCE'])
        else:
            client_modified_ts = None

        self.logger.debug('client check modified etag=%s modified=%s', client_etag, client_modified_ts)

        image_dst = None
        for action in ('resize', 'proxy'):
            regex = self.config['%s_url_re' % action]
            if regex:
                match = re.match(regex, environ['PATH_INFO'])
                if match:
                    image_dst, meta = getattr(self, action)(match.groupdict())
                    if image_dst:
                        headers = [('Content-Type', 'image/jpeg'), ('X-Response-Time', str(timer)),]

                        client_not_modified = False
                        if meta.get('etag'):
                            headers.append(('ETag', meta['etag']))
                            if client_etag:
                                client_not_modified = client_etag == meta['etag']
                        if meta.get('last_modified'):
                            headers.append(('Last-Modified', meta['last_modified']))
                            if not client_not_modified and client_modified_ts:
                                client_not_modified = date_to_ts(meta['last_modified']) <= client_modified_ts

                        expires = meta.get('expires', 0)
                        if isinstance(self.config['external_expires'], int):
                            expires = max(self.config['external_expires'],  expires)
                        if expires:
                            now = time()
                            timestamp_expires = meta.get('timestamp', now) + expires
                            max_age = timestamp_expires - now
                            headers.append(('Expires', datetime.utcfromtimestamp(timestamp_expires).strftime("%a, %d %b %Y %H:%M:%S GMT")))
                            headers.append(('Cache-Control', 'max-age=%d' % max_age))
                        if client_not_modified:
                            start_response('304 Not Modified', headers)
                            return []
                        elif self.config['accel_redirect']:
                            accel_redirect = self.config['accel_redirect_path'] + image_dst[len(self.config['cache_dir']):]
                            if request_method == 'GET':
                                headers.append(('X-Accel-Redirect', accel_redirect))
                            start_response('200 OK', headers)
                            return []
                        else:
                            start_response('200 OK', headers)
                            if request_method == 'HEAD':
                                return []
                            try:
                                image = open(image_dst, 'rb')
                            except IOError as exc:
                                self.logger.error('can\'t open %s: %s', image_dst, exc)
                                return []
                            try:
                                return environ['wsgi.file_wrapper'](image, self.config['chunk_size'])
                            except KeyError:
                                return  iter(lambda: image.read(self.config['chunk_size']), '')
                    break

        start_response('404 Not Found', [('X-Response-Time', str(timer))])
        return []
