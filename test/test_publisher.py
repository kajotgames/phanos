import unittest
from datetime import datetime
from typing import Optional
from unittest.mock import patch, MagicMock, AsyncMock

from phanos.publisher import Profiler, TIME_PROFILER, RESPONSE_SIZE, AsyncImpProfHandler
from phanos.tree import curr_node


class TestProfiler(unittest.IsolatedAsyncioTestCase):
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

    @patch("phanos.publisher.Profiler.create_response_size_profiler")
    @patch("phanos.publisher.Profiler.create_time_profiler")
    def test_async_config(self, mock_time: MagicMock, mock_size: MagicMock):
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
        metric.label_names = set()

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
        with self.subTest("valid"):
            self.profiler.add_handler(handler)
            self.profiler.add_handler(handler)
            self.assertIn("test", self.profiler.handlers)
            self.assertEqual(self.profiler.handlers["test"], handler)
            self.assertEqual(len(self.profiler.handlers), 1)

        with self.subTest("add async handler to sync profiler"):
            handler = AsyncImpProfHandler("test")
            with self.assertRaises(ValueError):
                self.profiler.add_handler(handler)

        self.profiler.profile_ext = None  # simulates that configuration did not happen
        with self.subTest("not configured"):
            with self.assertRaises(RuntimeError):
                self.profiler.add_handler(handler)

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

    def test_set_error_raised(self):
        self.profiler.time_profile.label_names = {"some_value"}
        self.profiler.error_raised_label = False
        for metric in self.profiler.metrics.values():
            self.assertNotIn("error_raised", metric.label_names)

        self.profiler.error_raised_label = True
        for metric in self.profiler.metrics.values():
            self.assertIn("error_raised", metric.label_names)

    def test_set_curr_node(self):
        node = self.profiler.set_curr_node(lambda: None)
        self.assertEqual(node, curr_node.get())
        self.assertEqual(node.parent, self.profiler.tree.root)
        node2 = self.profiler.set_curr_node(lambda: None)
        self.assertEqual(node, node2.parent)

    def test_delete_curr_node(self):
        node = self.profiler.set_curr_node(lambda: None)
        self.profiler.delete_curr_node(node)
        self.assertEqual(curr_node.get(), self.profiler.tree.root)

        self.profiler.delete_curr_node(node)

    def test_measure_execution_start(self):
        self.assertIsInstance(self.profiler.measure_execution_start(), datetime)
        self.profiler.time_profile = None
        self.assertIsNone(self.profiler.measure_execution_start())

    def test_before_func(self):
        mock_func = MagicMock()

        def dummy_func(func, args, kwargs):
            mock_func()

        self.profiler.before_root_func = dummy_func
        self.profiler.before_func = dummy_func
        self.profiler.set_curr_node(lambda: None)
        x = self.profiler.before_func_profiling(lambda x: x, (), {})
        self.assertEqual(mock_func.call_count, 2)
        self.assertIsInstance(x, datetime)

    def test_after_func(self):
        self.profiler.time_profile = mock_time = MagicMock()
        self.profiler.resp_size_profile = mock_size = MagicMock()
        mock_func = MagicMock()

        def dummy_func(func, args, kwargs):
            mock_func()

        self.profiler.after_func = dummy_func
        self.profiler.after_root_func = dummy_func
        self.profiler.set_curr_node(lambda: None)
        now = datetime.utcnow()
        with self.subTest("all measured"):
            self.profiler.after_function_profiling(1, now, (), {})
            self.assertEqual(mock_func.call_count, 2)
            mock_time.stop.assert_called_once_with(start=now, label_values={})
            mock_size.rec.assert_called_once_with(value=1, label_values={})

        self.profiler.after_func = None
        self.profiler.after_root_func = None
        self.profiler.time_profile = None
        self.profiler.resp_size_profile = None
        mock_func.reset_mock()
        mock_time.reset_mock()
        mock_size.reset_mock()
        with self.subTest("not measured"):
            self.profiler.after_function_profiling(1, now, (), {})
            mock_func.assert_not_called()
            mock_time.stop.assert_not_called()
            mock_size.rec.assert_not_called()

    async def test_profile(self):
        async def dummy_func():
            return

        self.profiler.profile_ext.sync_inner = MagicMock()
        self.profiler.profile_ext.async_inner = AsyncMock()

        with self.subTest("sync"):
            _ = self.profiler.profile(lambda: None)()
            self.profiler.profile_ext.sync_inner.assert_called_once()

        with self.subTest("async"):
            _ = await self.profiler.profile(dummy_func)()
            self.profiler.profile_ext.async_inner.assert_called_once()


