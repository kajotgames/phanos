import asyncio
from time import sleep

import flask
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

    @phanos_profiler.profile
    def raise_access(self):
        self.first_access()
        raise RuntimeError()


class AsyncTest:
    @staticmethod
    @phanos_profiler.profile
    async def async_access_short():
        await asyncio.sleep(0.1)

    @staticmethod
    @phanos_profiler.profile
    async def async_access_long():
        await asyncio.sleep(0.2)


@ns.route("/one")
class DummyResource(Resource):
    access = DummyDbAccess()

    @phanos_profiler.profile
    def get(self):
        self.access.first_access()
        self.access.second_access()
        return {"success": True}, 201

    @phanos_profiler.profile
    def get_(self):
        self.access.third_access()
        return {"success": True}, 201

    # for testing nested api calls
    @phanos_profiler.profile
    def post(self):
        with app.app_context():
            return app.test_client().delete("/api/dummy/one")

    @phanos_profiler.profile
    def delete(self):
        with app.app_context():
            response = app.test_client().put("/api/dummy/one")
        return response.json, response.status_code

    @phanos_profiler.profile
    def put(self):
        flask.abort(400, "some shit")
        return {"success", True}, 200


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
