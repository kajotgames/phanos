import asyncio
import datetime
import logging
import unittest
from io import StringIO
import sys
from os.path import dirname, abspath, join

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)


from src.phanos import async_profiler
from phanos.handlers import StreamHandler
from test import dummy_api
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
        async_profiler.config(job="TEST", logger=logger, request_size_profile=False)
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        async_profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        self.output.close()

    @classmethod
    def tearDownClass(cls) -> None:
        async_profiler.delete_handlers()
        async_profiler.delete_metrics(True, True)

    async def test_time_measurement(self):
        """checks if time profiling works with async"""
        async_access = dummy_api.AsyncTest()
        _ = await async_access.nested()
