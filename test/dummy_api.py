from abc import abstractmethod
from functools import partial
from time import sleep


from flask import Flask
from flask_restx import Api, Resource, Namespace

from src.phanos import profile_publisher

ns = Namespace("dummy")


def dummy_method():
    pass


class DummyDbAccess:
    @staticmethod
    def test_static():
        pass

    @classmethod
    def test_class(cls):
        pass

    def test_method(self):
        pass

    @classmethod
    @profile_publisher.profile
    def first_access(cls):
        sleep(0.2)

    @profile_publisher.profile
    def second_access(self):
        self.first_access()
        sleep(0.3)


@ns.route("/one")
class DummyResource(Resource):
    access = DummyDbAccess()

    @profile_publisher.profile
    def get(self):
        self.access.first_access()
        self.access.second_access()
        return {"success": True}, 201


app = Flask("TEST")
api = Api(
    app,
    prefix="/api",
)
api.add_namespace(ns)
