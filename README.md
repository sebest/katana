Katana
======

*Katana* is a HTTP caching proxy with dynamic image resizing capabilities.
 
It has been used on production for more than 2 years on moderate traffic websites and can scale linearly by adding more instances.

Even though it can serve traffic directly to clients, a really common setup is to use it as the origin of CDN like Akamai, Edgecast or Cloudfront.

Features
--------

- HTTP proxying
- HTTP caching with file cleaner
- Image resizing and caching
- Image format conversion: jpeg, webp or png.
- Full support of HTTP caching Headers (Etag, Cache-Control, If-Modified-Since, etc)
- URL rewriting
- HttpWhoHas: using HEAD requests on backends server to locate a file
- Configurable logging and debugging
- X-accel feature to put nginx in front of Katana
- Can return (resized) image for 404 not found
- Can work with Gunicorn or standalone using gevent wsgi server

Installation
------------

### Requirements

Katana depends on:
 * [PyZMQ](https://github.com/zeromq/pyzmq)
 * [Pillow](http://python-pillow.github.io/)
 * [gevent](https://github.com/gevent/gevent)

Make sure that `Pillow` has all its dependencies installed if you want support for jpeg or webp image formats.

On OsX you can do this with:
```
$ brew install libjpeg
$ brew install webp
```

For PyZMQ, make sure that the PyZMQ bindings match the ZeroMQ library version.

Tested with versions:
 * zeromq 4.0.5
 * pyzmq 14.6.0
 * webp 0.4.3
 * libjpeg 8d
 * Pillow 2.8.1g
 * gevent 1.0.1

### Install from source with a virtualenv

```
$ sudo pip install virtualenv
$ mkdir katana
$ cd katana/
$ virtualenv venv
$ git clone git@github.com:sebest/katana.git
$ source venv/bin/activate
$ cd katana/
$ python setup.py install
```

Quickstart
----------

Create a directory for the cache:
```
$ mkdir data
```

Use the `katana-simple.conf.sample` as a default configuration:
```
$ cp katana-simple.conf.sample katana.conf
```

This sample configuration file is proxying images hosted on www.google.com, we will resize the google logo.

Test the config file by dumping and checking that the output matches the content of katana.conf
```
$ katana --dump
```

Start the cache cleaner:
```
$ katana --cleaner &
```

Start the web server:
```
$ katana &
```

Do a request on the source image:
```
$ curl -I http://127.0.0.1:8080/images/srpr/logo4w.png
```

Do a request to resize the previous image:
```
$ curl -I http://127.0.0.1:8080/images/srpr/logo4w.png/resize-300x.webp
```

Configuration
-------------

The configuration file is a standard python file.

Two sample configuration files are provide:
 * `katana-simple.conf.sample`: the most basic configuration file to start with.
 * `katana-complex.conf.sample`: a more complex example showing off more features.

### Configuration parameters

#### origins

`origins` defines the origins from where the proxy will fetch the images.

You can define multiple origins that you can later reference in your `routing`.

Each origin can contain multiple clusters, a cluster is a list of servers having the same files.

Each cluster contains different files.

The proxy is able to locate which cluster is hosting a specific file.

Each node in a cluster does not have to be perfectly synced as the proxy will try up to 3 nodes in parallel.

So even if a node is down it does not affect the service.

It is highly recommended that every node in a cluster contains the same files at a certain point in time but it is not required for the sync process to be realtime.

Nodes in a cluster provide redundancy and higher throughput.

Clusters provide horizontal storage scalability.

The most simple setting is to have one origin with one cluster of one node.

It is recommended to use IP addresses to define nodes in a cluster to avoid DNS resolution, you can pass HTTP headers if you are using name based virtualhosts.

*example with clusters*:
```python
origins = {
    'origin_1': {
        'filer-01': {
            'ips': ['10.201.13.1', '10.201.13.2', '10.201.13.3'],
        },
        'filer-02': {
            'ips': ['10.195.24.%d:8079' % i for i in range(1, 20)],
            'headers': {
                'Host': 'filer-02.domain.com',
            }
        },
        'filer-03': {
            'ips': ['10.195.25.%d:8079' % i for i in range(1, 9)],
        }
    }
}
```

This example defines one origin with 3 clusters with multiple nodes.

We take advantage of the Python syntax to create a list of the nodes.

*example with amazon S3 and a custom origin*:
```python
origins = {
    's3': {
        's3': {
            'ips': ['s3.amazonaws.com'],
        },
    },
    'dm': {
        'dm': {
            'ips': ['s1.dmcdn.net'],
        },
    },
}
```

This example defines 2 origins with 1 cluster of one node.


*default*:
```python
origins = {
    'default': {
        'localhost': {
            'ips': ['127.0.0.1'],
            'headers': {
                'Host': 'localhost'
            }
        }
    }
}
```

#### routing

`routing` is the most important parameter as it allows you to define how you will route the requests hitting the proxy.

`routing` is a `list` of `dict`, the routes will be tried in list order, and the first route that match a regex will be choosen.

Each `dict` can contains up to actions as key: `resize` and/or `proxy`, the value of the `action` key is a dict of parameters.

Here is the default value to give you an idea of the structure.

*default*:
```python
routing = [{
    'proxy': {
        'url_re': None,
        'origin_tmpl': '',
        'cache_path': '',
        'origin': 'default',
    },
    'resize': {
        'url_re': None,
        'origin_tmpl': '',
        'cache_path_source': '',
        'cache_path_resized': '',
        'origin': 'default',
    }
}]
```
**Actions**

 * `proxy` is used if you want to serve the image as is with no processing, only proxy/caching. Proxy is usefull if you want to give access to the source image.
 * `resize` is used if you want to be able to resize the image.

**Proxy parameters**

 * `url_re`: regex with capturing named groups, see python documentation [here](https://docs.python.org/2/library/re.html).
 * `origin_tmpl`: a template string to rewrite the path of the image on the origin using the caputred named groups from `url_re`.
 * `origin`: name of the origin to use (see the `origins` parameter).
 * `cache_path`: a template string to store the image on disk in the `cache_dir`.

**Resize parameters**

 * `url_re`: regex with capturing named groups, see python documentation [here](https://docs.python.org/2/library/re.html).
 * `origin_tmpl`: a template string to rewrite the path of the image on the origin using the caputred named groups from `url_re`.
 * `origin`: name of the origin to use (see the `origins` parameter).
 * `cache_path_source`: a template string to store the source image on disk in the  `cache_dir`.
 * `cache_path_resized`: a template string to store the resized image on disk in the `cache_dir`.

Note that you could and should use the same value for `cache_path` and `cache_path_source` if you use both `proxy` and `resize` actions to share the cached source image.

#### logging

`logging` uses the python [DictConfig](https://docs.python.org/2/library/logging.config.html#logging.config.dictConfig
) syntax.

*default*: `{'version': 1},`

*example*:
```python
logging = {
    'version': 1,
    'loggers': {
        'katana.server': {
            'handlers': ['file_server', 'console'],
            'level': 'ERROR',
        },
        'katana.cleaner': {
            'handlers': ['file_cleaner', 'console'],
            'level': 'DEBUG',
        },
        'katana.httpwhohas': {
            'handlers': ['file_server', 'console'],
            'level': 'INFO',
        }
    },
    'handlers': {
        'file_server': {
            'class': 'logging.FileHandler',
            'formatter': 'default',
            'filename': '/var/log/katana-server.log',
        },
        'file_cleaner': {
            'class': 'logging.FileHandler',
            'formatter': 'default',
            'filename': '/var/log/katana-cleaner.log',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    }
}
```

#### cache_dir

*default*: `'./data'`

#### cache_dir_max_usage

*default*:  `90`

#### clean_batch_size

*default*:  `100`

#### clean_every

*default*:  `60`

#### ipc_sock_path

*default*:  `'/tmp/katana.sock'`

#### cleaner_db_path

*default*:  `'/tmp/katana_cleaner.db'`

#### not_found_as_200

*default*:  `False`

#### not_found_source

*default*:  `'./404.jpeg'`

#### proxy_url_re

*default*: `None`

#### proxy_origin

*default*: `''`

#### proxy_cache_path

*default*: `''`

#### proxy

*default*: `None`

#### chunk_size

*default*: `16 * 1024`

#### origin_fetch_timeout

*default*: `3`

#### origin_timeout

*default*: `1`

#### thumb_max_width

*default*: `1920`

#### thumb_max_height

*default*: `1080`

#### thumb_max_quality

*default*: `90`

#### thumb_default_quality

*default*: `75`

#### external_expires

*default*: `600`

#### cache_force_expires

*default*: `False`

#### cache_default_expires

*default*: `300`

#### accel_redirect

*default*: `False`

#### accel_redirect_path

*default*: `'/resized'`
