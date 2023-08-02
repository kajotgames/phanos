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


class TestTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", request_size_profile=True)

    def tearDown(self) -> None:
        pass

    def test_tree(self):
        root = MethodTreeNode()
        # classmethod
        first = MethodTreeNode(dummy_api.DummyDbAccess.test_class)
        root.add_child(first)
        self.assertEqual(first.parent, root)
        self.assertEqual(root.children, [first])
        self.assertEqual(first.context, "DummyDbAccess:test_class")
        root.delete_child()
        self.assertEqual(root.children, [])
        self.assertEqual(first.parent, None)
        # method
        first = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        root.add_child(first)
        self.assertEqual(first.context, "DummyDbAccess:test_method")
        root.delete_child()
        # function
        first = MethodTreeNode(dummy_method)
        root.add_child(first)
        self.assertEqual(first.context, "dummy_api:dummy_method")
        root.delete_child()
        # descriptor
        access = DummyDbAccess()
        first = MethodTreeNode(access.__getattribute__)
        root.add_child(first)
        self.assertEqual(first.context, "object:__getattribute__")
        root.delete_child()
        # staticmethod
        first = MethodTreeNode(access.test_static)
        root.add_child(first)
        self.assertEqual(first.context, "DummyDbAccess:test_static")
        root.delete_child()

        first = MethodTreeNode(self.tearDown)
        root.add_child(first)
        self.assertEqual(first.context, "TestTree:tearDown")

    def test_clear_tree(self):
        root = phanos_profiler._root
        _1 = MethodTreeNode(self.tearDown)
        root.add_child(_1)
        self.assertEqual(_1.context, "TestTree:tearDown")
        _1.add_child(MethodTreeNode(self.tearDown))
        _1.add_child(MethodTreeNode(self.tearDown))
        _1.add_child(MethodTreeNode(self.tearDown))
        with patch.object(MethodTreeNode, "clear_children") as mock:
            phanos_profiler.clear()

        mock.assert_any_call()
        self.assertEqual(mock.call_count, 5)

        phanos_profiler.clear()
        # no children exist but error should not be raised
        phanos_profiler._root.delete_child()

    def test_methods_between(self):
        output = StringIO()
        str_handler = StreamHandler("str_handler", output)
        phanos_profiler.add_handler(str_handler)
        dummy_api.test_list_comp()
        dummy_api.DummyResource().get_()
        output.seek(0)
        methods = []
        for line in output.readlines():
            methods.append(line.split(", ")[1][8:])
        phanos_profiler.delete_handlers()
        self.assertEqual([methods[0], methods[3]], testing_data.methods_between_out)


class TestHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", request_size_profile=True)

    def tearDown(self) -> None:
        phanos_profiler.delete_handlers()

    def test_stream_handler(self):
        # base handler test
        base = BaseHandler("test_handler")
        self.assertRaises(NotImplementedError, base.handle, "test_profiler", {})
        # stream handler
        output = StringIO()
        str_handler = StreamHandler("str_handler", output)
        str_handler.handle(testing_data.test_handler_in, "test_name")
        str_handler.handle(testing_data.test_handler_in_no_lbl, "test_name")
        output.seek(0)
        self.assertEqual(
            output.read(),
            testing_data.test_handler_out + testing_data.test_handler_out_no_lbl,
        )

    def test_log_handler(self):
        tmp = sys.stdout
        output = StringIO()
        sys.stdout = output
        logger = logging.getLogger()
        logger.setLevel(10)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(10)
        logger.addHandler(handler)
        log_handler = LoggerHandler("log_handler", logger)
        log_handler.handle(testing_data.test_handler_in, "test_name")
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        log_handler = LoggerHandler("log_handler1")
        self.assertEqual(log_handler.logger.name, "PHANOS")
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        sys.stdout = tmp

    def test_handlers_management(self):
        length = len(phanos_profiler.handlers)
        log1 = LoggerHandler("log_handler1")
        phanos_profiler.add_handler(log1)
        log2 = LoggerHandler("log_handler2")
        phanos_profiler.add_handler(log2)
        self.assertEqual(len(phanos_profiler.handlers), length + 2)
        phanos_profiler.delete_handler("log_handler1")
        self.assertEqual(phanos_profiler.handlers.get("log_handler1"), None)
        phanos_profiler.delete_handlers()
        self.assertEqual(phanos_profiler.handlers, {})

        self.assertRaises(KeyError, phanos_profiler.delete_handler, "nonexistent")

        handler1 = StreamHandler("handler")
        handler2 = StreamHandler("handler")
        phanos_profiler.add_handler(handler1)
        self.assertEqual(handler1, phanos_profiler.handlers["handler"])
        phanos_profiler.add_handler(handler2)
        self.assertEqual(handler2, phanos_profiler.handlers["handler"])

    def test_rabbit_handler_connection(self):
        self.assertRaises(RuntimeError, ImpProfHandler, "handle")

    def test_rabbit_handler_publish(self):
        handler = None
        with patch("src.phanos.publisher.BlockingPublisher") as test_publisher:
            handler = ImpProfHandler("rabbit")
            test_publisher.assert_called()
            # noinspection PyDunderSlots,PyUnresolvedReferences
            test_publish = handler.publisher.publish = MagicMock(return_value=3)

            handler.handle(profiler_name="name", records=testing_data.test_handler_in)
            test_publish.assert_called()


