DEFAULT_CONFIG = {
    'ipc_sock_path': '/tmp/katana.sock',
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
    'cache_default_expires': 300,
    'external_expires': 600,
    'cache_dir': './data',
    'cache_dir_max_usage': 90,
    'clean_older_than': 24,
    'clean_every': 4,
    'clean_dry': False,
    'logging': {'version': 1},
}

import os
import logging.config
from copy import deepcopy

def get_config(config_file='katana.conf'):
    config = deepcopy(DEFAULT_CONFIG)
    config_file = os.environ.get('CONFIG_FILE', config_file)
    if os.path.exists(config_file):
        execfile(config_file, {}, config)

    if config['cache_force_expires']:
        config['external_expires'] = max(config['external_expires'], config['cache_default_expires'])

    logging.config.dictConfig(config['logging'])

    return config
