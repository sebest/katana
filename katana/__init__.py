__version__ = '1.0'

def create_app():
    from .server import Server
    return Server().app