class TestMetrics(unittest.TestCase):
    app: Flask
    client: FlaskClient
    context: AppContext

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = app

    def test_histogram(self):
        with app.test_request_context():
            hist_no_lbl = Histogram(
                "hist_no_lbl",
                "V",
                "TEST",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                hist_no_lbl.store_operation,
                "test:method",
                "observe",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                hist_no_lbl.store_operation,
                "test:method",
                "nonexistent",
                2.0,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                hist_no_lbl.store_operation,
                "test:method",
                "observe",
                "asd",
            )
            hist_no_lbl.cleanup()
            # valid operation
            hist_no_lbl.store_operation("test:method", operation="observe", value=2.0),
            self.assertEqual(hist_no_lbl.to_records(), testing_data.hist_no_lbl)

            hist_w_lbl = Histogram("hist_w_lbl", "V", "TEST", labels=["test"])

            # missing label
            self.assertRaises(
                ValueError,
                hist_w_lbl.store_operation,
                "test:method",
                "observe",
                2.0,
            )
            hist_w_lbl.cleanup()
            # default operation
            hist_w_lbl.store_operation(method="test:method", value=2.0, label_values={"test": "test"})
            self.assertEqual(hist_w_lbl.to_records(), testing_data.hist_w_lbl)

    def test_summary(self):
        with app.test_request_context():
            sum_no_lbl = Summary("sum_no_lbl", "V", job="TEST")
            # invalid label
            self.assertRaises(
                ValueError,
                sum_no_lbl.store_operation,
                "test:method",
                "observe",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                sum_no_lbl.store_operation,
                "test:method",
                "nonexistent",
                2.0,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                sum_no_lbl.store_operation,
                "test:method",
                "observe",
                "asd",
            )
            sum_no_lbl.cleanup()
            # valid operation
            sum_no_lbl.store_operation("test:method", operation="observe", value=2.0),
            self.assertEqual(sum_no_lbl.to_records(), testing_data.sum_no_lbl)

    def test_counter(self):
        with app.test_request_context():
            cnt_no_lbl = Counter(
                "cnt_no_lbl",
                "V",
                "TEST",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                cnt_no_lbl.store_operation,
                "test:method",
                "inc",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                cnt_no_lbl.store_operation,
                "test:method",
                "inc",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                cnt_no_lbl.store_operation,
                "test:method",
                "inc",
                -1,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                cnt_no_lbl.store_operation,
                "test:method",
                "nonexistent",
                2.0,
            )
            cnt_no_lbl.cleanup()

            # valid operation
            cnt_no_lbl.store_operation("test:method", operation="inc", value=2.0),
            self.assertEqual(cnt_no_lbl.to_records(), testing_data.cnt_no_lbl)

    def test_info(self):
        with app.test_request_context():
            inf_no_lbl = Info(
                "inf_no_lbl",
                job="TEST",
            )
            # invalid value type
            self.assertRaises(
                ValueError,
                inf_no_lbl.store_operation,
                "test:method",
                "info",
                "asd",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                inf_no_lbl.store_operation,
                "test:method",
                "nonexistent",
                2.0,
            )
            inf_no_lbl.cleanup()
            # valid operation
            inf_no_lbl.store_operation("test:method", operation="info", value={"value": "asd"}),
            self.assertEqual(inf_no_lbl.to_records(), testing_data.inf_no_lbl)

    def test_gauge(self):
        with app.test_request_context():
            gauge_no_lbl = Gauge(
                "gauge_no_lbl",
                "V",
                "TEST",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                gauge_no_lbl.store_operation,
                "test:method",
                "inc",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "test:method",
                "inc",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "test:method",
                "inc",
                -1,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "test:method",
                "dec",
                -1,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "test:method",
                "set",
                False,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                gauge_no_lbl.store_operation,
                "test:method",
                "nonexistent",
                2.0,
            )
            gauge_no_lbl.cleanup()
            # valid operation
            gauge_no_lbl.store_operation("test:method", operation="inc", value=2.0),
            gauge_no_lbl.store_operation("test:method", operation="dec", value=2.0),
            gauge_no_lbl.store_operation("test:method", operation="set", value=2.0),
            self.assertEqual(gauge_no_lbl.to_records(), testing_data.gauge_no_lbl)

    def test_enum(self):
        with app.test_request_context():
            enum_no_lbl = Enum(
                "enum_no_lbl",
                ["true", "false"],
                job="TEST",
            )
            # invalid value
            self.assertRaises(
                ValueError,
                enum_no_lbl.store_operation,
                "test:method",
                "state",
                "maybe",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                enum_no_lbl.store_operation,
                "test:method",
                "nonexistent",
                "true",
            )
            enum_no_lbl.cleanup()
            # valid operation
            enum_no_lbl.store_operation("test:method", operation="state", value="true")
            self.assertEqual(enum_no_lbl.to_records(), testing_data.enum_no_lbl)

            enum_no_lbl.store_operation("test:method", operation="state", value="true")
            enum_no_lbl._values.pop(0)
            self.assertRaises(RuntimeError, enum_no_lbl.to_records)

    def test_builtin_profilers(self):
        time_profiler = TimeProfiler("test_time_prof", "TEST")

        time_profiler.start()
        time_profiler.start()
        self.assertEqual(len(time_profiler._start_ts), 2)
        time.sleep(0.2)
        time_profiler.store_operation("test:method", operation="stop")
        self.assertEqual(len(time_profiler._start_ts), 1)
        time.sleep(0.2)
        time_profiler.store_operation("test:method", operation="stop")
        self.assertEqual(len(time_profiler._start_ts), 0)
        self.assertEqual(time_profiler._values[0][1] // 100, 2)
        self.assertEqual(time_profiler._values[1][1] // 100, 4)

        self.assertRaises(RuntimeError, time_profiler.store_operation, "test:method", "stop")


class TestProfiling(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", request_size_profile=True)
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

    def test_metric_management(self):
        length = len(phanos_profiler.metrics)
        # create metrics
        hist = Histogram("name", "TEST", "units")
        phanos_profiler.add_metric(hist)
        hist1 = Histogram("name1", "TEST", "units")
        phanos_profiler.add_metric(hist1)
        self.assertEqual(len(phanos_profiler.metrics), length + 2)
        # delete metric
        phanos_profiler.delete_metric("name")
        self.assertEqual(len(phanos_profiler.metrics), length + 1)
        self.assertEqual(phanos_profiler.metrics.get("name"), None)
        # delete time_profiling metric
        phanos_profiler.delete_metric(publisher.TIME_PROFILER)
        self.assertEqual(phanos_profiler.metrics.get(publisher.TIME_PROFILER), None)
        self.assertEqual(phanos_profiler.time_profile, None)
        # delete response size metric
        phanos_profiler.delete_metric(publisher.RESPONSE_SIZE)
        self.assertEqual(phanos_profiler.metrics.get(publisher.RESPONSE_SIZE), None)
        self.assertEqual(phanos_profiler.resp_size_profile, None)
        # create response size metric
        phanos_profiler.create_response_size_profiler()
        self.assertIsNotNone(phanos_profiler.resp_size_profile)
        self.assertEqual(len(phanos_profiler.metrics), 2)

        # delete all metrics (without response size and time profiling metrics)
        phanos_profiler.delete_metrics()
        self.assertEqual(len(phanos_profiler.metrics), 1)
        self.assertIsNotNone(phanos_profiler.resp_size_profile, None)
        self.assertIsNotNone(phanos_profiler.metrics.get(publisher.RESPONSE_SIZE))
        phanos_profiler.delete_metrics(rm_time_profile=True, rm_resp_size_profile=True)
        self.assertEqual(phanos_profiler.metrics, {})
        self.assertEqual(phanos_profiler.metrics.get(publisher.RESPONSE_SIZE), None)

        self.assertRaises(KeyError, phanos_profiler.delete_metric, "nonexistent")

        metric1 = Histogram("hist", "TEST", "xz")
        metric2 = Histogram("hist", "TEST", "xz")
        phanos_profiler.add_metric(metric1)
        self.assertEqual(metric1, phanos_profiler.metrics["hist"])
        phanos_profiler.add_metric(metric2)
        self.assertEqual(metric2, phanos_profiler.metrics["hist"])

    def test_profiling(self):
        # do not handle records
        phanos_profiler.handle_records = False
        _ = self.client.get("http://localhost/api/dummy/one")
        self.output.seek(0)
        lines = self.output.readlines()
        self.assertEqual(lines, [])

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

        # profiling after request, where error_occurred
        _ = self.client.get("http://localhost/api/dummy/one")
        self.assertEqual(phanos_profiler.error_occurred, False)
        self.output.seek(0)
        lines = self.output.readlines()
        time_lines = lines[:-1]
        size_line = lines[-1]
        for i in range(len(time_lines)):
            line = time_lines[i][:-1]
            value = line.split("value: ")[1][:-3]
            self.assertEqual(
                (float(value)) // 100,
                testing_data.profiling_out[i]["value"],
            )
            method = line.split(", ")[1][8:]
            self.assertEqual(
                method,
                testing_data.profiling_out[i]["method"],
            )

        size_line = size_line[:-1]
        value = size_line.split("value: ")[1][:-2]
        self.assertEqual(
            (float(value)),
            testing_data.profiling_out[-1]["value"],
        )
        method = size_line.split(", ")[1][8:]
        self.assertEqual(
            method,
            testing_data.profiling_out[-1]["method"],
        )

        self.assertEqual(phanos_profiler.current_node, phanos_profiler._root)
        self.assertEqual(phanos_profiler._root.children, [])

        access = dummy_api.DummyDbAccess()
        self.output.truncate(0)
        self.output.seek(0)
        self.assertRaises(RuntimeError, access.raise_access)
        self.output.seek(0)
        # len 1 cuz DummyDbAccess.first_access finished, but then raise error so raise_access wasn't measured
        self.assertEqual(len(self.output.readlines()), 1)

        # cleanup assertion
        for metric in phanos_profiler.metrics.values():
            self.assertEqual(metric._values, [])
            self.assertEqual(metric._label_values, [])
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.item, [])

    def test_custom_profile_addition(self):
        hist = Histogram("test_name", "TEST", "test_units", ["place"])
        self.assertEqual(len(phanos_profiler.metrics), 2)
        phanos_profiler.add_metric(hist)
        self.assertEqual(len(phanos_profiler.metrics), 3)
        phanos_profiler.delete_metric(publisher.TIME_PROFILER)
        phanos_profiler.delete_metric(publisher.RESPONSE_SIZE)

        def before_root_func(func, args, kwargs):
            print(func)
            print(args)
            print(kwargs)
            hist.store_operation(
                method=phanos_profiler.current_node.context,
                operation="observe",
                value=1.0,
                label_values={"place": "before_root"},
            )

        phanos_profiler.before_root_func = before_root_func

        def before_func(func, args, kwargs):
            _ = args
            _ = kwargs
            _ = func
            hist.store_operation(
                method=phanos_profiler.current_node.context,
                operation="observe",
                value=2.0,
                label_values={"place": "before_func"},
            )

        phanos_profiler.before_func = before_func

        def after_func(fn_result, args, kwargs):
            _ = args
            _ = kwargs
            _ = fn_result
            hist.store_operation(
                method=phanos_profiler.current_node.context,
                operation="observe",
                value=3.0,
                label_values={"place": "after_func"},
            )

        phanos_profiler.after_func = after_func

        def after_root_func(fn_result, args, kwargs):
            _ = args
            _ = kwargs
            _ = fn_result
            hist.store_operation(
                method=phanos_profiler.current_node.context,
                operation="observe",
                value=4.0,
                label_values={"place": "after_root"},
            )

        phanos_profiler.after_root_func = after_root_func

        dummy_access = DummyDbAccess()
        _ = dummy_access.second_access()
        self.output.seek(0)
        logs = self.output.readlines()
        for i in range(len(logs)):
            line = logs[i].split(", ")
            method = line[1][8:]
            value = line[2][7:10]
            place = line[3][14:-1]
            self.assertEqual(method, testing_data.custom_profile_out[i]["method"])
            self.assertEqual(float(value), testing_data.custom_profile_out[i]["value"])
            self.assertEqual(place, testing_data.custom_profile_out[i]["place"])


class TestAsync(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual(round(stop.total_seconds(), 1), 0.2)
        self.output.seek(0)
        output = []
        for line in self.output.readlines():
            output.append(float(line.split("value: ")[1][:-4]) // 100)
        # [short_task, long_task] execution time from phanos profiler
        self.assertEqual(output, [1.0, 2.0])
