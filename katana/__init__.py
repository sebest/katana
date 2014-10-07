__version__ = '1.3'


def create_app():
    from .server import Server
    return Server().app
