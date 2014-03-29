import contextlib
import functools
import json
import logging
import urllib2
import pprint

import jsonschema
import requests

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# disabling annoying requests lib's logs
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)


_identifier = 'id'


def get_implementation(cls, **kwargs):
    for subclass in cls.__subclasses__():
        if all(getattr(subclass, k, None) == v for k, v in kwargs.iteritems()):
            return subclass
    return cls


class HttpError(Exception):
    pass


class BaseRestError(Exception):
    pass


class FilterError(BaseRestError):
    pass


class BaseChainedRequester(object):

    """
    Base class that implements request chaining interface:
    it takes client object that have '_request' method
    and base path. And then when inner request come
    it is redirected to client object with adding base path to
    request path.
    @param client: object that has _request method - client, resource
    or resource_factory
    @param path: base path tuple of current object that will be added to
    each request
    """

    def __init__(self, client, path):
        self._client = client
        self._path = path

    def _request(self, method='get', **kwargs):
        """
        delegates inner requests to client object with adding
        base path to any requested path
        @param method: requests http method
        @param path: tuple of path to add to base path
        @param body: dict that will be dumped to json
        @return: response dict or list of dicts
        """

        path = kwargs.get('path', ())
        kwargs.update(path=self._path + path)
        return self._client._request(method=method, **kwargs)


class ChainCaller():
    """
    Get resource by property
    """
    CHAINS = None

    def __getattr__(self, item):
        return get_implementation(self.CHAINS or ResourceFactory,
                                  RESOURCE=item)(self, item)


class Resource(BaseChainedRequester,
               ChainCaller,):
    """
    Resource base class, that can hold resource fabrics.
    @param client: object with _request method, for url chaining
    @param kwargs: resource attributes

    usage:
    foo = client.resources.create( name='foo')
    """
    RESOURCE = None
    IDENTIFIER = _identifier
    SCHEMA = None

    def __init__(self, client, kwargs):
        super(Resource, self).__init__(client, (str(kwargs[self.IDENTIFIER]),))
        self._kwargs = kwargs

    def _update(self, kwargs):
        """
        Internal update for resource attributes
        """
        self._kwargs.update(kwargs)

    def delete(self):
        """
        Deletes resource
        """
        self._request('delete')

    def get(self):
        """
        Updates resource objects attributes
        """
        kwargs = self._request()
        self._update(kwargs)

    def post(self, **kwargs):
        """
        Updates resources attributes
        @params kwargs: attributes to update
        """
        self._request('post', body=kwargs)
        self.get()

    def put(self, **kwargs):
        """
        Updates whole resource. Is idempotent
        @params kwargs: attributes to update
        """
        self._request('put', body=kwargs)
        self.get()

    def __getitem__(self, item):
        """
        Better getter for self._kwargs
        """
        if item in self._kwargs:
            return self._kwargs[item]
        raise KeyError(item)

    def __str__(self):
        """
        Better string representation
        """
        header = '---{} object---'.format(self.__class__.__name__)
        footer = '-------------------'
        return '\n'.join(
            (header,
             pprint.pformat(self._kwargs),
             footer))


class ResourceFactory(BaseChainedRequester, ChainCaller):
    """
    Creates or lists resources
    @param client: object with _request method, for url chaining
    @param resource: requested resource

    usage:
    class SomeResource():
        def __init__(self, client):
            self.resources = ResourceFactory(Resource)
    ...
    foo = bar.resources.get('first', name='foo')
    """

    RESOURCE = None
    PRODUCES = Resource

    def __init__(self, client, resource):

        super(ResourceFactory, self).__init__(
            client,
            (resource,),
        )
        self._resource_name = resource
        resource_cls = get_implementation(Resource, RESOURCE=resource)
        self._resource_schema = resource_cls.SCHEMA
        self.resource = functools.partial(resource_cls, self)

    def _get(self, where, query):

        response = self._request(query=query)

        def resources():
            req = True
            for entity in response:
                ent = self.resource(entity)
                try:
                    if req:
                        ent.get()
                except HttpError as e:
                    req = False
                yield ent

        if where:

            #filter with kwargs if they are present
            def filtered_resources():
                for resource in resources():
                    try:
                        if all(resource[k] == v for k, v in where.items()):
                            yield resource
                    except KeyError as e:
                        raise FilterError(
                            '''Resource "{}" doesn't have "{}" field'''.
                            format(self._resource_name, e.message)
                        )

            entities_gen = filtered_resources()
        else:
            entities_gen = iter(response)

        return entities_gen

    def get(self, where=None, query=None):
        """
        Get resources with filtering
        @param where: optional dict param to filter response
        @param query: optional dict of queries to be send with request
        @return: list of resources or None depending on filter
        """
        return list(self._get(where, query))

    def first(self, where=None, query=None):
        """
        Get first resource with filtering
        @param where: optional dict param to filter response
        @param query: optional dict of queries to be send with request
        @return: resource or None depending on filter
        """
        return next(self._get(where, query), None)

    def post(self, **kwargs):
        """
        Create new resource
        @param kwargs: resource attributes
        @rtype resource sub-type
        @return: specified on time of creation resource
        """
        if self._resource_schema:
            jsonschema.validate(kwargs, self._resource_schema)
        t_id = (self._request(method='post', body=kwargs)['id'],)
        return self.resource(self._request(path=t_id))


