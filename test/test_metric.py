import logging
import unittest
from io import StringIO
import sys
import ast
from unittest.mock import patch, MagicMock, Mock

from flask import Flask
from flask.ctx import AppContext
from flask.testing import FlaskClient
from imp_prof.messaging.publisher import BlockingPublisher

from src.phanos import profile_publisher, publisher
from src.phanos.publisher import StreamHandler, RabbitMQHandler, LoggerHandler
from src.phanos.tree import MethodTree
from test import testing_data, dummy_api
from test.dummy_api import app, no_class, dummy_method, DummyResource, DummyDbAccess
from src.phanos.metrics import (
    Histogram,
    Summary,
    Counter,
    Info,
    Gauge,
    Enum,
)


def side_effect_func(record, *args, **kwargs):
    print("bitch")
    return record


config = {
    "BlockingPublisher.return_value": "self",
    "publish.side_effect": "side_effect_func",
}


class TestTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_tree(self):
        root = MethodTree()
        # classmethod
        first = MethodTree(self.setUpClass)
        root.add_child(first)
        self.assertEqual(first.parent, root)
        self.assertEqual(root.children, [first])
        self.assertEqual(first.context, "TestTree:setUpClass")
        root.delete_child()
        self.assertEqual(root.children, [])
        self.assertEqual(first.parent, None)
        # method
        first = MethodTree(self.tearDown)
        root.add_child(first)
        self.assertEqual(first.context, "TestTree:tearDown")
        root.delete_child()
        # function
        first = MethodTree(dummy_method)
        root.add_child(first)
        self.assertEqual(first.context, "dummy_api:dummy_method")
        root.delete_child()
        # descriptor
        access = DummyDbAccess()
        first = MethodTree(access.__getattribute__)
        root.add_child(first)
        self.assertEqual(first.context, "object:__getattribute__")
        root.delete_child()
        # staticmethod
        first = MethodTree(access.test_static)
        root.add_child(first)
        self.assertEqual(first.context, "DummyDbAccess:test_static")
        root.delete_child()


class TestHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.publisher = MagicMock()
        cls.publisher._publish.return_value = 2

    def tearDown(self) -> None:
        pass

    def test_stream_handler(self):
        output = StringIO()
        str_handler = StreamHandler("str_handler", output)
        str_handler.handle("test_name", testing_data.test_handler_in)
        str_handler.handle("test_name", testing_data.test_handler_in_no_lbl)
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
        log_handler.handle("test_name", testing_data.test_handler_in)
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        log_handler = LoggerHandler("log_handler1")
        self.assertEqual(log_handler, log_handler)
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        sys.stdout = tmp

    def test_handlers_management(self):
        length = len(profile_publisher._handlers)
        log1 = LoggerHandler("log_handler1")
        profile_publisher.add_handler(log1)
        log2 = LoggerHandler("log_handler2")
        profile_publisher.add_handler(log2)
        self.assertEqual(len(profile_publisher._handlers), length + 2)
        profile_publisher.delete_handler("log_handler1")
        self.assertEqual(profile_publisher._handlers.get("log_handler1"), None)
        profile_publisher.delete_handlers()
        self.assertEqual(profile_publisher._handlers, {})

    @patch(
        "src.phanos.publisher.BlockingPublisher",
    )
    def test_rabbit_handler(self, BlockingPublisher):
        handler = RabbitMQHandler("rabbit")
        resp = handler.handle(testing_data.test_handler_in)
        print(resp)


