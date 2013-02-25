__version__ = '1.0'

from gevent import monkey; monkey.patch_all()

import os
import re
import errno
import urllib2
import fcntl
import gevent
import logging
import logging.config
from contextlib import contextmanager
from time import time

from resizer import resize
from httpwhohas import HttpWhoHas

USER_AGENT = 'Katana/%s' % __version__

@contextmanager
def wlock(filename):
    try:
        with open(filename, 'rb+') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except IOError as exc:
                    if exc.errno == errno.EAGAIN:
                        gevent.sleep(0.05)
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
                            gevent.sleep(0.05)
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


META_MAGIC = 'A'


class Katana(object):

    def __init__(self):
        self.slog = logging.getLogger('katana.server')
        self.clog = logging.getLogger('katana.cleaner')

        self.config = {
            'proxy': None,
            'accel_redirect': False,
            'accel_redirect_path': '/resized',
            'chunk_size': 16 * 1024,
            'thumb_max_width': 1920,
            'thumb_max_height': 1080,
            'thumb_max_quality': 90,
            'thumb_default_quality': 75,
            'origin_fetch_timeout': 3,
            'origin_timeout': 1,
            'origin_mapping': {
                'localhost': {'ips': ['127.0.0.1'], 'headers': {'Host': 'localhost'}}
            },
            'resize_url_re': None,
            'resize_origin': '',
            'resize_cache_path_source': '',
            'resize_cache_path_resized': '',
            'proxy_url_re': None,
            'proxy_origin': '',
            'proxy_cache_path': '',
            'cache_force_expires': False,
            'cache_default_expires': 600,
            'cache_dir': './data',
            'cache_dir_max_usage': 90,
            'clean_older_than': 24,
            'clean_every': 4,
            'clean_dry': False,
            'logging': {'version': 1},
        }
        configfile = os.environ.get('CONFIG_FILE', 'katana.conf')
        if os.path.exists(configfile):
            execfile(configfile, {}, self.config)

        logging.config.dictConfig(self.config['logging'])

        self.hws = HttpWhoHas(proxy=self.config['proxy'], timeout=self.config['origin_timeout'], user_agent=USER_AGENT)
        for name, conf in self.config['origin_mapping'].items():
            self.hws.set_cluster(name, conf['ips'], conf.get('headers'))

    def get_meta(self, cache):
        try:
            with open('%s.meta' % cache, 'r') as cache_meta:
                splitted = cache_meta.read().split('|')
                if splitted[0] == META_MAGIC:
                    magic, expires, last_modified, etag = splitted
                    return {
                        'expires': int(expires),
                        'last_modified': last_modified,
                        'etag': etag,
                    }
                else:
                    self.slog.error('get_meta wrong magic [%s] for %s', splitted[0], cache)
                    os.remove('%s.meta' % cache)
        except (IOError, OSError) as exc:
            self.slog.error('get_meta failed for %s: %s', cache, exc)
        return {}

    def set_meta(self, cache, headers):
        try:
            with open('%s.meta' % cache, 'w') as cache_meta:
                etag = headers.get('etag', '')
                last_modified = headers.get('last-modified', '')
                expires = self.config['cache_default_expires']
                if not self.config['cache_force_expires']:
                    m = re.match('.*max-age=(\d+).*', headers.get('cache-control', ''))
                    if m:
                        expires = int(m.group(1))
                expires = int(time() + expires)
                cache_meta.write('%s|%s|%s|%s' % (META_MAGIC, expires, last_modified, etag))
                return {
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
                if time() > meta['expires']:
                    write = True
            if write:
                self.slog.debug('write lock: resolving %s', origin)
                info = self.hws.resolve(origin, etag=meta.get('etag'), last_modified=meta.get('last_modified'))
                if info:
                    url = info['url']
                    if not info['modified']:
                        self.slog.debug('url=%s not modified', url)
                        return cache, self.set_meta(cache, info['headers'])
                    headers = {'User-Agent': USER_AGENT}
                    if info['host']:
                        headers['Host'] = info['host']
                    try:
                        req = urllib2.Request(url, headers=headers)
                        resp = urllib2.urlopen(req, timeout=self.config['origin_fetch_timeout'])
                    except urllib2.HTTPError as exc:
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
                        return cache, meta
                else:
                    self.slog.debug('%s not found on origin', cache)

            elif self._get_cache(cache):
                self.slog.debug('read lock: %s found in cache as %s', origin, cache)
                return cache, meta

        return None, {}

    def get_image_resized(self, image_src, cache, width, height, fit, quality, values):
        with wlock(cache) as (write, cache_fd):
            if write:
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
        image_src, meta = self.get_file(origin, cache)
        if image_src:
            os.utime(image_src, None)
            cache = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_resized'].format(**values))
            return self.get_image_resized(image_src, cache, width, height, fit, quality, values)
        return None, meta

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
                    image_dst, meta = getattr(self, action)(match.groupdict())
                    if image_dst:
                        headers = [('Content-Type', 'image/jpeg'), ('X-Response-Time', str(timer)),]
                        if meta.get('etag'):
                            headers.append(('ETag', meta['etag']))
                        if meta.get('last_modified'):
                            headers.append(('Last-Modified', meta['last_modified']))
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

    def clean(self, dry=False):
        try:
            cleaner_lock = open(self.config['cache_dir'] + '/cleaner.lock', 'w')
            fcntl.flock(cleaner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            cleaner_lock.write('%s\n' % os.getpid())
        except (IOError, OSError) as exc:
            if exc.errno == errno.EAGAIN:
                self.clog.debug('cleaner already running')
            else:
                self.clog.exception('error while acquiring cleaner lock')
        else:
            clean_older_than = self.config['clean_older_than']
            self.clog.info('cleaner process starting')
            while True:
                st = os.statvfs(self.config['cache_dir'])
                disk_usage = (st.f_blocks - st.f_bfree) / float(st.f_blocks) * 100
                if disk_usage < self.config['cache_dir_max_usage']:
                    self.clog.info('cleaner process ending')
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
                                    self.clog.debug('%s already locked', filepath)
                                else:
                                    self.clog.exception('error while cleaning %s', filepath)
                            else:
                                if not dry:
                                    os.unlink(filepath)
                                self.clog.info('cleaned %s : %fh old', filepath, age)
                clean_older_than -= 1
                if clean_older_than < 0:
                    self.clog.error('no more file to clean')
                    break
            cleaner_lock.close()

    def start_cleaner(self):
        while True:
            self.clean(self.config['clean_dry'])
            gevent.sleep(self.config['clean_every'] * 3600)

def create_app():
    return Katana().app

def main():
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--clean', help='start the cleaner process', action='store_true')
    group.add_argument('--dump', help='print the configuration', action='store_true')
    group.add_argument('--start', help='start the server', action='store_true')
    args = parser.parse_args()

    if args.dump:
        from pprint import pprint
        pprint(Katana().config)

    elif args.clean:
        try:
            Katana().start_cleaner()
        except KeyboardInterrupt:
            pass

    elif args.start:
        from gevent.pywsgi import WSGIServer
        WSGIServer(('', 8088), Katana().app).serve_forever()

if __name__ == '__main__':
    main()
