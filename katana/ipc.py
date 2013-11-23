from zmq import green as zmq


class IPCInvalidMode(Exception): pass
class IPCSockPathError(Exception): pass

class IPC(object):

    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.ctx = zmq.Context()
        self.sock_push = None
        self.sock_pull = None

    def push(self, msg):
        if not self.sock_push:
            self.sock_push = self.ctx.socket(zmq.PUSH)
            self.sock_push.set_hwm(0)
            self.sock_push.connect("ipc://%s" % self.sock_path)
        self.sock_push.send(msg)

    def pull(self):
        if not self.sock_pull:
            self.sock_pull = self.ctx.socket(zmq.PULL)
            self.sock_pull.set_hwm(0)
            self.sock_pull.bind("ipc://%s" % self.sock_path)
        return self.sock_pull.recv()

if __name__ == '__main__':
    import sys
    from gevent import sleep
    sock_path = sys.argv[1]
    mode = sys.argv[2]
    if mode == 'push':
        i = IPC(sock_path)
        while True:
            i.push('hello')
            sleep(0.1)
    elif mode == 'pull':
        i = IPC(sock_path)
        while True:
            print i.pull()
