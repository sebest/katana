__version__ = '1.1'

def create_app():
    from .server import Server
    return Server().app
