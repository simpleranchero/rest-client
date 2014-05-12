rest-client
===========

rest-client is a base for creating python rest client.

Usage
-----

This is a simple example of using rest-client from the box::

    from rest_client import base

    client = base.Client('127.0.0.1:8080/v1')
    admin = client.users(where={
        'role': 'admin',
        'status': 'registered'
    })

    test_organization = client.organizations.post(
        name="Test",
        address="Fake address",
        admin=admin['id']
    )

    test_organization.action.register.get()

Or you can update it with more complex logic::

    from rest_client import base

    class Organization(base.Resource):
        resource = 'departments'

        def register(self):
            self.actions.register.get()

    client = base.Client('127.0.0.1:8080/v1')
    test_organization = client.organizations.first(where={
        'name': 'Test'
    })

    test_organization.register()

