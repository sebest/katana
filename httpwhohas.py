from gevent import monkey; monkey.patch_all()

import gevent

from gevent.queue import Queue
from gevent.timeout import Timeout

from random import sample
import urllib2
import logging

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

        self.logger = logging.getLogger('httpwhohas')

    def set_cluster(self, name, ips, headers=None):
        self.clusters[name] = {
            'ips': ips,
            'headers': headers if headers else {},
            'per_cluster': min(self.per_cluster, len(ips)),
        }

    def _do_req(self, name, req, res):
        full_url = req.get_full_url()
        try:
            status_code = urllib2.urlopen(req, timeout=self.timeout).code
            if status_code == 200 and not hasattr(req, 'redirect_dict'):
                res.put((name, full_url, req.get_header('Host'),))
            else:
                self.logger.debug('%s url=%s returned code %d', name, full_url, status_code)
        except urllib2.HTTPError as exc:
           self.logger.debug('%s url=%s error: %s', name, full_url, exc)
        except Exception as exc:
            self.logger.exception('%s url=%s got an exception', name, full_url)

    def _do_reqs(self, reqs, res):
        jobs = [gevent.spawn(self._do_req, name, req, res) for name, req in reqs]
        gevent.joinall(jobs, timeout=self.timeout)
        res.put(None)
        gevent.killall(jobs)

    def resolve(self, filename):
        self.logger.debug('resolving %s', filename)
        res = Queue()
        reqs = []
        for name, info in self.clusters.items():
            headers = {'User-Agent': self.user_agent}
            headers.update(info['headers'])
            for ip in sample(info['ips'], info['per_cluster']):
                self.logger.debug('looking for %s on %s with headers %s', filename, ip, headers)
                req = urllib2.Request('http://%s%s' % (ip, filename), headers=headers)
                req.get_method = lambda: 'HEAD'
                reqs.append((name, req))

        gevent.spawn(self._do_reqs, reqs, res)
        result = res.get()
        if result:
            self.logger.debug('found %s on %s: url=%s host=%s', filename, result[0], result[1], result[2])
        else:
            self.logger.debug('%s not found', filename)
