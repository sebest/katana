from setuptools import setup

from katana import __version__

setup(
    name='katana',
    version=__version__,
    author='Sebastien Estienne',
    author_email='sebastien.estienne@gmail.com',
    url='http://github.com/sebest/katana',
    packages=['katana'],
    scripts=['scripts/katana'],
    install_requires=[
        'Pillow',
        'gevent',
        'pyzmq',
    ],
    )
