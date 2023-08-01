import unittest

from flask import Flask
from flask.ctx import AppContext
from flask.testing import FlaskClient

from phanos.metrics import Histogram, Summary, Counter, Info, Gauge, Enum
from test import testing_data
from test.dummy_api import app


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
        # TODO: test time profiling
        pass
