import base


class Resource(base.Resource):
    def data(self):
        return self._kwargs

Client = base.Client