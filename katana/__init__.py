__version__ = '2.0'


def create_app():
    from .server import Server
    return Server().app
