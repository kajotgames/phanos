import asyncio
import datetime
import logging
import unittest
from io import StringIO
import sys
from os.path import dirname, abspath, join


import phanos.tree

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)


from src.phanos import async_profiler
from phanos.handlers import StreamHandler
from src.phanos.tree import MethodTreeNode
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
        loop = asyncio.get_event_loop()

        start = datetime.datetime.now()
        # await asyncio.wait([task])
        _ = await async_access.nested()

        stop = datetime.datetime.now() - start
        print(stop)
        # total time of execution is 0.3 (most time consuming method)
        # self.assertEqual(round(stop.total_seconds(), 1), 0.3)
        self.output.seek(0)
        print(self.output.read())
        self.output.seek(0)
        output = []
        for line in self.output.readlines():
            output.append(float(line.split("value: ")[1][:-4]) // 100)
        print(output)
        print(async_profiler.tree.active_tasks)

        # [short_task, long_task] execution time from phanos profiler

    # self.assertEqual(output, [2.0, 3.0, 3.0])


class TestAsyncTree(unittest.TestCase):
    def test_async_tree(self):
        # TODO: asserty
        tree = phanos.tree.ContextTree(logger)

        node1 = MethodTreeNode()
        node1.ctx.context = "POST:x.y.z"

        node2 = MethodTreeNode()
        node2.ctx.context = "POST:x.y.q"

        node3 = MethodTreeNode()
        node3.ctx.context = "POST:x.y"

        node4 = MethodTreeNode()
        node4.ctx.context = "POST:x.y"

        tree.insert(node1)
        tree.insert(node2)
        tree.insert(node3)
        tree.insert(node4)

        tree.postorder_print()


class TestAsyncContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        async_profiler.config(job="TEST")
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        async_profiler.create_time_profiler()
        async_profiler.create_response_size_profiler()
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        async_profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        async_profiler.delete_handlers()
        async_profiler.delete_metrics(True, True)
        async_profiler.before_root_func = None
        async_profiler.after_root_func = None
        async_profiler.before_func = None
        async_profiler.after_func = None
        self.output.close()

    def test_profiling(self):
        """
        # test of api call inside same api call with error risen
        async_profiler.handle_records = True
        _ = self.client.post("http://localhost/api/dummy/one")
        self.output.seek(0)
        self.assertEqual(self.output.readlines(), [])
        # cleanup assertion
        for metric in async_profiler.metrics.values():
            self.assertEqual(metric._values, [])
            self.assertEqual(metric._label_values, [])
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.item, [])
        # error_occurred will be set to false before root function of next profiling
        self.assertEqual(async_profiler.error_occurred, True)
        self.assertEqual(async_profiler.current_node, async_profiler._root)

        # profiling after request, where error_occurred
        _ = self.client.get("http://localhost/api/dummy/one")
        self.assertEqual(async_profiler.error_occurred, False)
        self.output.seek(0)

        async_profiler.tree.postorder()
        """
