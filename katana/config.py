DEFAULT_CONFIG = {
    'ipc_sock_path': '/tmp/katana.sock',
    'cleaner_db_path': '/tmp/katana_cleaner.db',
    'clean_batch_size': 100,
    'clean_every': 60,
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
    'routing': [{
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
        },
    }],
    'origins': {
        'default': {
            'localhost': {'ips': ['127.0.0.1'], 'headers': {'Host': 'localhost'}}
        }
    },
    'cache_force_expires': False,
    'cache_default_expires': 300,
    'external_expires': 600,
    'cache_dir': './data',
    'cache_dir_max_usage': 90,
    'logging': {'version': 1},
    'not_found_as_200': False,
    'not_found_source': './data/404.jpeg',
}

import os
import logging.config
from copy import deepcopy


def get_config(config_file='katana.conf'):
    config = deepcopy(DEFAULT_CONFIG)
    config_file = os.environ.get('CONFIG_FILE', config_file)
    for config_file in [config_file, '/etc/katana/katana.conf']:
        if os.path.exists(config_file):
            exec(compile(open(config_file).read(), config_file, 'exec'), {}, config)
            break

    logging.config.dictConfig(config['logging'])

    return config
