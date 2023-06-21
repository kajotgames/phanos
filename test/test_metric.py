import logging
import unittest
from io import StringIO
import sys
import ast
from unittest.mock import patch

from flask import Flask
from flask.ctx import AppContext
from flask.testing import FlaskClient

from src.phanos import profile_publisher
from src.phanos.publisher import StreamHandler, RabbitMQHandler
from test import testing_data
from test.dummy_api import app
from src.phanos.metrics import (
    Histogram,
    Summary,
    Counter,
    Info,
    Gauge,
    Enum,
)


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
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                hist_no_lbl.store_operation,
                "nonexistent",
                2.0,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                hist_no_lbl.store_operation,
                "observe",
                "asd",
            )
            # valid operation
            hist_no_lbl.store_operation("observe", 2.0),
            self.assertEqual(hist_no_lbl._to_records(), testing_data.hist_no_lbl)

            hist_w_lbl = Histogram("hist_w_lbl", "V", labels=["test"])

            # missing label
            self.assertRaises(
                ValueError,
                hist_w_lbl.store_operation,
                "observe",
                2.0,
            )

            # default operation
            hist_w_lbl.store_operation(value=2.0, label_values={"test": "test"})
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
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                sum_no_lbl.store_operation,
                "nonexistent",
                2.0,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                sum_no_lbl.store_operation,
                "observe",
                "asd",
            )
            # valid operation
            sum_no_lbl.store_operation("observe", 2.0),
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
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                cnt_no_lbl.store_operation,
                "inc",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                cnt_no_lbl.store_operation,
                "inc",
                -1,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                cnt_no_lbl.store_operation,
                "nonexistent",
                2.0,
            )

            # valid operation
            cnt_no_lbl.store_operation("inc", 2.0),
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
                "asd",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                inf_no_lbl.store_operation,
                "nonexistent",
                2.0,
            )

            # valid operation
            inf_no_lbl.store_operation("info", {"value": "asd"}),
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
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "inc",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "inc",
                -1,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "dec",
                -1,
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.store_operation,
                "set",
                False,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                gauge_no_lbl.store_operation,
                "nonexistent",
                2.0,
            )

            # valid operation
            gauge_no_lbl.store_operation("inc", 2.0),
            gauge_no_lbl.store_operation("dec", 2.0),
            gauge_no_lbl.store_operation("set", 2.0),
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
                "maybe",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                enum_no_lbl.store_operation,
                "nonexistent",
                "true",
            )

            # valid operation
            enum_no_lbl.store_operation("state", "true")
            self.assertEqual(enum_no_lbl._to_records(), testing_data.enum_no_lbl)

    @patch("src.phanos.publisher.BlockingPublisher")
    def test_profiles_publish(self, BlockingPublisher):
        handler = StreamHandler("test")
        profile_publisher.add_handler(handler)
        io = StringIO()
        handler = StreamHandler("test1", io)
        profile_publisher.add_handler(handler)

        _ = self.client.get("http://localhost/api/dummy/one")

        io.seek(0)
        print(io.readline())

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
