from distutils.core import setup

from katana import __version__

setup(
    name='katana',
    version=__version__,
    author='Sebastien Estienne',
    author_email='sebastien.estienne@gmail.com',
    url='-',
    py_modules=['katana'],
    install_requires=['gevent', 'gunicorn', 'PIL'],
    )
