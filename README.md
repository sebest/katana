Katana
======

*Katana* is a HTTP caching proxy with dynamic image resizing capabiliy.

Features
--------

- HTTP proxying
- HTTP caching with file cleaner
- Image resizing and caching
- Full support of HTTP caching Headers (Etag, Cache-Control, If-Modified-Since, etc)
- Rewriting of URLs and path in the cache
- HttpWhoHas
- Configurable logging and debugging
- X-accel feature to put nginx in front of Katana
- Can return (resized) image on 404 not found
- Can work with Gunicorn or standalone

Configuration
-------------

### General

    'logging': {'version': 1},

### Cache

    'cache_dir': './data',
    'cache_dir_max_usage': 90,
    'clean_batch_size': 100,
    'clean_every': 60,
    'ipc_sock_path': '/tmp/katana.sock',
    'cleaner_db_path': '/tmp/katana_cleaner.db',
    'not_found_as_200': False,
    'not_found_source': './404.jpeg',

### Proxy

    'proxy_url_re': None,
    'proxy_origin': '',
    'proxy_cache_path': '',

### Thumbnail resizer

    'resize_url_re': None,
    'resize_origin': '',
    'resize_cache_path_source': '',
    'resize_cache_path_resized': '',

    'thumb_max_width': 1920,
    'thumb_max_height': 1080,
    'thumb_max_quality': 90,
    'thumb_default_quality': 75,

### Expire Headers

    'external_expires': 600,
    'cache_force_expires': False,
    'cache_default_expires': 300,

### Origin fetcher

    'proxy': None,
    'chunk_size': 16 * 1024,
    'origin_fetch_timeout': 3,
    'origin_timeout': 1,
    'origin_mapping': {
        'localhost': {'ips': ['127.0.0.1'], 'headers': {'Host': 'localhost'}}
    },

### Nginx specific

    'accel_redirect': False,
    'accel_redirect_path': '/resized',
