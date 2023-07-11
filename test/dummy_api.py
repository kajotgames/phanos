from abc import abstractmethod
from functools import partial
from time import sleep


from flask import Flask
from flask_restx import Api, Resource, Namespace

from src.phanos import phanos_profiler

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
    @phanos_profiler.profile
    def first_access(cls):
        sleep(0.2)

    @phanos_profiler.profile
    def second_access(self):
        self.first_access()
        sleep(0.3)

    def third_access(self):
        self.second_access()


@ns.route("/one")
class DummyResource(Resource):
    access = DummyDbAccess()

    @phanos_profiler.profile
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

if __name__ == "__main__":
    from src.phanos import phanos_profiler
    from src.phanos.publisher import LoggerHandler

    phanos_profiler.config()
    handler = LoggerHandler("asd")
    phanos_profiler.add_handler(handler)
    print("starting profle")
    resource = DummyResource()
    res = resource.get()
