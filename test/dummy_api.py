from abc import abstractmethod
from functools import partial
from time import sleep

from flask import Flask
from flask_restx import Api, Resource, Namespace

from src.phanos import phanos_profiler
from src.phanos.publisher import LoggerHandler

ns = Namespace("dummy")


def dummy_method():
    pass


@phanos_profiler.profile
def test_inside_list_comp():
    return 5


@phanos_profiler.profile
def test_list_comp():
    _ = [test_inside_list_comp() for i in range(1)]
    y = lambda a: test_inside_list_comp() + a
    _ = y(1)
    x = (test_inside_list_comp() ** 2 for i in range(1))
    for i in x:
        _ = i


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
    phanos_profiler.config()
    handler = LoggerHandler("asd")
    phanos_profiler.add_handler(handler)
    print("starting profile")
    _ = test_list_comp()
