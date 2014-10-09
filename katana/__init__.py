__version__ = '1.4'


def create_app():
    from .server import Server
    return Server().app
