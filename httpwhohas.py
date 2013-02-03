import gevent

from gevent import monkey; monkey.patch_all()

from gevent.event import AsyncResult
from gevent.queue import Queue
from gevent.timeout import Timeout

from random import sample
import urllib2

class HttpWhoHas(object):

    def __init__(self, per_cluster=3, user_agent='HttpWhoHas.py', proxy=None, timeout=5):
        self.clusters = {}
        self.per_cluster = per_cluster
        self.user_agent = user_agent
        self.timeout = timeout

        if proxy:
            urllib2.install_opener(
                urllib2.build_opener(
                    urllib2.ProxyHandler({'http': proxy})
                )
            )

    def set_cluster(self, name, ips, headers=None):
        self.clusters[name] = {
            'ips': ips,
            'headers': headers if headers else {},
            'per_cluster': min(self.per_cluster, len(ips)),
        }

    def do_req(self, name, req, res):
        try:
            status_code = urllib2.urlopen(req, timeout=self.timeout).code
            if status_code == 200 and not hasattr(req, 'redirect_dict'):
                res.set((name, req.get_full_url(), req.get_header('Host'),))
        except Exception, e:
            pass

    def resolve(self, filename):
        res = AsyncResult()
        reqs = []
        for name, info in self.clusters.items():
            headers = {'User-Agent': self.user_agent}
            headers.update(info['headers'])
            for ip in sample(info['ips'], info['per_cluster']):
                req = urllib2.Request('http://%s%s' % (ip, filename), headers=headers)
                req.get_method = lambda: 'HEAD'
                reqs.append((name, req))

        jobs = [gevent.spawn(self.do_req, name, req, res) for name, req in reqs]
        try:
            info = res.get(timeout=self.timeout)
        except Timeout:
            info = None
        gevent.killall(jobs)
        return info

if __name__ == '__main__':
    h = HttpWhoHas(proxy='127.0.0.1:8888', timeout=1)
    h.set_cluster('filer-01', ['10.201.6.%d' % i for i in range(1, 7)], {'Host': 'filer-01.int.dmcloud.net'})
    h.set_cluster('filer-02', ['10.201.13.%d' % i for i in range(1, 7)], {'Host': 'filer-02.int.dmcloud.net'})
    h.set_cluster('filer-01.dev', ['10.195.10.%d' % i for i in range(1, 7)], {'Host': 'filer-01.dev.int.dmcloud.net'})
    res = h.resolve('/e/3/4c1a4d3edede832bfd000002/d/4/5108124ddede8349d3000003/jpeg_thumbnail_source.jpeg')
    print res