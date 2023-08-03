import asyncio
import logging
import unittest
from io import StringIO
import sys
from os.path import dirname, abspath, join

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)


from src.phanos import profiler
from src.phanos.handlers import StreamHandler
from test import dummy_api, common, testing_data
from test.dummy_api import app


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# create console handler with a higher log level
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
# create formatter and add it to the handler
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
# add the handler to the logger
logger.addHandler(handler)


class TestAsyncProfile(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        profiler.config(job="TEST", logger=logger, response_size_profile=False)
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        self.output.close()

    @classmethod
    def tearDownClass(cls) -> None:
        profiler.delete_handlers()
        profiler.delete_metrics(True, True)

    async def test_await(self):
        async_access = dummy_api.AsyncTest()
        _ = await async_access.await_test()
        _ = await async_access.await_test()

        self.output.seek(0)
        methods, values = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.test_await_out_methods)
        self.assertEqual(values, testing_data.test_await_out_values)

    async def test_task(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        task1 = loop.create_task(async_access.task_test())
        task2 = loop.create_task(async_access.async_access_short())
        await asyncio.wait([task1, task2])

        self.output.seek(0)
        methods, values = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.test_task_out_methods)
        self.assertEqual(values, testing_data.test_task_out_values)

    async def test_mix(self):
        async_access = dummy_api.AsyncTest()
        await async_access.test_mix()
        self.output.seek(0)
        methods, values = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.test_mix_out_methods)
        self.assertEqual(values, testing_data.test_mix_out_values)

    async def test_sync_in_async(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        task1 = loop.create_task(async_access.sync_in_async())
        task2 = loop.create_task(async_access.sync_in_async())
        await asyncio.wait([task1, task2])
        self.output.seek(0)
        methods, values = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.sync_in_async_methods)
        self.assertEqual(values, testing_data.sync_in_async_values)

    async def test_async_error(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        with self.assertRaises(RuntimeError):
            await loop.create_task(async_access.raise_error())
        self.output.seek(0)
        print(self.output.readlines())
        methods, values = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
