import unittest

from src.phanos.metrics import Histogram, Summary, Counter, Info, Gauge, Enum
from test import testing_data


class TestMetrics(unittest.TestCase):
    def test_histogram(self):
        hist_no_lbl = Histogram(
            "hist_no_lbl",
            "TEST",
            "V",
        )
        # invalid label
        self.assertRaises(
            ValueError,
            hist_no_lbl.observe,
            2.0,
            label_values={"nonexistent": "123"},
        )
        # invalid value
        self.assertRaises(
            TypeError,
            hist_no_lbl.observe,
            "asd",
        )
        hist_no_lbl.cleanup()
        # valid operation
        hist_no_lbl.observe(2.0, None),
        self.assertEqual(hist_no_lbl.to_records(), testing_data.hist_no_lbl)

        hist_w_lbl = Histogram("hist_w_lbl", "TEST", "V", labels=["test"])

        # missing label
        self.assertRaises(
            ValueError,
            hist_w_lbl.observe,
            2.0,
        )
        hist_w_lbl.cleanup()
        # default operation
        hist_w_lbl.observe(2.0, {"test": "test"})
        self.assertEqual(hist_w_lbl.to_records(), testing_data.hist_w_lbl)

    def test_summary(self):
        sum_no_lbl = Summary("sum_no_lbl", "TEST", "V")
        # invalid label
        self.assertRaises(
            ValueError,
            sum_no_lbl.observe,
            2.0,
            {"nonexistent": "123"},
        )
        # invalid value
        self.assertRaises(
            TypeError,
            sum_no_lbl.observe,
            "asd",
        )
        sum_no_lbl.cleanup()
        # valid operation
        sum_no_lbl.observe(2.0, None),
        self.assertEqual(sum_no_lbl.to_records(), testing_data.sum_no_lbl)

    def test_counter(self):
        cnt_no_lbl = Counter(
            "cnt_no_lbl",
            "TEST",
            "V",
        )
        # invalid label
        self.assertRaises(
            ValueError,
            cnt_no_lbl.inc,
            2.0,
            label_values={"nonexistent": "123"},
        )
        # invalid value type
        self.assertRaises(
            TypeError,
            cnt_no_lbl.inc,
            "asd",
        )
        # invalid value
        self.assertRaises(
            TypeError,
            cnt_no_lbl.inc,
            -1,
        )
        cnt_no_lbl.cleanup()

        # valid operation
        cnt_no_lbl.inc(2.0, None),
        self.assertEqual(cnt_no_lbl.to_records(), testing_data.cnt_no_lbl)

    def test_info(self):
        inf_no_lbl = Info(
            "inf_no_lbl",
            "TEST",
        )
        # invalid value type
        self.assertRaises(
            ValueError,
            inf_no_lbl.info_,
            "asd",
        )
        inf_no_lbl.cleanup()
        # valid operation
        inf_no_lbl.info_({"value": "asd"}, None),
        self.assertEqual(inf_no_lbl.to_records(), testing_data.inf_no_lbl)

    def test_gauge(self):
        gauge_no_lbl = Gauge(
            "gauge_no_lbl",
            "TEST",
            "V",
        )
        # invalid label
        self.assertRaises(
            ValueError,
            gauge_no_lbl.inc,
            2.0,
            label_values={"nonexistent": "123"},
        )
        # invalid value type
        self.assertRaises(
            TypeError,
            gauge_no_lbl.inc,
            "asd",
        )
        # invalid value
        self.assertRaises(
            TypeError,
            gauge_no_lbl.inc,
            -1,
        )
        # invalid value
        self.assertRaises(
            TypeError,
            gauge_no_lbl.dec,
            -1,
        )
        # invalid value
        self.assertRaises(
            TypeError,
            gauge_no_lbl.set,
            False,
        )
        gauge_no_lbl.cleanup()
        # valid operation
        gauge_no_lbl.inc(2.0, None),
        gauge_no_lbl.dec(2.0, None),
        gauge_no_lbl.set(2.0, None),
        self.assertEqual(gauge_no_lbl.to_records(), testing_data.gauge_no_lbl)

    def test_enum(self):
        enum_no_lbl = Enum(
            "enum_no_lbl",
            "TEST",
            ["true", "false"],
        )
        # invalid value
        self.assertRaises(
            ValueError,
            enum_no_lbl.state,
            "maybe",
        )

        enum_no_lbl.cleanup()
        # valid operation
        enum_no_lbl.state("true", None)
        self.assertEqual(enum_no_lbl.to_records(), testing_data.enum_no_lbl)

        enum_no_lbl.state("true", None)
        enum_no_lbl.values.pop(0)
        self.assertRaises(RuntimeError, enum_no_lbl.to_records)
