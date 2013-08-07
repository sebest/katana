from setuptools import setup
from pip.req import parse_requirements

from katana import __version__

install_reqs = parse_requirements("requirements.txt")

setup(
    name='katana',
    version=__version__,
    author='Sebastien Estienne',
    author_email='sebastien.estienne@gmail.com',
    url='http://github.com/sebest/katana',
    packages=['katana'],
    scripts = ['scripts/katana',],
    data_files = [('/etc/katana', ['katana.conf.sample']),],
    install_requires=[str(ir.req) for ir in install_reqs],
    )
