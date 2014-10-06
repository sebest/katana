__version__ = '1.2'


def create_app():
    from .server import Server
    return Server().app
