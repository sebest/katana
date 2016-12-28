__all__ = ['HttpWhoHas']

from gevent import monkey; monkey.patch_all() # flake8: noqa

import gevent

from gevent.queue import Queue

from random import sample
import urllib.request, urllib.error, urllib.parse
import logging


class DefaultErrorHandler(urllib.request.HTTPDefaultErrorHandler):

    def http_error_default(self, req, fp, code, msg, headers):
        result = urllib.error.HTTPError(req.get_full_url(), code, msg, headers, fp)
        result.status = code
        return result


class HttpWhoHas(object):
    """Finds the HTTP server that store a specific file from a list of HTTP servers.

    This object allow to defines clusters of nodes, each nodes of the cluster should have
    the same data.

    The resole process will try to find a node in a cluster storing a specific file and
    will return the full url to the filename.
    """

    def __init__(self, per_cluster=3, user_agent='HttpWhoHas.py', proxy=None, timeout=5):
        """Initializes the resolver.

        Args:
            per_cluster (int): number of node to query from the same cluster.
            user_agent (str): the user agent that will be used for queries.
            proxy (str): a proxy server with IP/HOST:PORT format (eg: '127.0.0.1:8888').
            timeout (int): timeout of the queries.
        """
        self.clusters = {}
        self.per_cluster = per_cluster
        self.user_agent = user_agent
        self.timeout = timeout

        if proxy:
            urllib.request.install_opener(
                urllib.request.build_opener(urllib.request.ProxyHandler({'http': proxy})))

        urllib.request.install_opener(urllib.request.build_opener(DefaultErrorHandler()))

        self.logger = logging.getLogger('katana.httpwhohas')

    def set_cluster(self, name, ips, headers=None):
        """Adds a new cluster in the resolver.

        Args:
            name (str): the name of the cluster.
            ips (list): a list of ips of nodes in this cluster.
            headers (dict): a dict of headers that will be passed to every queries.

        Returns:
            None
        """
        self.clusters[name] = {
            'ips': ips,
            'headers': headers if headers else {},
            'per_cluster': min(self.per_cluster, len(ips)),
        }

    def _do_req(self, name, req, res):
        full_url = req.get_full_url()
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            status_code = resp.code
            if status_code in (200, 304) and not hasattr(req, 'redirect_dict'):
                host = req.get_header('Host')
                modified = status_code == 200
                self.logger.debug(
                    'found url=%s filer=%s host=%s modified=%s', full_url, name, host, modified)
                res.put({
                        'filer': name,
                        'url': full_url,
                        'host': host,
                        'modified': modified,
                        'headers': dict(resp.headers),
                        })
            else:
                self.logger.debug(
                    '%s url=%s returned code %d', name, full_url, status_code)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            self.logger.debug('%s url=%s error: %s', name, full_url, exc)
        except Exception as exc:
            self.logger.exception('%s url=%s got an exception', name, full_url)

    def _do_reqs(self, reqs, res):
        jobs = [gevent.spawn(self._do_req, name, req, res)
                for name, req in reqs]
        gevent.joinall(jobs, timeout=self.timeout)
        res.put(None)
        gevent.killall(jobs)

    def resolve(self, filename, etag=None, last_modified=None):
        """Resolves a filename on the clusters.

        Args:
            filename (str): the filename that we are looking for on the clusters.
            etag (str): the etag to user for the query if any.
            last_modified (str): the date in the same format as returned by Last-Modified.

        Returns:
            A dict if the filename was found otherwise None.

            The dict has the following keys:
             * filer (str): the name of the cluster.
             * url (str): the full url of the filename.
             * host (str): the value of the Host header.
             * modified (bool): True if the file has been modified since the previous request.
             * headers (dict): the HTTP response headers.
        """
        self.logger.debug('resolving %s', filename)
        res = Queue()
        reqs = []
        for name, info in list(self.clusters.items()):
            headers = {'User-Agent': self.user_agent}
            headers.update(info['headers'])
            if etag:
                headers['If-None-Match'] = etag
            elif last_modified:
                headers['If-Modified-Since'] = last_modified
            for ip in sample(info['ips'], info['per_cluster']):
                self.logger.debug(
                    'looking for %s on %s with headers %s', filename, ip, headers)
                req = urllib.request.Request(
                    'http://%s%s' % (ip, filename), headers=headers)
                req.get_method = lambda: 'HEAD'
                reqs.append((name, req))

        gevent.spawn(self._do_reqs, reqs, res)
        result = res.get()
        if result:
            self.logger.debug('found %s on %s: url=%s host=%s', filename,
                              result['filer'], result['url'], result['host'])
        else:
            self.logger.debug('%s not found', filename)
        return result
