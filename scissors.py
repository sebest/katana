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

LOGGER = logging.getLogger('scissors')


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


class Scissors(object):

    def __init__(self):
        self.config = {
            'proxy': None,
            'accel_redirect': False,
            'accel_redirect_path': '/resized',
            'thumb_chunk': 16 * 1024,
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
            'url_re': r'/(?P<path>.*)/thumb-(?P<width>\d{1,4})?x(?P<height>\d{1,4})?(?P<fit>-f)?(?:-q(?P<quality>\d{1,2}))?.jpeg',
            'origin_src': '/{path}/jpeg_thumbnail_source.jpeg',
            'cache_src': '/{path}/source.jpeg',
            'cache_dst': '/{path}/{width}x{height}-{fit}-q{quality}.jpeg',
        }
        configfile = os.environ.get('CONFIG_FILE', 'scissors.conf')
        if os.path.exists(configfile):
            execfile(configfile, {}, self.config)

        self.hws = HttpWhoHas(proxy=self.config['proxy'], timeout=self.config['origin_timeout'])
        for name, conf in self.config['origin_mapping'].items():
            self.hws.set_cluster(name, conf['ips'], conf.get('headers'))

        self.url_re = re.compile(self.config['url_re'])
        self.values = {}

    def get_thumb_src(self):
        thumb_src_file = '%s%s' % (self.config['cache_dir'], self.config['cache_src'].format(**self.values))

        try:
            os.makedirs(os.path.dirname(thumb_src_file))
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.ENOENT):
                raise

        with wlock(thumb_src_file) as thumb_src_fdw:
            if thumb_src_fdw:
                filename = self.config['origin_src'].format(**self.values)
                info = self.hws.resolve(filename)
                if info:
                    url = info[1]
                    headers = {'User-Agent': 'DcRecizer'}
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
                            chunk = req.read(self.config['thumb_chunk'])
                            if not chunk:
                                break
                            thumb_src_fdw.write(chunk)

                        return thumb_src_file
            elif os.path.exists(thumb_src_file):
                if os.path.getsize(thumb_src_file):
                    return thumb_src_file
                else:
                    os.unlink(thumb_src_file)

        return None

    def get_thumb_resized(self, width, height, fit, quality):
        thumb_src_file = self.get_thumb_src()

        if not thumb_src_file:
            return None

        thumb_resized_file_rel = self.config['cache_dst'].format(**self.values)
        thumb_resized_file = '%s%s' % (self.config['cache_dir'], thumb_resized_file_rel)

        with wlock(thumb_resized_file) as lockw:
            if lockw:
                if not resize(thumb_src_file, thumb_resized_file, width, height, fit, quality):
                    return None

            if os.path.exists(thumb_resized_file):
                if os.path.getsize(thumb_resized_file):
                    if self.config['accel_redirect']:
                        return '%s%s' % (self.config['accel_redirect_path'], thumb_resized_file_rel)
                    return thumb_resized_file
                else:
                    os.unlink(thumb_resized_file)

        return None

    def app(self, environ, start_response):
        timer = Timer()

        if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
            start_response('405 Invalid Method', [])
            return ''

        match = self.url_re.match(environ['PATH_INFO'])
        if not match:
            start_response('404 Not Found', [])
            return ''

        self.values = match.groupdict()

        width = match.group('width')
        if width:
            width = int(width)
        else:
            width = 0
        if width > self.config['thumb_max_width']:
            width = self.config['thumb_max_width']

        height = match.group('height')
        if height:
            height = int(height)
        else:
            height = 0
        if height > self.config['thumb_max_height']:
            height = self.config['thumb_max_height']

        quality = match.group('quality')
        if quality:
            quality = int(quality)
        else:
            quality = self.config['thumb_default_quality']
        if quality > self.config['thumb_max_quality']:
            quality = self.config['thumb_max_quality']
        elif quality == 0:
            quality = 1

        fit = True if match.group('fit') else False

        if width == height == 0:
            start_response('404 Invalid Dimensions', [('X-Response-Time', str(timer))])
            return ''

        self.values.update({
            'width': width,
            'height': height,
            'fit': '1' if fit else '0',
            'quality': quality,
            })

        thumb_resized = self.get_thumb_resized(width, height, fit, quality)
        if not thumb_resized:
            start_response('404 Not Found', [('X-Response-Time', str(timer))])
            return ''

        headers = [('X-Response-Time', str(timer)), ('Content-Type', 'image/jpeg'),]
        if self.config['accel_redirect']:
            headers.append(('X-Accel-Redirect', thumb_resized))
            start_response('200 OK', headers)
            return ''
        else:
            start_response('200 OK', headers)
            return environ['wsgi.file_wrapper'](open(thumb_resized, 'rb'))

def app():
    return Scissors().app
