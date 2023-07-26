import asyncio
import datetime
import logging
import time
import unittest
from io import StringIO
import sys
from os.path import dirname, abspath, join
from unittest.mock import patch, MagicMock

from flask import Flask
from flask.ctx import AppContext
from flask.testing import FlaskClient

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)


from src.phanos import phanos_profiler, publisher
from src.phanos.publisher import (
    StreamHandler,
    ImpProfHandler,
    LoggerHandler,
    BaseHandler,
)
from src.phanos.tree import MethodTreeNode
from test import testing_data, dummy_api
from test.dummy_api import app, dummy_method, DummyDbAccess
from src.phanos.metrics import (
    Histogram,
    Summary,
    Counter,
    Info,
    Gauge,
    Enum,
    TimeProfiler,
)


class TestAsyncProfile(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", request_size_profile=False)
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        phanos_profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        phanos_profiler.delete_handlers()
        phanos_profiler.delete_metrics(True, True)
        self.output.close()

    async def test_profiling(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        task_long = loop.create_task(async_access.async_access_long())
        task_short = loop.create_task(async_access.async_access_short())
        start = datetime.datetime.now()
        await asyncio.wait([task_long, task_short])
        stop = datetime.datetime.now() - start
        # total time of execution is 0.2 (long_task)
        self.assertEqual(round(stop.total_seconds(), 1), 0.3)
        self.output.seek(0)
        print(self.output.read())
        self.output.seek(0)
        output = []
        for line in self.output.readlines():
            output.append(float(line.split("value: ")[1][:-4]) // 100)
        # [short_task, long_task] execution time from phanos profiler
        # self.assertEqual(output, [2.0, 0.3])


class TestAsyncTree(unittest.TestCase):
    def test_async_tree(self):
        # TODO: asserty
        root = MethodTreeNode()
        node1 = MethodTreeNode()
        node1.context = "POST:x.y.z"

        node2 = MethodTreeNode()
        node2.context = "POST:x.y"

        node3 = MethodTreeNode()
        node3.context = "POST:y.z"
        node4 = MethodTreeNode()
        node4.context = "POST:x.y.z.w"

        node1._insert_into_tree(root, node1.context.split(":")[1].split("."))
        node2._insert_into_tree(root, node2.context.split(":")[1].split("."))

        node3._insert_into_tree(root, node3.context.split(":")[1].split("."))
        node4._insert_into_tree(root, node4.context.split(":")[1].split("."))

        root.print_postorder()


class TestAsyncContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST")
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        phanos_profiler.create_time_profiler()
        phanos_profiler.create_response_size_profiler()
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        phanos_profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        phanos_profiler.delete_handlers()
        phanos_profiler.delete_metrics(True, True)
        phanos_profiler.before_root_func = None
        phanos_profiler.after_root_func = None
        phanos_profiler.before_func = None
        phanos_profiler.after_func = None
        self.output.close()

    def test_profiling(self):
        """
        # test of api call inside same api call with error risen
        phanos_profiler.handle_records = True
        _ = self.client.post("http://localhost/api/dummy/one")
        self.output.seek(0)
        self.assertEqual(self.output.readlines(), [])
        # cleanup assertion
        for metric in phanos_profiler.metrics.values():
            self.assertEqual(metric._values, [])
            self.assertEqual(metric._label_values, [])
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.item, [])
        # error_occurred will be set to false before root function of next profiling
        self.assertEqual(phanos_profiler.error_occurred, True)
        self.assertEqual(phanos_profiler.current_node, phanos_profiler._root)
        """
        # profiling after request, where error_occurred
        _ = self.client.get("http://localhost/api/dummy/one")
        self.assertEqual(phanos_profiler.error_occurred, False)
        self.output.seek(0)

        phanos_profiler.tree.postorder()
