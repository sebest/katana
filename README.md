Katana
======

*Katana* is a HTTP caching proxy with dynamic image resizing capabiliy.

It is used on production for more than 2 years on moderate traffic websites and can scale linearly adding more instances.

Even thought it can serve traffic directly to clients, a really common setup is to use it as the origin of CDN like Akamai, Edgecast or Cloudfront.

Features
--------

- HTTP proxying
- HTTP caching with file cleaner
- Image resizing and caching
- Full support of HTTP caching Headers (Etag, Cache-Control, If-Modified-Since, etc)
- Rewriting of URLs and path in the cache
- HttpWhoHas: using HEAD requests on backends server to locate a file
- Configurable logging and debugging
- X-accel feature to put nginx in front of Katana
- Can return (resized) image on 404 not found
- Can work with Gunicorn or standalone

Configuration
-------------

The configuration file is a standard python file.

Two sample configuration files are provide:
 * katana-simple.conf.sample: the most basic configuration file to start with.
 * katana-complex.conf.sample: a more complex example showing off more features.

### Configuration parameters

#### origins

`origins` defines the origins from where the proxy will fetch the images.

You can define multiple origins that you can later reference in your `routing`.

Each origin can contain multiple clusters, a cluster is a list of servers having the same files.

Each cluster have different files.

The proxy is able to locate which cluster is hosting a specific file.

Each node in a cluster does not have to be perfectly synced as the proxy will try up to 3 nodes in parallel.

So even if a node is down it does not affect the service.

It is highly recommended that every nodes in a cluster have the same files at a certain point in time but it is not required for the sync process to be realtime.

Nodes in a cluster provide redundancy and higher throughput.

Clusters provide horizontal storage scalability.

The most simple setting is to have one origin with one cluster of one node.

It is recommended to use ip address to define nodes in a cluster to avoid DNS resolution, you can pass HTTP headers is you are using names based virtualhost.

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

We take advantage of the python syntax to create a list the nodes.

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

`routing` is a `list` of `dict`, the routes will be try in the order of the list, and the first route that match a regex will be choosen.

Each `dict` can contains up to actions as key: `resize` and/or `proxy`, the value of the `action` key is a dict of parameters.

Here is the default value to give you an idea of the structure.

*default*:
```python
routing = [{
    'resize': {
        'url_re': None,
        'origin_tmpl': '',
        'cache_path_source': '',
        'cache_path_resized': '',
        'origin': 'default',
    },
    'proxy': {
        'url_re': None,
        'origin_tmpl': '',
        'cache_path': '',
        'origin': 'default',
    }
}]
```
**Actions**

`proxy` is used is you want to serve the image as is with no processin

**paramters for **


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
