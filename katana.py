def main():
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--clean', help='start the cleaner process', action='store_true')
    group.add_argument('--dump', help='print the configuration', action='store_true')
    group.add_argument('--start', help='start the server', action='store_true')
    args = parser.parse_args()

    if args.dump:
        from katana.server import Server
        from pprint import pprint
        pprint(Server().config)

    elif args.clean:
        from katana.cleaner import Cleaner
        try:
            Cleaner().start()
        except KeyboardInterrupt:
            pass

    elif args.start:
        from gevent.pywsgi import WSGIServer
        from katana.server import Server
        WSGIServer(('', 8088), Server().app).serve_forever()

if __name__ == '__main__':
    main()
