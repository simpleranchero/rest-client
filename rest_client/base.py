import functools
import json
import logging
import urllib2
import pprint

import jsonschema
import requests

from pprint import pprint as pp
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# disabling annoying requests lib's logs
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

# TODO: Need a better configuration facilities
_identifier = 'id'
_resource_list_slash = False
_resource_slash = False


def empty_callable(*args, **kwargs):
    pass


def get_implementation(cls, **kwargs):
    """
    @param cls: Base class in which to search for inheritors
    @param kwargs: a dict of {class property name: class property value} to
    look for in @cls inheritors
    @return class, that have class properties matching, or the latest,
    that do not properties.

    usage:
    >>>class BaseResource(object): pass
    >>>class Resource(BaseResource): pass
    >>>get_implementation(BaseResource, resource='users')
    __main__.Resource
    >>>class Users(BaseResource): resource = 'users'
    >>>get_implementation(BaseResource, resource='users')
    __main__.Users
    """
    return_cls = cls
    for subclass in cls.__subclasses__():
        if all(getattr(subclass, k, None) == v for k, v in kwargs.iteritems()):
            return subclass

        elif all(getattr(subclass, k, None) is None for k in kwargs):
            return_cls = get_implementation(subclass, **kwargs)
    return return_cls


class HttpError(Exception):
    pass


class BaseRestError(Exception):
    pass


class FilterError(BaseRestError):
    pass


class Base():
    """
    Get resource list by name MixIn
    """

    def __init__(self, client, path):
        self._client = client
        self._path = path

    def __getattr__(self, item):
        resource_list_cls = get_implementation(ResourceList, RESOURCE=item)
        return resource_list_cls(self._client, item, self._path)


class BaseRequest(Base):
    def _request(self, method='get', **kwargs):
        """
        Delegates inner requests to client object with adding
        base path to any requested path
        @param method: requests http method
        @param path: tuple of path to add to base path
        @param body: dict that will be dumped to json
        @return: response dict or list of dicts
        """
        path = kwargs.get('path', '')
        kwargs.update(path=self._path+path)
        return self._client._request(method=method, **kwargs)


class Resource(BaseRequest, object):
    # TODO: test dict as base class to enable unpacking
    """
    Resource base class, that can hold resource lists as properties.
    @param client: object with _request method, for url chaining
    @param kwargs: resource attributes

    usage:
    >>>client = Client("localhost")
    >>>foo = client.resources.post(name='foo')
    >>>foo.put(name='bar')
    >>>spam = foo.nested_resources.post('SPAM')
    """
    RESOURCE = None
    IDENTIFIER = _identifier
    SCHEMA = None

    def __init__(self, client, resource, path, kwargs):
        self._resource_name = resource
        super(Resource, self).__init__(client, path)
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
        kwargs = self._request().json()
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
        Updates resource.
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
        header = '---{} object---'.format(self._resource_name)
        footer = '-------------------'
        return '\n'.join(
            (header,
             pprint.pformat(self._kwargs),
             footer))


class ResourceList(BaseRequest, list):
    """
    Creates or lists resources
    @param client: object with _request method, for url chaining
    @param path: requested resource

    """

    RESOURCE = None

    def __init__(self, client, resource, path):
        super(ResourceList, self).__init__(
            client,
            '/'.join([path, resource])
        )
        self._resource_name = resource
        self._resource_cls = get_implementation(Resource, RESOURCE=self._resource_name)
        self.SCHEMA = self._resource_cls.SCHEMA
        self._id = self._resource_cls.IDENTIFIER

    def _request(self, method='get', **kwargs):
        """
        Add trailing slash, if it is in config
        """
        path = kwargs.get('path', '')
        tail = '/' if _resource_list_slash else ''
        kwargs.update(path=path+tail)
        return super(ResourceList, self)._request(method, **kwargs)

    def _get(self, where, query):
        """
        @return generator of resources that match @where dict
        @raise FilterError if fields from @where are not found in resource"""
        response = self._request(query=query).json()

        if not where:
            where = {}

        def resources():
            upd = True
            for kwargs in response:
                path = '/'.join([self._path, str(kwargs[self._id])])
                resource = self._resource(path, kwargs)
                try:
                    if upd:
                        resource.get()
                except HttpError as e:
                    upd = False
                yield resource

        for resource in resources():
            try:
                if all(resource[k] == v for k, v in where.items()):
                    yield resource
            except KeyError as e:
                raise FilterError(
                    '''Resource "{}" doesn't have "{}" field'''.
                    format(self._resource_name, e.message)
                )

    def _resource(self, path, kwargs):
        return self._resource_cls(self._client,
                                  self._resource_name,
                                  path,
                                  kwargs)

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
        @return: resource object as of /resources/<resource_id>
        """
        if self.SCHEMA:
            jsonschema.validate(kwargs, self.SCHEMA)

        response = self._request(method='post', body=kwargs)
        kwargs = response.json()
        path = response.headers.get('location', self._path)
        resource = self._resource(path, kwargs)
        resource.get()
        return resource


class Client(Base):
    """
    Entry point for the front end API.Does not contain
    public methods, only holds resource fabrics
    @param auth: username/password tuple
    @param url: base API url

    usage:
    >>>client = Client(('admin', 'password'),'127.0.0.1')
    >>>all_users = client.users.get()
    >>>client._path
    '127.0.0.1'
    """

    _headers = {}

    def __init__(self, url, auth=None):
        args = iter(url.split('/', 1))
        base = next(args)
        path = next(args, None)
        self.url = 'http://{}'.format(base)
        self.auth = auth
        self._client = self
        self._path = '/'+path if path is not None else ''

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

        path = kwargs.get('path', "")
        url = ''.join([self.url, path, query_path])

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
        log.info('request : {} {} {}'.format(
            method.upper(),
            url,
            response.status_code))
        log.debug('request headers: {}'.format(headers))
        log.debug('request body: {}'.format(response.request.body))
        log.debug('response body: {}'.format(response.text))
        log.info('-'*18)
        if response.status_code not in range(200, 210):
            raise HttpError('\n'.join((str(response.status_code),
                                       response.text)))
        return response


class Context():
    def __init__(self, obj,  **kwargs):
        self.obj = obj
        self._exit_callback = kwargs.pop('exit_callback')
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
        self._exit_callback(self.obj)


def context_headers(cls, enter, exit=empty_callable):
    def __call(self):
        return Context(self, _headers=enter, exit_callback=exit)
    cls.__call__ = __call
