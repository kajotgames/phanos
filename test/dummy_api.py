import asyncio
from time import sleep

import flask
from flask import Flask
from flask_restx import Api, Resource, Namespace

from src.phanos import phanos_profiler, sync_profile, async_profile
from phanos.handlers import LoggerHandler

ns = Namespace("dummy")


def dummy_method():
    pass


@sync_profile
def test_inside_list_comp():
    return 5


@sync_profile
def test_list_comp():
    _ = [test_inside_list_comp() for _ in range(1)]


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
    @sync_profile
    def first_access(cls):
        sleep(0.2)

    @sync_profile
    def second_access(self):
        self.first_access()
        sleep(0.3)

    def third_access(self):
        self.second_access()

    @sync_profile
    def raise_access(self):
        self.first_access()
        raise RuntimeError()


class AsyncTest:
    @staticmethod
    @async_profile
    async def async_access_short():
        await asyncio.sleep(0.2)
        await asyncio.sleep(0.1)

    @staticmethod
    @async_profile
    async def async_access_long():
        await asyncio.sleep(0.2)

    @async_profile
    async def multiple_calls(self):
        loop = asyncio.get_event_loop()
        await loop.create_task(self.async_access_long(), name="long")
        await loop.create_task(self.async_access_short(), name="short")
        # await asyncio.wait([task1, task2])

    @async_profile
    async def nested(self):
        loop = asyncio.get_event_loop()
        await self.multiple_calls()
        await loop.create_task(self.async_access_short(), name="nested-short")
        # await asyncio.wait([task1, task2])
        return 5


@async_profile
async def async_access_short():
    await asyncio.sleep(0.2)
    await asyncio.sleep(0.1)


@async_profile
async def async_access_long():
    await asyncio.sleep(0.2)


@async_profile
async def multiple_calls():
    loop = asyncio.get_event_loop()
    task1 = loop.create_task(async_access_long())
    task2 = loop.create_task(async_access_short())
    await asyncio.wait([task1, task2])


@async_profile
async def nested():
    await multiple_calls()


@ns.route("/one")
class DummyResource(Resource):
    access = DummyDbAccess()

    @sync_profile
    def get(self):
        self.access.first_access()
        self.access.second_access()
        return {"success": True}, 201

    @sync_profile
    def get_(self):
        self.access.third_access()
        return {"success": True}, 201

    # for testing nested api calls
    @sync_profile
    def post(self):
        with app.app_context():
            return app.test_client().delete("/api/dummy/one")

    @sync_profile
    def delete(self):
        with app.app_context():
            response = app.test_client().put("/api/dummy/one")
        return response.json, response.status_code

    @sync_profile
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
