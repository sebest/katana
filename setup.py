from distutils.core import setup
setup(
    name='katana',
    version='1.0',
    py_modules=['katana'],
    install_requires=['gevent', 'gunicorn', 'PIL'],
    )