class Client(object, ChainCaller):
    """
    Entry point for the front end API.Does not contain
    public methods, only holds resource fabrics
    @param auth: username/password tuple
    @param url: base API url

    usage:
    client = Client(('admin', 'password'),'10.10.121.53')
    all_users = client.users.get()
    ...
    """

    _headers = {}

    def __init__(self, url, auth=None):
        self.url = 'http://{}'.format(url)
        self.auth = auth
        self.trailing_slash = False

    def _request(self, method='get', **kwargs):
        """
        Request sender. Joins all chained resources in path.
        @raises HttpError is response is not ok
        """

        query_path = ''
        query = kwargs.get('query', None)
        if query:
            query_path = '?' + '&'.join('{}={}'.format(k, urllib2.quote(v))
                                        for k, v in query.iteritems())
        trailing = '/' if self.trailing_slash else ''

        path = kwargs.get('path', ())
        url = '/'.join((self.url,) + path) + trailing + query_path

        headers = kwargs.get('headers', {})
        headers.update({'Content-Type': 'application/json'})
        headers.update(self._headers)

        body = kwargs.get('body', None)
        if body:
            body = json.dumps(body)

        try:
            response = requests.request(
                method,
                url,
                auth=self.auth,
                headers=headers,
                data=body)
        except Exception as e:
            raise HttpError(e.message)
        log.debug('-'*18)
        log.debug('request : {} {} {}'.format(
            method.upper(),
            url,
            response.status_code))
        log.debug('request headers: {}'.format(headers))
        log.debug('request body: {}'.format(response.request.body))
        log.debug('response body: {}'.format(response.text))
        log.debug('-'*18)
        if response.status_code not in range(200, 210):
            raise HttpError('\n'.join((str(response.status_code),
                                       response.text)))
        return response.json()


class FakeClient(object, ChainCaller):
    """
    Entry point for the front end API.Does not contain
    public methods, only holds resource fabrics
    @param auth: username/password tuple
    @param url: base API url

    usage:
    client = Client(('admin', 'password'),'10.10.121.53')
    all_users = client.users.get()
    ...
    """
    def __init__(self, url, auth=None):
        self.url = 'http://{}'.format(url)
        self.auth = auth
        self.trailing_slash = False

    def _request(self, method='get', path=None, query=None, body=None):
        """
        Request sender. Joins all chained resources in path.
        @raises HttpError is response is not ok
        """
        query_path = ''
        if query:
            query_path = '?' + '&'.join('{}={}'.format(k, urllib2.quote(v))
                                        for k, v in query.iteritems())
        trailing = '/' if self.trailing_slash else ''
        url = '/'.join((self.url,) + path) + trailing + query_path

        headers = {'Content-Type': 'application/json'}

        print method.upper(), url
        print "headers: "
        pprint.pprint(headers)
        pprint.pprint(body)
        return [{'id': '1'}]


class Context():
    def __init__(self, obj,  **kwargs):
        self.kwargs = {k: v(obj) for k, v in kwargs.iteritems()}

    def _update_cls(self, kwargs):
        for k, v in kwargs.iteritems():
            setattr(Client, k, v)

    def __enter__(self):
        self.initial = {k: getattr(Client, k) for k in self.kwargs}
        self._update_cls(self.kwargs)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._update_cls(self.initial)
        if exc_type:
            raise exc_type(exc_val)


def context_headers(cls, callback):
    def __call(self):
        return Context(self, _headers=callback)
    cls.__call__ = __call

