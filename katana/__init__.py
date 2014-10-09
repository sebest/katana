__version__ = '1.5'


def create_app():
    from .server import Server
    return Server().app