class TestTimeProfiling(unittest.TestCase):
    app: Flask
    client: FlaskClient
    context: AppContext

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = app
        cls.client = cls.app.test_client()

    def tearDown(self) -> None:
        pass

    def test_metric_management(self):
        length = len(profile_publisher._metrics)
        hist = Histogram("name", "units")
        profile_publisher.add_metric(hist)
        hist1 = Histogram("name1", "units")
        profile_publisher.add_metric(hist1)
        self.assertEqual(len(profile_publisher._metrics), length + 2)
        profile_publisher.delete_metric("name")
        self.assertEqual(len(profile_publisher._metrics), length + 1)
        self.assertEqual(profile_publisher._metrics.get("name"), None)
        profile_publisher.delete_metric(publisher.TIME_PROFILER)
        self.assertEqual(profile_publisher._metrics.get(publisher.TIME_PROFILER), None)
        self.assertEqual(profile_publisher.time_profile, None)
        profile_publisher.delete_metrics()
        self.assertEqual(len(profile_publisher._metrics), 1)
        self.assertIsNotNone(profile_publisher.resp_size_profile, None)
        self.assertIsNotNone(profile_publisher._metrics.get(publisher.RESPONSE_SIZE))
        profile_publisher.delete_metrics(
            rm_time_profile=True, rm_resp_size_profile=True
        )
        self.assertEqual(profile_publisher._metrics, {})
        self.assertEqual(profile_publisher._metrics.get(publisher.RESPONSE_SIZE), None)

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
                "observe",
                "test:method",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                hist_no_lbl.store_operation,
                "nonexistent",
                "test:method",
                2.0,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                hist_no_lbl.store_operation,
                "observe",
                "test:method",
                "asd",
            )
            # valid operation
            hist_no_lbl.store_operation("observe", "test:method", 2.0),
            self.assertEqual(hist_no_lbl._to_records(), testing_data.hist_no_lbl)

            hist_w_lbl = Histogram("hist_w_lbl", "V", labels=["test"])

            # missing label
            self.assertRaises(
                ValueError,
                hist_w_lbl.store_operation,
                "observe",
                "test:method",
                2.0,
            )

            # default operation
            hist_w_lbl.store_operation(
                method="test:method", value=2.0, label_values={"test": "test"}
            )
            self.assertEqual(hist_w_lbl._to_records(), testing_data.hist_w_lbl)

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
                "observe",
                "test:method",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                sum_no_lbl.store_operation,
                "nonexistent",
                "test:method",
                2.0,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                sum_no_lbl.store_operation,
                "observe",
                "test:method",
                "asd",
            )
            # valid operation
            sum_no_lbl.store_operation("observe", "test:method", 2.0),
            self.assertEqual(sum_no_lbl._to_records(), testing_data.sum_no_lbl)

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
                "inc",
                "test:method",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                cnt_no_lbl.store_operation,
                "inc",
                "test:method",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                cnt_no_lbl.store_operation,
                "inc",
                "test:method",
                -1,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                cnt_no_lbl.store_operation,
                "nonexistent",
                "test:method",
                2.0,
            )

            # valid operation
            cnt_no_lbl.store_operation("inc", "test:method", 2.0),
            self.assertEqual(cnt_no_lbl._to_records(), testing_data.cnt_no_lbl)

    def test_info(self):
        with app.test_request_context():
            inf_no_lbl = Info(
                "inf_no_lbl",
            )
            # invalid value type
            self.assertRaises(
                ValueError,
                inf_no_lbl.store_operation,
                "info",
                "test:method",
                "asd",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                inf_no_lbl.store_operation,
                "nonexistent",
                "test:method",
                2.0,
            )

            # valid operation
            inf_no_lbl.store_operation("info", "test:method", {"value": "asd"}),
            self.assertEqual(inf_no_lbl._to_records(), testing_data.inf_no_lbl)

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
                "inc",
                "test:method",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "inc",
                "test:method",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "inc",
                "test:method",
                -1,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "dec",
                "test:method",
                -1,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "set",
                "test:method",
                False,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                gauge_no_lbl.store_operation,
                "nonexistent",
                "test:method",
                2.0,
            )

            # valid operation
            gauge_no_lbl.store_operation("inc", "test:method", 2.0),
            gauge_no_lbl.store_operation("dec", "test:method", 2.0),
            gauge_no_lbl.store_operation("set", "test:method", 2.0),
            self.assertEqual(gauge_no_lbl._to_records(), testing_data.gauge_no_lbl)

    def test_enum(self):
        with app.test_request_context():
            enum_no_lbl = Enum(
                "enum_no_lbl",
                ["true", "false"],
            )
            # invalid value
            self.assertRaises(
                TypeError,
                enum_no_lbl.store_operation,
                "state",
                "test:method",
                "maybe",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                enum_no_lbl.store_operation,
                "nonexistent",
                "test:method",
                "true",
            )

            # valid operation
            enum_no_lbl.store_operation("state", "test", "true")
            self.assertEqual(enum_no_lbl._to_records(), testing_data.enum_no_lbl)

    @patch("src.phanos.publisher.BlockingPublisher")
    def test_profiles_publish(self, BlockingPublisher):
        handler = StreamHandler("test:method")
        profile_publisher.add_handler(handler)
        io = StringIO()
        handler = StreamHandler("test1", io)
        profile_publisher.add_handler(handler)

        _ = self.client.get("http://localhost/api/dummy/one")

        # io.seek(0)
        # print(io.readline())

    @patch("src.phanos.publisher.BlockingPublisher")
    def test_custom_profile_addition(self, BlockingPublisher):
        pass

    """
     @patch("src.phanos.publisher.BlockingPublisher")
    def test_profiles_publish(self, BlockingPublisher):
        profile_publisher._logger.setLevel(10)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(10)
        profile_publisher._logger.addHandler(handler)
        backup = sys.stdout
        sys.stdout = StringIO()
        _ = self.client.get("http://localhost/api/dummy/one")
        out = sys.stdout
        out.seek(0)
        lines = out.readlines()
        time_lines = lines[-5:-1]
        size_line = lines[-1]
        sys.stdout = backup
        for i in range(len(time_lines)):
            line = time_lines[i][16:-1]
            line = ast.literal_eval(line)
            self.assertEqual(
                (float(line["value"][1])) // 100,
                testing_data.time_profile_out[i]["value"][1],
            )
            line["value"] = ""
            testing_data.time_profile_out[i]["value"] = ""
            self.assertEqual(line, testing_data.time_profile_out[i])

        size_line = size_line[16:-1]
        size_line = ast.literal_eval(size_line)
        self.assertEqual(size_line, testing_data.resp_size_out)

        self.assertEqual(profile_publisher._current_node, profile_publisher._root)
        self.assertEqual(profile_publisher._root.children, [])
        
        
            @patch("src.phanos.publisher.BlockingPublisher")
    def test_custom_profile_addition(self, BlockingPublisher):
        profile_publisher.create_publisher()
        profile_publisher._logger.setLevel(10)
        backup = sys.stdout
        sys.stdout = StringIO()
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(10)
        profile_publisher._logger.addHandler(handler)

        hist = Histogram("new_name", "asd")
        self.assertEqual(len(profile_publisher._metrics), 2)
        profile_publisher.add_metric(hist)
        self.assertEqual(len(profile_publisher._metrics), 3)
        profile_publisher.delete_metric("time_profiler")
        profile_publisher.delete_metric("response_size")
        self.assertEqual(len(profile_publisher._metrics), 1)

        sys.stdout = backup

    """
