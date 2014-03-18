import json

import requests
import pytest
import httpretty

import base


class TestBase(object):

    @classmethod
    @pytest.fixture(autouse=True, scope='class')
    def class_setup(cls, request):

        httpretty.enable()
        deals_url = "http://random.random.org/v1/deals"
        deals_data = [
            {"title": "Test Deal",
             "id": "1111"},
            {"title": "Second Deal",
             "id": "2222"}
        ]

        test_deal_url = "http://random.random.org/v1/deals/1111"
        test_deal_data = {
            "title": "Test Deal",
            "id": "1111",
            "description": "some description",
            "date": "12:11:32 Tue 14 Apr 2014",
            "agent": "007"
        }

        second_deal_url = "http://random.random.org/v1/deals/2222"
        second_deal_data = {
            "title": "Second Deal",
            "id": "2222",
            "description": "another description",
            "date": "11:11:32 Tue 14 Apr 2014",
            "agent": "666"
        }

        second_deal_items = {
            "url": "http://random.random.org/v1/deals/2222/items",
            "data": [
            {"title": "oranges",
             "id": "12345"},
            {"title": "apples",
             "id": "33333"}]
        }

        second_deal_items_oranges = {
            "url": "http://random.random.org/v1/deals/2222/items/12345",
            "data": {
                "title": "oranges",
                "id": "12345",
                "amount": "1000",
                "price": "200"}
        }

        agents_url = "http://random.random.org/v1/agents"
        agents_data = [
            {"name": "Kurochkin",
             "id": "007"},
            {"name": "Putler",
             "id": "666"}
        ]

        cls.service = {
            "deals": {
                "url": deals_url,
                "data": deals_data},
            "test_deal": {
                "url": test_deal_url,
                "data": test_deal_data},
            "second_deal": {
                "url": second_deal_url,
                "data": second_deal_data},
            "second_deal_items": second_deal_items,
            "second_deal_items_oranges": second_deal_items_oranges,
            "agents": {
                "url": agents_url,
                "data": agents_data}}

        for value in cls.service.values():
            httpretty.register_uri(httpretty.GET, value['url'],
                                   body=json.dumps(value['data']),
                                   content_type="application/json")

        fin = lambda: httpretty.disable()
        request.addfinalizer(fin)

    @pytest.fixture(scope='class')
    def client(self):
        return base.Client('random.random.org/v1')

    def test_sanity(self):
        response = requests.get(self.service['deals']['url'])
        assert response.json() == self.service['deals']['data']

    def test_get_first(self, client):
        assert client.deals.first()['id'] == '1111'

    def test_get_first_filter(self, client):
        assert client.deals.first(title='Second Deal')['id'] == '2222'

    def test_get_first_raises(self, client):
        with pytest.raises(base.FilterError) as excinfo:
            client.deals.first(name='Second Deal')
        assert excinfo.value.message == \
            '''Resource "deals" doesn't have "name" field'''

    def test_updating_resource_got_from_list(self, client):
        test_deal = client.deals.first(title='Test Deal')
        test_deal.get()
        assert test_deal['agent'] == self.service['test_deal']['data']['agent']

    def test_get_filtering_by_resource(self, client):
        pass

    def test_get_encapsulated_resource(self, client):
        second_deal = client.deals.first(title='Second Deal')
        oranges = second_deal.items.first(title="oranges")
        oranges.get()
        assert oranges['amount'] == \
            self.service["second_deal_items_oranges"]['data']['amount']

