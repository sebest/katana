__version__ = '1.0'

import os
import re
import errno
import urllib2
import fcntl
import gevent
import logging
from contextlib import contextmanager
from time import time

from resizer import resize
from httpwhohas import HttpWhoHas

LOGGER = logging.getLogger('katana')

USER_AGENT = 'Katana/%s' % __version__

@contextmanager
def wlock(filename):
    try:
        with open(filename, 'r') as lock:
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
                    yield
                    break
    except IOError as exc:
        if exc.errno == errno.ENOENT:
            with open(filename, 'wb') as lockw:
                while True:
                    try:
                        fcntl.flock(lockw, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except IOError as exc:
                        if exc.errno == errno.EAGAIN:
                            gevent.sleep(0.05)
                            continue
                        else:
                            raise
                    else:
                        yield lockw

                        if os.path.exists(filename):
                            if not lockw.closed:
                                lockw.seek(0, 2)
                                if not lockw.tell():
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
        return '%.3f ms' % (time() - self.start)


class Katana(object):

    def __init__(self):
        self.config = {
            'proxy': None,
            'accel_redirect': False,
            'accel_redirect_path': '/resized',
            'chunk_size': 16 * 1024,
            'thumb_max_width': 1920,
            'thumb_max_height': 1080,
            'thumb_max_quality': 90,
            'thumb_default_quality': 75,
            'origin_fetch_timeout': 1,
            'origin_timeout': 1,
            'origin_mapping': {
                'localhost': {'ips': ['127.0.0.1'], 'headers': {'Host': 'localhost'}}
            },
            'cache_dir': './data',
            'resize_url_re': None,
            'resize_origin': '',
            'resize_cache_path_source': '',
            'resize_cache_path_resized': '',
            'proxy_url_re': None,
            'proxy_origin': '',
            'proxy_cache_path': '',
        }
        configfile = os.environ.get('CONFIG_FILE', 'katana.conf')
        if os.path.exists(configfile):
            execfile(configfile, {}, self.config)

        self.hws = HttpWhoHas(proxy=self.config['proxy'], timeout=self.config['origin_timeout'], user_agent=USER_AGENT)
        for name, conf in self.config['origin_mapping'].items():
            self.hws.set_cluster(name, conf['ips'], conf.get('headers'))

        if self.config['resize_url_re']:
            self.resize_url_re = re.compile(self.config['resize_url_re'])
        else:
            self.resize_url_re = None
        if self.config['proxy_url_re']:
            self.proxy_url_re = re.compile(self.config['proxy_url_re'])
        else:
            self.proxy_url_re = None

    def get_file(self, origin, cache):
        try:
            os.makedirs(os.path.dirname(cache))
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.ENOENT):
                raise

        with wlock(cache) as cache_fdw:
            if cache_fdw:
                info = self.hws.resolve(origin)
                if info:
                    url = info[1]
                    headers = {'User-Agent': USER_AGENT}
                    if info[2]:
                        headers['Host'] = info[2]
                    try:
                        req = urllib2.Request(url, headers=headers)
                        req = urllib2.urlopen(req, timeout=self.config['origin_fetch_timeout'])
                    except Exception as exc:
                        # TODO improve error logging
                        pass
                    else:
                        while True:
                            chunk = req.read(self.config['chunk_size'])
                            if not chunk:
                                break
                            cache_fdw.write(chunk)

                        return cache
            elif os.path.exists(cache):
                if os.path.getsize(cache):
                    return cache
                else:
                    os.unlink(cache)

        return None

    def get_image_resized(self, image_src, cache, width, height, fit, quality, values):
        with wlock(cache) as lockw:
            if lockw:
                if not resize(image_src, cache, width, height, fit, quality):
                    return None

            if os.path.exists(cache):
                if os.path.getsize(cache):
                    return cache
                else:
                    os.unlink(cache)

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
            start_response('404 Invalid Dimensions', [('X-Response-Time', str(timer))])
            return ''

        values.update({
            'width': width,
            'height': height,
            'fit': '1' if fit else '0',
            'quality': quality,
            })

        origin = self.config['resize_origin'].format(**values)
        cache = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_source'].format(**values))
        image_src = self.get_file(origin, cache)
        if image_src:
            cache = '%s%s' % (self.config['cache_dir'], self.config['resize_cache_path_resized'].format(**values))
            return self.get_image_resized(image_src, cache, width, height, fit, quality, values)
        return None

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
        match = None
        if self.resize_url_re:
            match = self.resize_url_re.match(environ['PATH_INFO'])
            if match:
                values = match.groupdict()
                image_dst = self.resize(value)

        if not match and self.proxy_url_re:
            match = self.proxy_url_re.match(environ['PATH_INFO'])
            if match:
                values = match.groupdict()
                image_dst = self.proxy(values)

        if image_dst:
            headers = [('Content-Type', 'image/jpeg'), ('X-Response-Time', str(timer)),]
            if self.config['accel_redirect']:
                accel_redirect = self.config['accel_redirect_path'] + image_dst[len(self.config['cache_dir']):]
                headers.append(('X-Accel-Redirect', accel_redirect))
                start_response('200 OK', headers)
                return []
            else:
                start_response('200 OK', headers)
                return environ['wsgi.file_wrapper'](open(image_dst, 'rb'))

        start_response('404 Not Found', [('X-Response-Time', str(timer))])
        return ''

app = Katana().app
