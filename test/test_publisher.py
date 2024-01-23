import unittest
from typing import Optional
from unittest.mock import patch, MagicMock

from phanos.publisher import Profiler, TIME_PROFILER, RESPONSE_SIZE
from phanos.tree import curr_node


class TestProfiler(unittest.TestCase):
    profiler: Optional[Profiler] = None

    def setUp(self):
        self.profiler = Profiler()
        self.profiler.config(request_size_profile=True)

    def tearDown(self):
        self.profiler = None

    @patch("phanos.publisher.Profiler.create_response_size_profiler")
    @patch("phanos.publisher.Profiler.create_time_profiler")
    def test_config(self, mock_time: MagicMock, mock_size: MagicMock):
        profiler = Profiler()
        profiler.config(request_size_profile=True)
        self.assertTrue(profiler.handle_records)
        self.assertIsNotNone(profiler.job)
        self.assertTrue(profiler.error_raised_label)
        mock_size.assert_called_once()
        mock_time.assert_called_once()

    def test_create_profilers(self):
        self.profiler.metrics = {}
        self.profiler.time_profile = None
        self.profiler.resp_size_profile = None

        self.profiler.create_time_profiler()
        self.assertIsNotNone(self.profiler.time_profile)
        self.assertIn(TIME_PROFILER, self.profiler.metrics)

        self.profiler.create_response_size_profiler()
        self.assertIsNotNone(self.profiler.resp_size_profile)
        self.assertIn(RESPONSE_SIZE, self.profiler.metrics)

    def test_delete_metric(self):
        self.profiler.delete_metric("response_size")
        self.assertIsNone(self.profiler.resp_size_profile)
        self.assertNotIn(RESPONSE_SIZE, self.profiler.metrics)

        self.profiler.delete_metric("time_profiler")
        self.assertIsNone(self.profiler.time_profile)
        self.assertNotIn(TIME_PROFILER, self.profiler.metrics)

        self.profiler.metrics["test"] = MagicMock()
        self.profiler.delete_metric("test")
        self.assertNotIn("test", self.profiler.metrics)

        self.profiler.delete_metric("unknown")
        self.assertNotIn("unknown", self.profiler.metrics)

    def test_delete_metrics(self):
        self.profiler.metrics["test"] = MagicMock()
        self.profiler.delete_metrics(True, False)
        self.assertNotIn("test", self.profiler.metrics)
        self.assertNotIn(TIME_PROFILER, self.profiler.metrics)
        self.assertIn(RESPONSE_SIZE, self.profiler.metrics)

    @patch("phanos.publisher.MetricWrapper.cleanup")
    def test_clear(self, mock_cleanup: MagicMock):
        self.profiler.clear()
        self.assertEqual(mock_cleanup.call_count, 2)
        self.assertEqual(curr_node.get(), self.profiler.tree.root)

    def test_add_metric(self):
        self.profiler.metrics = {}
        metric = MagicMock()
        metric.name = "test"
        metric.label_names = []

        self.profiler.add_metric(metric)
        self.profiler.add_metric(metric)

        self.assertIn("test", self.profiler.metrics)
        self.assertIn("error_raised", metric.label_names)

    def test_get_records_count(self):
        self.profiler.time_profile.values = [1.1, 1.1, 1.1]
        self.profiler.resp_size_profile.values = [1.1, 1.1, 1.1]
        self.assertEqual(self.profiler.get_records_count(), 6)

    def test_add_handler(self):
        self.profiler.handlers = {}
        handler = MagicMock()
        handler.handler_name = "test"
        self.profiler.add_handler(handler)
        self.profiler.add_handler(handler)
        self.assertIn("test", self.profiler.handlers)

    def test_delete_handler(self):
        self.profiler.handlers = {}
        handler = MagicMock()
        handler.handler_name = "test"
        self.profiler.add_handler(handler)
        self.profiler.delete_handler("test")
        self.profiler.delete_handler("test")
        self.assertNotIn("test", self.profiler.handlers)

    def test_delete_handlers(self):
        self.profiler.delete_handlers()
        self.assertEqual(len(self.profiler.handlers), 0)

    @patch("phanos.publisher.MetricWrapper.to_records")
    @patch("phanos.publisher.MetricWrapper.cleanup")
    def test_handle_records_clear(self, cleanup: MagicMock, to_records: MagicMock):
        mock_handler = MagicMock()
        mock_handler.handler_name = "test"
        self.profiler.handlers = {"test": mock_handler}
        self.profiler.handle_records_clear()
        self.assertEqual(cleanup.call_count, 2)
        self.assertEqual(to_records.call_count, 2)
        self.assertEqual(mock_handler.handle.call_count, 2)

        mock_handler.handle.reset_mock()
        to_records.return_value = None
        self.profiler.handle_records_clear()
        self.assertEqual(mock_handler.handle.call_count, 0)

    @patch("phanos.publisher.Profiler.handle_records_clear")
    @patch("phanos.publisher.ContextTree.clear")
    def test_force_handle_records_clear(self, mock_clear: MagicMock, mock_handle: MagicMock):
        self.profiler.force_handle_records_clear()
        mock_handle.assert_called_once()
        mock_clear.assert_called_once()

    def test_set_error_raised(self):
        self.profiler.time_profile.label_names = ["some_value"]
        self.profiler.error_raised_label = False
        for metric in self.profiler.metrics.values():
            self.assertNotIn("error_raised", metric.label_values)
