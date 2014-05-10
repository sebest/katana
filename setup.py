from setuptools import setup

from katana import __version__

setup(
    name='katana',
    version=__version__,
    author='Sebastien Estienne',
    author_email='sebastien.estienne@gmail.com',
    url='http://github.com/sebest/katana',
    packages=['katana'],
    scripts = ['scripts/katana',],
    data_files = [('/etc/katana', ['katana.conf.sample']),],
    install_requires=[
        'Pillow',
        'gevent',
        'pyzmq',
    ],
    )
