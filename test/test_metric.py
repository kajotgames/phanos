import logging
import time
import unittest
from io import StringIO
import sys
from unittest.mock import patch, MagicMock

from flask import Flask
from flask.ctx import AppContext
from flask.testing import FlaskClient

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
        phanos_profiler.config()

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
        with patch.object(MethodTreeNode, "_clear_children") as mock:
            phanos_profiler.clear()

        mock.assert_any_call()
        self.assertEqual(mock.call_count, 5)


class TestHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config()

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
        self.assertEqual(log_handler._logger.name, "PHANOS")
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        sys.stdout = tmp

    def test_handlers_management(self):
        length = len(phanos_profiler._handlers)
        log1 = LoggerHandler("log_handler1")
        phanos_profiler.add_handler(log1)
        log2 = LoggerHandler("log_handler2")
        phanos_profiler.add_handler(log2)
        self.assertEqual(len(phanos_profiler._handlers), length + 2)
        phanos_profiler.delete_handler("log_handler1")
        self.assertEqual(phanos_profiler._handlers.get("log_handler1"), None)
        phanos_profiler.delete_handlers()
        self.assertEqual(phanos_profiler._handlers, {})

    def test_rabbit_handler_connection(self):
        self.assertRaises(RuntimeError, ImpProfHandler, "handle")

    def test_rabbit_handler_publish(self):
        handler = None
        with patch("src.phanos.publisher.BlockingPublisher") as test_publisher:
            handler = ImpProfHandler("rabbit")
            test_publisher.assert_called()

            test_publish = handler._publisher.publish = MagicMock(return_value=3)

            #  self.assert
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
            hist_no_lbl.store_operation("test:method", "observe", 2.0),
            self.assertEqual(hist_no_lbl.to_records(), testing_data.hist_no_lbl)

            hist_w_lbl = Histogram("hist_w_lbl", "V", labels=["test"])

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
            hist_w_lbl.store_operation(
                method="test:method", value=2.0, label_values={"test": "test"}
            )
            self.assertEqual(hist_w_lbl.to_records(), testing_data.hist_w_lbl)

    def test_summary(self):
        with app.test_request_context():
            sum_no_lbl = Summary(
                "sum_no_lbl",
                "V",
            )
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
            sum_no_lbl.store_operation("test:method", "observe", 2.0),
            self.assertEqual(sum_no_lbl.to_records(), testing_data.sum_no_lbl)

    def test_counter(self):
        with app.test_request_context():
            cnt_no_lbl = Counter(
                "cnt_no_lbl",
                "V",
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
            cnt_no_lbl.store_operation("test:method", "inc", 2.0),
            self.assertEqual(cnt_no_lbl.to_records(), testing_data.cnt_no_lbl)

    def test_info(self):
        with app.test_request_context():
            inf_no_lbl = Info(
                "inf_no_lbl",
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
            inf_no_lbl.store_operation("test:method", "info", {"value": "asd"}),
            self.assertEqual(inf_no_lbl.to_records(), testing_data.inf_no_lbl)

    def test_gauge(self):
        with app.test_request_context():
            gauge_no_lbl = Gauge(
                "gauge_no_lbl",
                "V",
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
            gauge_no_lbl.store_operation("test:method", "inc", 2.0),
            gauge_no_lbl.store_operation("test:method", "dec", 2.0),
            gauge_no_lbl.store_operation("test:method", "set", 2.0),
            self.assertEqual(gauge_no_lbl.to_records(), testing_data.gauge_no_lbl)

    def test_enum(self):
        with app.test_request_context():
            enum_no_lbl = Enum(
                "enum_no_lbl",
                ["true", "false"],
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
            enum_no_lbl.store_operation("test:method", "state", "true")
            self.assertEqual(enum_no_lbl.to_records(), testing_data.enum_no_lbl)

    def test_builtin_profilers(self):
        time_profiler = TimeProfiler("test_time_prof")

        time_profiler.start()
        time_profiler.start()
        self.assertEqual(len(time_profiler._start_ts), 2)
        time.sleep(0.2)
        time_profiler.store_operation("test:method", "stop")
        self.assertEqual(len(time_profiler._start_ts), 1)
        time.sleep(0.2)
        time_profiler.store_operation("test:method", "stop")
        self.assertEqual(len(time_profiler._start_ts), 0)
        self.assertEqual(time_profiler._values[0][1] // 100, 2)
        self.assertEqual(time_profiler._values[1][1] // 100, 4)


class TestProfiling(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config()
        cls.app = app
        cls.client = cls.app.test_client()

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
        length = len(phanos_profiler._metrics)
        # create metrics
        hist = Histogram("name", "units")
        phanos_profiler.add_metric(hist)
        hist1 = Histogram("name1", "units")
        phanos_profiler.add_metric(hist1)
        self.assertEqual(len(phanos_profiler._metrics), length + 2)
        # delete metric
        phanos_profiler.delete_metric("name")
        self.assertEqual(len(phanos_profiler._metrics), length + 1)
        self.assertEqual(phanos_profiler._metrics.get("name"), None)
        # delete time_profiling metric
        phanos_profiler.delete_metric(publisher.TIME_PROFILER)
        self.assertEqual(phanos_profiler._metrics.get(publisher.TIME_PROFILER), None)
        self.assertEqual(phanos_profiler.time_profile, None)
        # delete response size metric
        phanos_profiler.delete_metric(publisher.RESPONSE_SIZE)
        self.assertEqual(phanos_profiler._metrics.get(publisher.RESPONSE_SIZE), None)
        self.assertEqual(phanos_profiler.resp_size_profile, None)
        # create response size metric
        phanos_profiler.create_response_size_profiler()
        self.assertIsNotNone(phanos_profiler.resp_size_profile)
        self.assertEqual(len(phanos_profiler._metrics), 2)

        # delete all metrics (without response size and time profiling metrics)
        phanos_profiler.delete_metrics()
        self.assertEqual(len(phanos_profiler._metrics), 1)
        self.assertIsNotNone(phanos_profiler.resp_size_profile, None)
        self.assertIsNotNone(phanos_profiler._metrics.get(publisher.RESPONSE_SIZE))
        phanos_profiler.delete_metrics(rm_time_profile=True, rm_resp_size_profile=True)
        self.assertEqual(phanos_profiler._metrics, {})
        self.assertEqual(phanos_profiler._metrics.get(publisher.RESPONSE_SIZE), None)

    def test_profiling(self):
        phanos_profiler.handle_records = False
        _ = self.client.get("http://localhost/api/dummy/one")
        self.output.seek(0)
        lines = self.output.readlines()
        self.assertEqual(lines, [])

        phanos_profiler.handle_records = True
        _ = self.client.get("http://localhost/api/dummy/one")

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

        # cleanup assertion
        for metric in phanos_profiler._metrics.values():
            self.assertEqual(metric._values, [])
            self.assertEqual(metric._label_values, [])
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.item, [])

    def test_custom_profile_addition(self):
        hist = Histogram("test_name", "test_units", ["place"])
        self.assertEqual(len(phanos_profiler._metrics), 2)
        phanos_profiler.add_metric(hist)
        self.assertEqual(len(phanos_profiler._metrics), 3)
        phanos_profiler.delete_metric(publisher.TIME_PROFILER)
        phanos_profiler.delete_metric(publisher.RESPONSE_SIZE)

        def before_root_func(function):
            hist.store_operation(
                operation="observe",
                method=phanos_profiler.current_node.context,
                value=1.0,
                label_values={"place": "before_root"},
            )

        phanos_profiler.before_root_func = before_root_func

        def before_func(function):
            hist.store_operation(
                operation="observe",
                method=phanos_profiler.current_node.context,
                value=2.0,
                label_values={"place": "before_func"},
            )

        phanos_profiler.before_func = before_func

        def after_func(fn_result):
            hist.store_operation(
                operation="observe",
                method=phanos_profiler.current_node.context,
                value=3.0,
                label_values={"place": "after_func"},
            )

        phanos_profiler.after_func = after_func

        def after_root_func(fn_result):
            hist.store_operation(
                operation="observe",
                method=phanos_profiler.current_node.context,
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
