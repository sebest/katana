THUMB_DATA = './data'
THUMB_ACCEL_REDIRECT = '/resized'
THUMB_CHUNK = 16 * 1024
THUMB_MAX_WIDTH = 1920
THUMB_MAX_HEIGHT = 1080
THUMB_MAX_QUALITY = 90
THUMB_DEFAULT_QUALITY = 75
HTTPWHOHAS_TIMEOUT = 1

from httpwhohas import HttpWhoHas

hws = HttpWhoHas(proxy='127.0.0.1:8888', timeout=HTTPWHOHAS_TIMEOUT)
hws.set_cluster('filer-01', ['10.201.6.%d' % i for i in range(1, 7)], {'Host': 'filer-01.int.dmcloud.net'})
hws.set_cluster('filer-02', ['10.201.13.%d' % i for i in range(1, 7)], {'Host': 'filer-02.int.dmcloud.net'})
hws.set_cluster('filer-01.dev', ['10.195.10.%d' % i for i in range(1, 7)], {'Host': 'filer-01.dev.int.dmcloud.net'})

import os
import errno
import urllib2
import fcntl
import gevent
from contextlib import contextmanager

@contextmanager
def wlock(filename):
    try:
        with open(filename, 'r') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except IOError, e:
                    if e.errno == errno.EAGAIN:
                        gevent.sleep(0.05)
                        continue
                    else:
                        raise
                else:
                    yield
                    break
    except IOError, e:
        if e.errno == errno.ENOENT:
            with open(filename, 'wb') as lockw:
                while True:
                    try:
                        fcntl.flock(lockw, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except IOError, e:
                        if e.errno == errno.EAGAIN:
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


def hash_id(user_id, media_id):
    return '%s/%s/%s/%s/%s/%s' % (user_id[7], user_id[6], user_id, media_id[7], media_id[6], media_id)

def get_thumb_src(user_id, media_id):
    hash_path = hash_id(user_id, media_id)
    thumb_src_file_dir = '%s/%s' % (THUMB_DATA, hash_path)
    thumb_src_file = '%s/source.jpeg' % (thumb_src_file_dir)

    try:
        os.makedirs(thumb_src_file_dir)
    except OSError, e:
        if e.errno not in (errno.EEXIST, errno.ENOENT):
            raise

    with wlock(thumb_src_file) as thumb_src_fdw:
        if thumb_src_fdw:
            filename = '/%s/%s.jpeg' % (hash_path, 'jpeg_thumbnail_source')
            info = hws.resolve(filename)
            if info:
                url = info[1]
                headers = {'User-Agent': 'DcRecizer'}
                if info[2]:
                    headers['Host'] = info[2]
                try:
                    req = urllib2.Request(url, headers=headers)
                    req = urllib2.urlopen(req, timeout=3)
                except Exception, e:
                    # TODO improve error logging
                    pass
                else:
                    while True:
                        chunk = req.read(THUMB_CHUNK)
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

from resizer import resize

def get_thumb_resized(user_id, media_id, width, height, fit, quality, accel_redirect=False):
    thumb_src_file = get_thumb_src(user_id, media_id)

    if not thumb_src_file:
        return None

    hash_path = hash_id(user_id, media_id)
    thumb_resized_file_rel = '%s/%dx%d-%s-%02d.jpeg' % (hash_path, width, height, '1' if fit else '0', quality)
    thumb_resized_file = '%s/%s' % (THUMB_DATA, thumb_resized_file_rel)

    with wlock(thumb_resized_file) as lockw:
        if lockw:
            if not resize(thumb_src_file, thumb_resized_file, width, height, fit, quality):
                return None

    if accel_redirect:
        return '%s/%s' % (THUMB_ACCEL_REDIRECT, thumb_resized_file_rel)
    return thumb_resized_file

import re
from time import time

PATH_RE = re.compile('^/(?P<user_id>[0-9a-f]{24})/(?P<media_id>[0-9a-f]{24})/thumb-(?P<width>\d{1,4})?x(?P<height>\d{1,4})?(?P<fit>-f)?(?:-q(?P<quality>\d{1,2}))?.jpeg')

class Timer:
    def __init__(self):
        self.start = time()

    def __str__(self):
        return '%.3f ms' % (time() - self.start)

def app(environ, start_response):
    timer = Timer()

    if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
        start_response('405 Invalid Method', [])
        return ''

    match = PATH_RE.match(environ['PATH_INFO'])
    if not match:
        start_response('404 Not Found', [])
        return ''

    user_id = match.group('user_id')
    media_id = match.group('media_id')

    width = match.group('width')
    if width:
        width = int(width)
    else:
        width = 0
    if width > THUMB_MAX_WIDTH:
        width = THUMB_MAX_WIDTH

    height = match.group('height')
    if height:
        height = int(height)
    else:
        height = 0
    if height > THUMB_MAX_HEIGHT:
        height = THUMB_MAX_HEIGHT

    quality = match.group('quality')
    if quality:
        quality = int(quality)
    else:
        quality = THUMB_DEFAULT_QUALITY
    if quality > THUMB_MAX_QUALITY:
        quality = THUMB_MAX_QUALITY
    elif quality == 0:
        quality = 1

    fit = True if match.group('fit') else False

    thumb_resized = get_thumb_resized(user_id, media_id, width, height, fit, quality, accel_redirect=True)
    if not thumb_resized:
        start_response('404 Not Found', [('X-Response-Time', str(timer))])
        return ''

    start_response('200 OK', [
        ('X-Response-Time', str(timer)),
        ('Content-Type', 'image/jpeg'),
        ('X-Accel-Redirect', thumb_resized),
    ])
    return ''
