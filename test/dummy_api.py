import asyncio
from time import sleep

import flask
from flask import Flask
from flask_restx import Api, Resource, Namespace

from src.phanos import profile

ns = Namespace("dummy")


def dummy_func():
    pass


# for context testing inside list comprehension
@profile
def test_inside_list_comp():
    return 5


@profile
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
    @profile
    def first_access(cls):
        sleep(0.2)

    @profile
    def second_access(self):
        self.first_access()
        sleep(0.3)

    def third_access(self):
        self.second_access()

    @profile
    def raise_access(self):
        self.first_access()
        raise RuntimeError()


class AsyncTest:
    @staticmethod
    @profile
    async def async_access_short():
        await asyncio.sleep(0.2)
        await asyncio.sleep(0.1)

    @staticmethod
    @profile
    async def async_access_long():
        await asyncio.sleep(0.2)

    @staticmethod
    @profile
    def sync_access_long():
        sleep(0.2)

    @profile
    async def await_test(self):
        await self.async_access_short()
        await self.async_access_long()

    @profile
    async def task_nested(self):
        await self.async_access_short()

    @profile
    async def task_test(self):
        loop = asyncio.get_event_loop()
        # task with no await_test
        loop.create_task(self.async_access_long())
        await asyncio.wait([asyncio.create_task(self.task_nested())])

    @profile
    async def test_mix(self):
        await asyncio.wait([asyncio.create_task(self.task_test())])
        await asyncio.wait([asyncio.create_task(self.task_test())])

    @profile
    async def nested(self):
        await self.async_access_short()

    @profile
    async def sync_in_async(self):
        self.sync_access_long()

    @profile
    async def raise_error(self):
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.async_access_short())
        await task
        raise RuntimeError()

    @profile
    async def wo_await(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.async_access_short())

    @profile
    async def all_task_possibilities(self):
        loop = asyncio.get_event_loop()
        await asyncio.gather(self.async_access_short())
        await asyncio.wait([asyncio.create_task(self.async_access_short())])
        loop.create_task(self.async_access_short())
        asyncio.create_task(self.async_access_short())
        # loop.run_until_complete(self.async_access_short())
        asyncio.ensure_future(self.async_access_short())
        await asyncio.sleep(0.4)


@profile
async def async_access_short():
    await asyncio.sleep(0.2)
    await asyncio.sleep(0.1)


@profile
async def async_access_long():
    await asyncio.sleep(0.2)


@profile
async def multiple_calls():
    loop = asyncio.get_event_loop()
    task1 = loop.create_task(async_access_long())
    task2 = loop.create_task(async_access_short())
    await asyncio.wait([task1, task2])


@profile
async def nested():
    await multiple_calls()


@ns.route("/one")
class DummyResource(Resource):
    access = DummyDbAccess()

    @profile
    def get(self):
        self.access.first_access()
        self.access.second_access()
        return {"success": True}, 201

    @profile
    def get_(self):
        self.access.third_access()
        return {"success": True}, 201

    # for testing nested api calls
    @profile
    def post(self):
        with app.app_context():
            return app.test_client().delete("/api/dummy/one")

    @profile
    def delete(self):
        with app.app_context():
            response = app.test_client().put("/api/dummy/one")
        return response.json, response.status_code

    @profile
    def put(self):
        flask.abort(400, "some shit")


app = Flask("TEST")
api = Api(
    app,
    prefix="/api",
)
api.add_namespace(ns)
