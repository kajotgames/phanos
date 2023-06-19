import unittest
from io import StringIO
from time import sleep
import sys
import ast

from flask import Flask, current_app
from flask.ctx import AppContext
from flask.testing import FlaskClient

from src.phanos.main import publisher
from tests import test_data
from tests.dummy_api import app
from src.phanos.metrics import (
    TimeProfiler,
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

    def test_profiles_publish(self):
        backup = sys.stdout
        sys.stdout = StringIO()
        _ = self.client.get("http://localhost/api/dummy/one")
        out = sys.stdout
        out.seek(0)
        lines = out.readlines()
        lines = lines[-4:]
        sys.stdout = backup
        for i in range(len(lines)):
            line = lines[i][16:-1]
            line = ast.literal_eval(line)
            self.assertEqual(
                (float(line["value"][1])) // 100,
                test_data.time_profile_out[i]["value"][1],
            )
            line["value"] = ""
            test_data.time_profile_out[i]["value"] = ""
            self.assertEqual(line, test_data.time_profile_out[i])

        self.assertEqual(publisher.current_node, publisher.root)
        self.assertEqual(publisher.root.children, [])

    def test_histogram(self):
        with app.test_request_context():
            hist_no_lbl = Histogram(
                "hist_no_lbl",
                "V",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                hist_no_lbl.record_op,
                "observe",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                hist_no_lbl.record_op,
                "nonexistent",
                2.0,
            )
            # valid operation
            hist_no_lbl.record_op("observe", 2.0),
            self.assertEqual(hist_no_lbl._to_records(), test_data.hist_no_lbl)

            hist_w_lbl = Histogram("hist_w_lbl", "V", labels=["test"])

            # missing label
            self.assertRaises(
                ValueError,
                hist_w_lbl.record_op,
                "observe",
                2.0,
            )

            # valid operation
            hist_w_lbl.record_op("observe", 2.0, label_values={"test": "test"})
            self.assertEqual(hist_w_lbl._to_records(), test_data.hist_w_lbl)

    def test_summary(self):
        with app.test_request_context():
            sum_no_lbl = Summary(
                "sum_no_lbl",
                "V",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                sum_no_lbl.record_op,
                "observe",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                sum_no_lbl.record_op,
                "nonexistent",
                2.0,
            )
            # valid operation
            sum_no_lbl.record_op("observe", 2.0),
            self.assertEqual(sum_no_lbl._to_records(), test_data.sum_no_lbl)

    def test_counter(self):
        with app.test_request_context():
            cnt_no_lbl = Counter(
                "cnt_no_lbl",
                "V",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                cnt_no_lbl.record_op,
                "inc",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                cnt_no_lbl.record_op,
                "inc",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                cnt_no_lbl.record_op,
                "inc",
                -1,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                cnt_no_lbl.record_op,
                "nonexistent",
                2.0,
            )

            # valid operation
            cnt_no_lbl.record_op("inc", 2.0),
            self.assertEqual(cnt_no_lbl._to_records(), test_data.cnt_no_lbl)

    def test_info(self):
        with app.test_request_context():
            inf_no_lbl = Info(
                "inf_no_lbl",
                "V",
            )
            # invalid value type
            self.assertRaises(
                ValueError,
                inf_no_lbl.record_op,
                "info",
                "asd",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                inf_no_lbl.record_op,
                "nonexistent",
                2.0,
            )

            # valid operation
            inf_no_lbl.record_op("info", {"value": "asd"}),
            self.assertEqual(inf_no_lbl._to_records(), test_data.inf_no_lbl)

    def test_gauge(self):
        with app.test_request_context():
            gauge_no_lbl = Gauge(
                "gauge_no_lbl",
                "V",
            )
            # invalid label
            self.assertRaises(
                ValueError,
                gauge_no_lbl.record_op,
                "inc",
                2.0,
                label_values={"nonexistent": "123"},
            )
            # invalid value type
            self.assertRaises(
                TypeError,
                gauge_no_lbl.record_op,
                "inc",
                "asd",
            )
            # invalid value
            self.assertRaises(
                TypeError,
                gauge_no_lbl.record_op,
                "inc",
                -1,
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                gauge_no_lbl.record_op,
                "nonexistent",
                2.0,
            )

            # valid operation
            gauge_no_lbl.record_op("inc", 2.0),
            gauge_no_lbl.record_op("dec", 2.0),
            gauge_no_lbl.record_op("set", 2.0),
            self.assertEqual(gauge_no_lbl._to_records(), test_data.gauge_no_lbl)

    def test_enum(self):
        with app.test_request_context():
            enum_no_lbl = Enum(
                "enum_no_lbl",
                ["true", "false"],
            )
            # invalid value
            self.assertRaises(
                TypeError,
                enum_no_lbl.record_op,
                "state",
                "maybe",
            )
            # invalid operation
            self.assertRaises(
                ValueError,
                enum_no_lbl.record_op,
                "nonexistent",
                "true",
            )

            # valid operation
            enum_no_lbl.record_op("state", "true")
            self.assertEqual(enum_no_lbl._to_records(), test_data.enum_no_lbl)