class TestSyncProfilerExt(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.profiler = Profiler()
        self.profiler.config(request_size_profile=True)

    def tearDown(self):
        self.profiler = None

    @patch("phanos.publisher.MetricWrapper.to_records")
    @patch("phanos.publisher.MetricWrapper.cleanup")
    def test_handle_records_clear(self, cleanup: MagicMock, to_records: MagicMock):
        with self.subTest("handle"):
            mock_handler = MagicMock()
            mock_handler.handler_name = "test"
            self.profiler.handlers = {"test": mock_handler}
            self.profiler.profile_ext.handle_records_clear()
            self.assertEqual(cleanup.call_count, 2)
            self.assertEqual(to_records.call_count, 2)
            self.assertEqual(mock_handler.handle.call_count, 2)

        with self.subTest("no records"):
            mock_handler.handle.reset_mock()
            to_records.return_value = None
            self.profiler.profile_ext.handle_records_clear()
            self.assertEqual(mock_handler.handle.call_count, 0)

    @patch("phanos.publisher.SyncExtProfiler.handle_records_clear")
    @patch("phanos.publisher.ContextTree.clear")
    def test_force_handle_records_clear(self, mock_clear: MagicMock, mock_handle: MagicMock):
        self.profiler.profile_ext.force_handle_records_clear()
        mock_handle.assert_called_once()
        mock_clear.assert_called_once()

    @patch("phanos.publisher.SyncExtProfiler.handle_records_clear")
    def test_sync_inner(self, mock_handle: MagicMock):
        func = lambda: None
        with patch.object(self.profiler.profile_ext, "base_profiler") as mock_base:
            mock_base.needs_profiling.return_value = False
            with self.subTest("no profile"):
                self.profiler.profile_ext.sync_inner(func)
                mock_base.set_curr_node.assert_not_called()

            mock_base.get_records_count.return_value = self.profiler.RECORDS_LEN_LIMIT
            mock_base.needs_profiling.return_value = True
            with self.subTest("profile"):
                self.profiler.profile_ext.sync_inner(func)
                mock_base.set_curr_node.assert_called_once_with(func)
                mock_base.before_func_profiling.assert_called_once_with(func, (), {})
                mock_base.after_function_profiling.assert_called_once_with(
                    None, mock_base.before_func_profiling.return_value, (), {}
                )
                mock_handle.assert_called_once()
                mock_base.delete_curr_node.assert_called_once()

            func = lambda x: x[0]
            mock_base.reset_mock()
            mock_handle.reset_mock()
            with self.subTest("error handling"):
                with self.assertRaises(IndexError):
                    self.profiler.profile_ext.sync_inner(func, [])
                    mock_base.after_function_profiling.assert_called_once()
                    mock_base.delete_curr_node.assert_called_once()
                    mock_handle.assert_called_once()

    @patch("phanos.publisher.SyncExtProfiler.handle_records_clear")
    async def test_async_inner(self, mock_handle: MagicMock):
        async def func(x):
            return x[0]

        with patch.object(self.profiler.profile_ext, "base_profiler") as mock_base:
            mock_base.needs_profiling.return_value = False
            with self.subTest("no profile"):
                await self.profiler.profile_ext.async_inner(func, [1])
                mock_base.set_curr_node.assert_not_called()

            mock_base.get_records_count.return_value = self.profiler.RECORDS_LEN_LIMIT
            mock_base.needs_profiling.return_value = True
            with self.subTest("profile"):
                await self.profiler.profile_ext.async_inner(func, [1])
                mock_base.set_curr_node.assert_called_once_with(func)
                mock_base.before_func_profiling.assert_called_once_with(func, ([1],), {})
                mock_base.after_function_profiling.assert_called_once_with(
                    1, mock_base.before_func_profiling.return_value, ([1],), {}
                )
                mock_handle.assert_called_once()
                mock_base.delete_curr_node.assert_called_once()

            func = lambda x: x[0]
            mock_base.reset_mock()
            mock_handle.reset_mock()
            with self.subTest("error handling"):
                with self.assertRaises(IndexError):
                    await self.profiler.profile_ext.async_inner(func, [])
                    mock_base.after_function_profiling.assert_called_once()
                    mock_base.delete_curr_node.assert_called_once()
                    mock_handle.assert_called_once()


class TestAsyncProfilerExt(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.profiler = Profiler()
        self.profiler.async_config(request_size_profile=True)

    def tearDown(self):
        self.profiler = None

    @patch("phanos.publisher.MetricWrapper.to_records")
    @patch("phanos.publisher.MetricWrapper.cleanup")
    @patch("phanos.publisher.AsyncImpProfHandler.handle")
    async def test_handle_records_clear(self, async_handle: MagicMock, cleanup: MagicMock, to_records: MagicMock):
        with self.subTest("handle"):
            mock_handler = MagicMock()
            mock_handler.handler_name = "test"
            async_handler = AsyncImpProfHandler("test")
            self.profiler.handlers = {"test": mock_handler, "next": async_handler}
            await self.profiler.profile_ext.handle_records_clear()
            self.assertEqual(cleanup.call_count, 2)
            self.assertEqual(to_records.call_count, 2)
            self.assertEqual(mock_handler.handle.call_count, 2)
            self.assertEqual(async_handle.call_count, 2)

        with self.subTest("no records"):
            mock_handler.handle.reset_mock()
            to_records.return_value = None
            await self.profiler.profile_ext.handle_records_clear()
            self.assertEqual(mock_handler.handle.call_count, 0)

    @patch("phanos.publisher.AsyncExtProfiler.handle_records_clear")
    @patch("phanos.publisher.ContextTree.clear")
    async def test_force_handle_records_clear(self, mock_clear: MagicMock, mock_handle: MagicMock):
        await self.profiler.profile_ext.force_handle_records_clear()
        mock_handle.assert_called_once()
        mock_clear.assert_called_once()

    def test_sync_inner(self):
        func = lambda: None
        with patch.object(self.profiler.profile_ext, "base_profiler") as mock_base:
            mock_base.needs_profiling.return_value = False
            with self.subTest("no profile"):
                self.profiler.profile_ext.sync_inner(func)
                mock_base.set_curr_node.assert_not_called()

            mock_base.get_records_count.return_value = self.profiler.RECORDS_LEN_LIMIT
            mock_base.needs_profiling.return_value = True
            with self.subTest("profile"):
                self.profiler.profile_ext.sync_inner(func)
                mock_base.set_curr_node.assert_called_once_with(func)
                mock_base.before_func_profiling.assert_called_once_with(func, (), {})
                mock_base.after_function_profiling.assert_called_once_with(
                    None, mock_base.before_func_profiling.return_value, (), {}
                )
                mock_base.delete_curr_node.assert_called_once()

            func = lambda x: x[0]
            mock_base.reset_mock()
            mock_base.get_records_count.return_value = self.profiler.RECORDS_ERR_LIMIT
            mock_base.metrics.values.return_value = [MagicMock()]
            with self.subTest("error handling"):
                with self.assertRaises(IndexError):
                    self.profiler.profile_ext.sync_inner(func, [])
                    mock_base.after_function_profiling.assert_called_once()
                    mock_base.delete_curr_node.assert_called_once()
                    mock_base.metrics.values.assert_called_once()

    @patch("phanos.publisher.AsyncExtProfiler.handle_records_clear")
    async def test_async_inner(self, mock_handle: MagicMock):
        async def func(x):
            return x[0]

        with patch.object(self.profiler.profile_ext, "base_profiler") as mock_base:
            mock_base.needs_profiling.return_value = False
            with self.subTest("no profile"):
                await self.profiler.profile_ext.async_inner(func, [1])
                mock_base.set_curr_node.assert_not_called()

            mock_base.get_records_count.return_value = self.profiler.RECORDS_LEN_LIMIT
            mock_base.needs_profiling.return_value = True
            with self.subTest("profile"):
                await self.profiler.profile_ext.async_inner(func, [1])
                mock_base.set_curr_node.assert_called_once_with(func)
                mock_base.before_func_profiling.assert_called_once_with(func, ([1],), {})
                mock_base.after_function_profiling.assert_called_once_with(
                    1, mock_base.before_func_profiling.return_value, ([1],), {}
                )
                mock_handle.assert_called_once()
                mock_base.delete_curr_node.assert_called_once()

            func = lambda x: x[0]
            mock_base.reset_mock()
            mock_handle.reset_mock()
            with self.subTest("error handling"):
                with self.assertRaises(IndexError):
                    await self.profiler.profile_ext.async_inner(func, [])
                    mock_base.after_function_profiling.assert_called_once()
                    mock_base.delete_curr_node.assert_called_once()
                    mock_handle.assert_called_once()
