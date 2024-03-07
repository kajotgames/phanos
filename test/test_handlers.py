import copy
import logging
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock, AsyncMock

from pika.adapters.utils.connection_workflow import AMQPConnectorException

from phanos.publisher import (
    BaseHandler,
    ImpProfHandler,
    LoggerHandler,
    NamedLoggerHandler,
    StreamHandler,
    OutputFormatter,
    log_error_profiling,
    AsyncImpProfHandler,
)
from test import testing_data


class TestOutputFormatter(unittest.TestCase):
    def test_record_to_str(self):
        record = testing_data.test_handler_in
        r = OutputFormatter().record_to_str("test_name", record)
        self.assertEqual(
            r,
            testing_data.test_handler_out[:-1],
        )

    def test_log_error_profiling(self):
        record = copy.deepcopy(testing_data.test_handler_in)
        records = [record, record]
        handler = MagicMock()
        mock_rec_to_str = handler.formatter.record_to_str
        mock_rec_to_str.return_value = ""
        with self.subTest("error raised"):
            log_error_profiling("test_name", handler.formatter, handler.logger, records)
            self.assertEqual(mock_rec_to_str.call_count, 2)
            mock_rec_to_str.assert_called_with("test_name", records[0])

        with self.subTest("error not raised"):
            record["labels"]["error_raised"] = "False"
            mock_rec_to_str.reset_mock()
            log_error_profiling("test_name", handler.formatter, handler.logger, records)
            mock_rec_to_str.assert_not_called()

        with self.subTest("error_raised not in labels"):
            _ = record["labels"].pop("error_raised", None)
            log_error_profiling("test_name", handler.formatter, handler.logger, records)
            mock_rec_to_str.assert_not_called()


class TestImpProfHandler(unittest.TestCase):
    def test_base_handler_init(self):
        base = BaseHandler("test_handler")
        self.assertEqual(base.handler_name, "test_handler")

    @patch("phanos.publisher.BlockingPublisher")
    def test_init(self, mock_publisher: MagicMock):
        handler = ImpProfHandler("rabbit")
        mock_publisher.assert_called_once()
        mock_publisher.return_value.connect.assert_called_once()
        mock_publisher.return_value.close.assert_called_once()
        self.assertIsNotNone(handler.formatter)

    @patch("phanos.publisher.BlockingPublisher")
    def test_invalid_init(self, mock_publisher: MagicMock):
        mock_publisher.return_value.connect.side_effect = AMQPConnectorException("test")
        with self.assertRaises(RuntimeError):
            _ = ImpProfHandler("rabbit")

    @patch("phanos.publisher.log_error_profiling")
    @patch("phanos.publisher.BlockingPublisher")
    def test_handle(self, mock_publisher: MagicMock, mock_profiling: MagicMock):
        with self.subTest("handle"):
            records = [testing_data.test_handler_in, testing_data.test_handler_in]
            handler = ImpProfHandler("rabbit")
            handler.handle(records, "test_name")
            mock_publisher.return_value.publish.assert_called_once_with(records)
            mock_profiling.assert_called_once_with("test_name", handler.formatter, handler.logger, records)


class TestAsyncImpProfHandler(unittest.IsolatedAsyncioTestCase):
    @patch("phanos.publisher.AsyncioPublisher")
    async def test_init(self, mock_publisher: MagicMock):
        handler = AsyncImpProfHandler("rabbit")
        mock_publisher.assert_called_once()
        self.assertIsNotNone(handler.publisher)
        self.assertIsNotNone(handler.formatter)

    @patch("phanos.publisher.AsyncioPublisher")
    @patch("phanos.publisher.AsyncImpProfHandler._post_init")
    async def test_create(self, mock_post_init: AsyncMock, mock_publisher: MagicMock):
        handler = await AsyncImpProfHandler.create("rabbit")
        mock_publisher.assert_called_once()
        mock_post_init.assert_awaited_once()
        self.assertIsInstance(handler, AsyncImpProfHandler)

    async def test_post_init(self):
        handler = AsyncImpProfHandler("rabbit")
        mock_publisher = handler.publisher = AsyncMock()
        with self.subTest("no error"):
            await handler._post_init()
            mock_publisher.connect.assert_awaited_once()
            mock_publisher.close.assert_awaited_once()

        with self.subTest("error"):
            mock_publisher.connect.side_effect = AMQPConnectorException("test")
            with self.assertRaises(RuntimeError):
                await handler._post_init()

    @patch("phanos.publisher.log_error_profiling")
    async def test_handle(self, mock_profiling: MagicMock):
        records = [testing_data.test_handler_in, testing_data.test_handler_in]
        handler = AsyncImpProfHandler("rabbit")
        mock_publisher = handler.publisher = AsyncMock()
        await handler.handle(records, "test_name")
        mock_publisher.publish.assert_awaited_once_with(records)
        mock_profiling.assert_called_once()


class TestHandlers(unittest.TestCase):
    def test_stream_handler(self):
        output = StringIO()
        str_handler = StreamHandler("str_handler", output)
        str_handler.handle([testing_data.test_handler_in, testing_data.test_handler_in_no_lbl], "test_name")
        output.seek(0)
        self.assertEqual(
            output.read(),
            testing_data.test_handler_out + testing_data.test_handler_out_no_lbl,
        )

    @patch("phanos.publisher.OutputFormatter.record_to_str")
    def test_log_handler(self, mock_rec_to_str: MagicMock):
        mock_rec_to_str.return_value = ""
        logger = logging.getLogger()
        logger.setLevel(10)

        log_handler = LoggerHandler("log_handler", logger)
        self.assertEqual(log_handler.logger, logger)
        log_handler.handle([testing_data.test_handler_in], "test_name")
        mock_rec_to_str.assert_called_once_with("test_name", testing_data.test_handler_in)

        mock_rec_to_str.reset_mock()
        log_handler = LoggerHandler("log_handler1")
        self.assertEqual(log_handler.logger.name, "PHANOS")
        log_handler.handle([testing_data.test_handler_in], "test_name")
        mock_rec_to_str.assert_called_once_with("test_name", testing_data.test_handler_in)

    @patch("phanos.publisher.OutputFormatter.record_to_str")
    def test_named_log_handler(self, mock_rec_to_str: MagicMock):
        mock_rec_to_str.return_value = ""
        log_handler = NamedLoggerHandler("log_handler", "logger_name")
        self.assertEqual(log_handler.logger.name, "logger_name")
        log_handler.handle([testing_data.test_handler_in], "test_name")
        mock_rec_to_str.assert_called_once_with("test_name", testing_data.test_handler_in)
