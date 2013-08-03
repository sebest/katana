from distutils.core import setup

from katana import __version__

REQUIREMENTS = [i.strip() for i in open("requirements.txt").readlines()]

setup(
    name='katana',
    version=__version__,
    author='Sebastien Estienne',
    author_email='sebastien.estienne@gmail.com',
    url='http://github.com/sebest/katana',
    py_modules=['katana'],
    scripts = ['katana.py',],
    data_files = [('/etc/katana', ['katana.conf.sample']),],
    install_requires=REQUIREMENTS,
    )
