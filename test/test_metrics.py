import datetime
import unittest
from unittest.mock import Mock, patch, MagicMock

from src.phanos.metrics import (
    Histogram,
    Summary,
    Counter,
    Info,
    Gauge,
    Enum,
    MetricWrapper,
    StoreOperationDecorator,
    TimeProfiler,
    ResponseSize,
    InvalidValueError,
)


class TestStoreOperationDecorator(unittest.TestCase):
    def setUp(self):
        self.operation_mock = Mock()
        self.operation_mock.__qualname__ = "mocked_method"

    @patch("src.phanos.metrics.curr_node", Mock(get=Mock(return_value=Mock(ctx=Mock(value="mocked_value")))))
    def test_successful_execution(self):
        # Create an instance of MetricWrapper
        metric_instance = MetricWrapper("test_metric", "TEST", "V", ["error_raised"])
        metric_instance.values = [("observe", 1)]

        # Apply the decorator to a test function
        decorated_function = StoreOperationDecorator(self.operation_mock).wrapper
        decorated_function(metric_instance, value=42)

        # Assert that the operation method was called with the correct arguments
        self.operation_mock.assert_called_once_with(metric_instance, 42, {"error_raised": False})

        # Assert that the values, label_values, and method lists are updated
        self.assertEqual(metric_instance.values, [("observe", 1)])
        self.assertEqual(metric_instance.label_values, [{"error_raised": False}])
        self.assertEqual(metric_instance.method, ["mocked_value"])

    @patch("src.phanos.metrics.curr_node", Mock(get=Mock(return_value=Mock(ctx=Mock(value="mocked_value")))))
    def test_invalid_labels(self):
        # Create an instance of MetricWrapper
        metric_instance = MetricWrapper("test_metric", "TEST", "V", ["label1", "label2"])
        decorated_function = StoreOperationDecorator(self.operation_mock).wrapper
        decorated_function(metric_instance, value=42, label_values={"invalid_label": "value"})
        self.assertEqual(len(metric_instance.label_values), 0)
        self.assertEqual(len(metric_instance.values), 0)
        self.assertEqual(len(metric_instance.method), 0)

    @patch("src.phanos.metrics.curr_node", Mock(get=Mock(side_effect=LookupError)))
    def test_ctx_not_found(self):
        metric_instance = MetricWrapper("test_metric", "TEST", "V")
        decorated_function = StoreOperationDecorator(self.operation_mock).wrapper
        decorated_function(metric_instance, value=42)
        self.assertEqual(len(metric_instance.label_values), 0)
        self.assertEqual(len(metric_instance.method), 0)
        self.assertEqual(len(metric_instance.values), 0)

    @patch("src.phanos.metrics.curr_node", Mock(get=Mock(return_value=Mock(ctx=Mock(value="mocked_value")))))
    def test_operation_raised(self):
        metric_instance = MetricWrapper("test_metric", "TEST", "V")
        self.operation_mock.side_effect = InvalidValueError("Float")
        decorated_function = StoreOperationDecorator(self.operation_mock).wrapper
        decorated_function(metric_instance, value=42)
        self.assertEqual(len(metric_instance.label_values), 0)
        self.assertEqual(len(metric_instance.method), 0)
        self.assertEqual(len(metric_instance.values), 0)

    @patch("src.phanos.metrics.curr_node", Mock(get=Mock(return_value=Mock(ctx=Mock(value="mocked_value")))))
    def test_operation_not_stored(self):
        metric_instance = MetricWrapper("test_metric", "TEST", "V")
        decorated_function = StoreOperationDecorator(self.operation_mock).wrapper
        decorated_function(metric_instance, value=42)

        # assert that last `label_value` and `method` was cleared
        self.assertEqual(len(metric_instance.label_values), 0)
        self.assertEqual(len(metric_instance.method), 0)
        self.assertEqual(len(metric_instance.values), 0)


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.tmp = StoreOperationDecorator.wrapper
        # monkey patch StoreOperationDecorator.wrapper to just call desired operation
        # I didn't find out another way how to test this
        StoreOperationDecorator.wrapper = lambda self_, *args, **kwargs: self_.operation(*args, **kwargs)

    def tearDown(self):
        StoreOperationDecorator.wrapper = self.tmp

    def test_metric_wrapper(self):
        metric = MetricWrapper("test_metric", "TEST", "V", ["test", "test2"])

        metric.method = ["X:y", "X:z"]
        metric.values = [("observe", 1), ("observe", 2)]
        metric.label_values = [{"test": "test", "test2": "test2"}, {"test": "test", "test2": "test2"}]
        with self.subTest("TO RECORDS VALID"):
            metric.metric = "histogram"
            r = metric.to_records()
            self.assertEqual(len(r), 2)
            self.assertEqual(r[0]["item"], "X")
            self.assertEqual(r[0]["method"], "X:y")
            self.assertEqual(r[0]["value"], ("observe", 1))
            self.assertEqual(r[0]["labels"], {"test": "test", "test2": "test2"})

        metric.method = metric.method[:1]
        with self.subTest("TO RECORDS INVALID"):
            r = metric.to_records()
            self.assertIsNone(r)

        with self.subTest("CHECK LABELS"):
            self.assertTrue(metric.check_labels(["test", "test2"]))
            self.assertFalse(metric.check_labels(["test", "invalid"]))

        with self.subTest("CLEANUP"):
            metric.cleanup()
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.values, [])
            self.assertEqual(metric.label_values, [])

    def test_histogram(self):
        hist = Histogram(
            "hist_no_lbl",
            "TEST",
            "V",
        )
        self.assertEqual(hist.metric, "histogram")
        with self.assertRaises(InvalidValueError):
            hist.observe("asd", None)
        hist.observe(2.0, None)
        self.assertEqual(hist.values, [("observe", 2.0)])

    def test_summary(self):
        sum_ = Summary(
            "hist_no_lbl",
            "TEST",
            "V",
        )
        self.assertEqual(sum_.metric, "summary")
        with self.assertRaises(InvalidValueError):
            sum_.observe("asd", None)
        sum_.observe(2.0, None)
        self.assertEqual(sum_.values, [("observe", 2.0)])

    def test_counter(self):
        cnt = Counter(
            "hist_no_lbl",
            "TEST",
            "V",
        )
        self.assertEqual(cnt.metric, "counter")
        with self.assertRaises(InvalidValueError):
            cnt.inc("asd", None)
        cnt.inc(2.0, None)
        self.assertEqual(cnt.values, [("inc", 2.0)])

    def test_info(self):
        inf = Info(
            "hist_no_lbl",
            "TEST",
        )
        self.assertEqual(inf.metric, "info")
        self.assertEqual(inf.units, "info")
        with self.assertRaises(InvalidValueError):
            inf.info_("asd", None)
        inf.info_({"x": "y"}, None)
        self.assertEqual(inf.values, [("info", {"x": "y"})])

    def test_gauge(self):
        g = Gauge(
            "hist_no_lbl",
            "TEST",
            "V",
        )
        self.assertEqual(g.metric, "gauge")
        with self.assertRaises(InvalidValueError):
            g.inc("asd", None)
        with self.assertRaises(InvalidValueError):
            g.inc(-1.2, None)
        g.inc(2.0, None)
        self.assertEqual(g.values, [("inc", 2.0)])
        g.values = []

        with self.assertRaises(InvalidValueError):
            g.dec("asd", None)
        with self.assertRaises(InvalidValueError):
            g.dec(-1.2, None)
        g.dec(2.0, None)
        self.assertEqual(g.values, [("dec", 2.0)])
        g.values.clear()

        with self.assertRaises(InvalidValueError):
            g.set("set", None)
        g.set(2.0, None)
        self.assertEqual(g.values, [("set", 2.0)])
        g.values.clear()

    def test_enum(self):
        enum = Enum(
            "hist_no_lbl",
            "TEST",
            ["x", "y"],
        )
        self.assertEqual(enum.metric, "enum")
        self.assertEqual(enum.units, "enum")
        with self.assertRaises(InvalidValueError):
            enum.state("asd", None)
        enum.state("x", None)
        self.assertEqual(enum.values, [("state", "x")])

    @patch("src.phanos.metrics.Histogram.observe")
    def test_time_profiler(self, mock_observe: MagicMock):
        time = TimeProfiler("test", "TEST")
        time.stop(datetime.datetime.now(), {})
        self.assertEqual(mock_observe.call_count, 1)

    @patch("src.phanos.metrics.Histogram.observe")
    def test_response_size(self, mock_observe: MagicMock):
        time = ResponseSize("test", "TEST")
        time.rec("asd", {})
        self.assertEqual(mock_observe.call_count, 1)
