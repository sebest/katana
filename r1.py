THUMB_DATA = './data'
THUMB_ACCEL_REDIRECT = '/resized'
THUMB_CHUNK = 16 * 1024
HTTPWHOHAS_TIMEOUT = 1

from httpwhohas import HttpWhoHas

hws = HttpWhoHas(proxy='127.0.0.1:8888', timeout=HTTPWHOHAS_TIMEOUT)
hws.set_cluster('filer-01', ['10.201.6.%d' % i for i in range(1, 7)], {'Host': 'filer-01.int.dmcloud.net'})
hws.set_cluster('filer-02', ['10.201.13.%d' % i for i in range(1, 7)], {'Host': 'filer-02.int.dmcloud.net'})
hws.set_cluster('filer-01.dev', ['10.195.10.%d' % i for i in range(1, 7)], {'Host': 'filer-01.dev.int.dmcloud.net'})

import os
import urllib2

from contextlib import contextmanager
import fcntl

@contextmanager
def lock(filename):
    lockfilename = filename + '.lock'
    lockfile = open(lockfilename, 'w')
    print lockfile.fileno()
    print '%d waiting for lock' % os.getpid()
    fcntl.flock(lockfile, fcntl.LOCK_EX)
    print '%d lock acquired' % os.getpid()
    yield
    #try:
    #    os.remove(lockfilename)
    #    print '%d file deleted' % os.getpid()
    #except OSError:
    #    print '%d lock not found' % os.getpid()
    fcntl.flock(lockfile, fcntl.LOCK_UN)
    print '%d lock released' % os.getpid()

def hash_id(user_id, media_id):
    return '%s/%s/%s/%s/%s/%s' % (user_id[7], user_id[6], user_id, media_id[7], media_id[6], media_id)

def get_thumb_src(user_id, media_id):
    hash_path = hash_id(user_id, media_id)
    thumb_src_file = '%s/%s/source.jpeg' % (THUMB_DATA, hash_path)

    if not os.path.exists(thumb_src_file):
        thumb_src_file_dir = os.path.dirname(thumb_src_file)
        if not os.path.exists(thumb_src_file_dir):
            try:
                os.makedirs(thumb_src_file_dir)
            except OSError:
                pass

        with lock(thumb_src_file):
            filename = '/%s/%s.jpeg' % (hash_path, 'jpeg_thumbnail_source')
            info = hws.resolve(filename)
            if not info:
                return None
            url = info[1]
            headers = {'User-Agent': 'DcRecizer'}
            if info[2]:
                headers['Host'] = info[2]
            try:
                req = urllib2.Request(url, headers=headers)
                req = urllib2.urlopen(req)
            except Exception, e:
                return None
            with open(thumb_src_file, 'wb') as f:
                while True:
                    chunk = req.read(THUMB_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)

    return thumb_src_file

import PIL
from PIL import Image, ImageOps

def resize_pil(src, dst, width, height, fit=True, quality=75):
    img = Image.open(src)
    if fit:
        img = ImageOps.fit(img, (width, height), Image.ANTIALIAS)
    else:
        hpercent = height / float(img.size[1])
        wsize = int(float(img.size[0]) * float(hpercent))
        img = img.resize((wsize, height), Image.ANTIALIAS)
    img.save(dst, quality=quality)

def get_thumb_resized(user_id, media_id, width, height, accel_redirect=False):
    thumb_src_file = get_thumb_src(user_id, media_id)

    if not thumb_src_file:
        return None

    hash_path = hash_id(user_id, media_id)
    thumb_resized_file_rel = '%s/%dx%d.jpeg' % (hash_path, width, height)
    thumb_resized_file = '%s/%s' % (THUMB_DATA, thumb_resized_file_rel)

    if not os.path.exists(thumb_resized_file):
        with lock(thumb_resized_file):
            resize_pil(thumb_src_file, thumb_resized_file, width, height)

    if accel_redirect:
        return '%s/%s' % (THUMB_ACCEL_REDIRECT, thumb_resized_file_rel)
    return thumb_resized_file

import re
from time import time

PATH_RE = re.compile('^/(?P<user_id>[0-9a-f]{24})/(?P<media_id>[0-9a-f]{24})/thumb-(?P<width>\d{1,4})x(?P<height>\d{1,4}).jpeg')

def app(environ, start_response):
    start = time()
    if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
        start_response('405 Invalid Method', [])
        return ''

    match = PATH_RE.match(environ['PATH_INFO'])
    if not match:
        start_response('404 Not Found', [])
        return ''

    user_id = match.group('user_id')
    media_id = match.group('media_id')
    width = int(match.group('width'))
    height = int(match.group('height'))
    thumb_resized = get_thumb_resized(user_id, media_id, width, height, accel_redirect=True)
    if not thumb_resized:
        timing = '%.3f ms' % (time() - start)
        print timing
        start_response('404 Not Found', [('X-Response-Time', timing)])
        return ''

    timing = '%.3f ms' % (time() - start)
    print timing
    start_response('200 OK', [
        ('X-Response-Time', timing),
        ('Content-Type', 'image/jpeg'),
        ('X-Accel-Redirect', thumb_resized),
    ])
    return ''
