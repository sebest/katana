from zmq import green as zmq


class IPCInvalidMode(Exception): pass
class IPCSockPathError(Exception): pass

class IPC(object):

    def __init__(self, sock_path, mode):
        self.sock_path = sock_path
        self.ctx = zmq.Context()
        if mode == 'push':
            self.sock = self.ctx.socket(zmq.PUSH)
            self.sock.connect("ipc://%s" % self.sock_path)
        elif mode == 'pull':
            self.sock = self.ctx.socket(zmq.PULL)
            self.sock.bind("ipc://%s" % self.sock_path)
        else:
            raise IPCInvalidMode('%s is not a valid mode, use pull or pull' % mode)       

    def push(self, msg):
        self.sock.send(msg)

    def pull(self):
        return self.sock.recv()

if __name__ == '__main__':
    import sys
    from gevent import sleep
    sock_path = sys.argv[1]
    mode = sys.argv[2]
    if mode == 'push':
        i = IPC(sock_path, mode)
        while True:
            i.push('hello')
            sleep(0.1)
    elif mode == 'pull':
        i = IPC(sock_path, mode)
        while True:
            print i.pull()
