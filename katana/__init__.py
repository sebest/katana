__version__ = '2.1'


def create_app():
    from .server import Server
    return Server().app
