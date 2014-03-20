import json

import jsonschema
import requests
import pytest
import httpretty

import base


class VersionFactory(base.ResourceFactory):
    RESOURCE = 'version'

    def _get(self, where=None, query=None):
        return iter([self.resource(self._request(query=query))])


class Version(base.Resource):
    RESOURCE = 'version'
    IDENTIFIER = 'number'


class Agent(base.Resource):
    RESOURCE = 'agents'
    SCHEMA = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "secret": {"type": "string"},
            "tasks": {"type": "number"},
            "id": {"type": "string"},
            'email': {'type': 'string', 'format': 'email'}
        },
        "required": ['email']
    }


class TestBase(object):

    @classmethod
    @pytest.fixture(autouse=True, scope='class')
    def class_setup(cls, request):

        httpretty.enable()

        base_url = "http://random.random.org/v1"

        deals = {
            "url": "/deals",
            "data": [
                {"title": "Test Deal",
                 "id": "1111"},
                {"title": "Second Deal",
                 "id": "2222"}
            ]
        }

        test_deal = {
            "url": "/deals/1111",
            "data": {
                "title": "Test Deal",
                "id": "1111",
                "description": "some description",
                "date": "12:11:32 Tue 14 Apr 2014",
                "agent": "007"
            }
        }

        second_deal = {
            "url": "/deals/2222",
            "data": {
                "title": "Second Deal",
                "id": "2222",
                "description": "another description",
                "date": "11:11:32 Tue 14 Apr 2014",
                "agent": "666"
            }
        }

        second_deal_items = {
            "url": "/deals/2222/items",
            "data": [
            {"title": "oranges",
             "id": "12345"},
            {"title": "apples",
             "id": "33333"}]
        }

        second_deal_items_oranges = {
            "url": "/deals/2222/items/12345",
            "data": {
                "title": "oranges",
                "id": "12345",
                "amount": "1000",
                "price": "200"}
        }

        agents = {
            "url": "/agents",
            "data": [
                {"name": "Kurochkin",
                 'secret': 'AA',
                 'tasks': 2,
                 "id": "007",
                 "email": "k@mail.com"
                 },
                {"name": "Adler",
                 'secret': 'A',
                 'tasks': 0,
                 "id": "111"}
            ]
        }
        agents_A = {
            'url': '/agents/AA',
            'data': [
                {'name': 'Kurochkin',
                 'id': '007'}
            ]
        }

        version = {
            "url": '/version',
            "data": {'number': '124.23.4'}
        }
        cls.service = {
            "deals": deals,
            "test_deal": test_deal,
            "second_deal": second_deal,
            "second_deal_items": second_deal_items,
            "second_deal_items_oranges": second_deal_items_oranges,
            "agents": agents,
            "agents_AA": agents_A,
            'version': version}

        for value in cls.service.values():
            httpretty.register_uri(httpretty.GET,
                                   ''.join([base_url, value['url']]),
                                   body=json.dumps(value['data']),
                                   content_type="application/json")

        fin = lambda: httpretty.disable()
        request.addfinalizer(fin)

    @pytest.fixture(scope='class')
    def client(self):
        return base.Client('random.random.org/v1')

    def test_sanity(self, client):
        client.deals.get()
        response = requests.get("http://random.random.org/v1/deals")
        assert response.json() == self.service['deals']['data']

    def test_get_all(self, client):
        assert client.deals.get()[1]['id'] == \
                   self.service['deals']['data'][1]['id']

    def test_get_first(self, client):
        assert client.deals.first()['id'] == '1111'

    def test_get_first_filter(self, client):
        assert client.deals.first(
            where={'title': 'Second Deal'})['id'] == '2222'

    def test_get_first_raises(self, client):
        with pytest.raises(base.FilterError) as excinfo:
            client.deals.first(where={'name': 'Second Deal'})
        assert excinfo.value.message == \
            '''Resource "deals" doesn't have "name" field'''

    def test_updating_resource_got_from_list(self, client):
        test_deal = client.deals.first(where={'title': 'Test Deal'})
        test_deal.get()
        assert test_deal['agent'] == self.service['test_deal']['data']['agent']

    def test_get_filtering_by_resource(self, client):
        pass

    def test_get_encapsulated_resource(self, client):
        second_deal = client.deals.first(where={'title': 'Second Deal'})
        oranges = second_deal.items.first(where={'title': "oranges"})
        oranges.get()
        assert oranges['amount'] == \
            self.service["second_deal_items_oranges"]['data']['amount']

    def test_get_url_filters(self, client):
        test_deal = client.deals.first(query={'title': 'Test Deal'})
        # TODO: check that URL query was send correctly

    def test_get_new_resource_factory(self, client):
        version = client.version.first()
        assert version['number'] == self.service['version']['data']['number']

    def test_get_factory_from_factory(self, client):
        A_agents = client.agents.AA.first()
        assert A_agents['name'] == self.service['agents_AA']['data'][0]['name']

    def test_get_resource_with_schema(self, client):
        client.agents.first(where={'name': 'Kurochkin'})
        with pytest.raises(jsonschema.ValidationError) as excinfo:
            client.agents.first(where={'name': 'Adler'})