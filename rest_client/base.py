import collections
import functools
import json
import logging
import pprint

import requests

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# disabling annoying requests lib's logs
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)


Pair = collections.namedtuple('Pair', 'key value')

_identifier = 'id'


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

    def _request(self, method='get', path=None, body=None):
        """
        delegates inner requests to client object with adding
        base path to any requested path
        @param method: requests http method
        @param path: tuple of path to add to base path
        @param body: dict that will be dumped to json
        @return: response dict or list of dicts
        """

        path = self._path + path if path else self._path
        return self._client._request(method=method, path=path, body=body)


class SelectByProperty():

    def __new__(cls, resource):
        """
        If there is a separate implementation of ResourceFactory for given
        resource it will be use, else default ResourceFactory is used
        """
        for subclass in cls.__subclasses__():
            if subclass.RESOURCE is resource:
                return object.__new__(subclass, resource)
        return object.__new__(cls, resource)


class FactoryGeneratorMixin():
    """
    Get resource by property
    """
    def __getattr__(self, item):
        return ResourceFactory(self, item)


class Resource(BaseChainedRequester,
               SelectByProperty,
               FactoryGeneratorMixin):
    """
    Resource base class, that can hold resource fabrics.
    @param client: object with _request method, for url chaining
    @param kwargs: resource attributes

    usage:
    foo = client.resources.create( name='foo')
    """
    RESOURCE = None
    IDENTIFIER = _identifier

    def __new__(cls, client, resource, kwargs):
        return super(cls, Resource).__new__(cls, resource)

    def __init__(self, client, resource, kwargs):
        super(Resource, self).__init__(client, (kwargs[self.IDENTIFIER],))
        self._kwargs = kwargs
        self._resource_name = resource

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


class ResourceFactory(BaseChainedRequester,
                      FactoryGeneratorMixin,
                      SelectByProperty):
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

    def __new__(cls, client, resource):
        return super(cls, ResourceFactory).__new__(cls, resource)

    def __init__(self, client, resource):

        super(ResourceFactory, self).__init__(
            client,
            (resource,),
        )
        self._resource_name = resource
        self.resource = functools.partial(Resource, self, resource)

    def _get(self, kwargs):

        response = self._request()

        if kwargs:
            #filter with kwargs if they are present

            try:
                entities_list = [item for item in response if
                                 all(item[k] == v for k, v in kwargs.items())]
            except KeyError as e:
                raise FilterError('''Resource "{}" doesn't have "{}" field'''.
                        format(self._resource_name, e.message))
        else:
            entities_list = response

        def map_and_update():
            updatable = True
            for entity in entities_list:
                e = self.resource(entity)
                try:
                    updatable and e.get()
                except HttpError as e:
                    if '404' in e.message:
                        updatable = False
                    else:
                        raise
                yield e
        return map_and_update()

    def get(self, **kwargs):
        """
        Get resources with filtering
        @param kwargs: optional attribute filter
        @return: list of resources or None depending on filter
        """
        return list(self._get(kwargs))

    def first(self, **kwargs):
        """
        Get first resource with filtering
        @param kwargs: optional attribute filter
        @return: resource or None depending on filter
        """
        return next(self._get(kwargs), None)

    def post(self, **kwargs):
        """
        Create new resource
        @param kwargs: resource attributes
        @rtype resource sub-type
        @return: specified on time of creation resource
        """
        t_id = (self._request(method='post', body=kwargs)['id'],)
        return self.resource(self._request(path=t_id))


class Client(object, FactoryGeneratorMixin):
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

    def _request(self, method='get', path=None, token=None, body=None):
        """
        Request sender. Joins all chained resources in path.
        @raises HttpError is response is not ok
        """
        url = '/'.join((self.url,) + path)

        headers = {'Content-Type': 'application/json'}
        if body:
            body = json.dumps(body)

        response = requests.request(
            method,
            url,
            auth=self.auth,
            headers=headers,
            data=body)

        log.debug('request: {} {} {}'.format(
            method.upper(),
            url,
            response.status_code))
        log.debug('body: {}'.format(response.request.body))

        if response.status_code not in range(200, 210):
            raise HttpError('\n'.join((str(response.status_code),
                                       response.text)))
        return response.json()
