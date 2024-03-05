import copy
import logging
import sys
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

from pika.adapters.utils.connection_workflow import AMQPConnectorException

import phanos
from src.phanos import phanos_profiler
from phanos.publisher import (
    BaseHandler,
    SyncImpProfHandler,
    LoggerHandler,
    NamedLoggerHandler,
    StreamHandler,
    OutputFormatter,
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


class TestHandlers(unittest.TestCase):
    def test_base_handler_init(self):
        base = BaseHandler("test_handler")
        self.assertEqual(base.handler_name, "test_handler")

        # base handler.handle
        base = BaseHandler("test_handler")
        self.assertRaises(NotImplementedError, base.handle, "test_profiler", {})

    @patch("phanos.publisher.BlockingPublisher")
    @patch("phanos.publisher.ImpProfHandler.log_error_profiling")
    def test_imp_prof_handler(self, mock_profiling: MagicMock, mock_publisher: MagicMock):
        mock_publisher.return_value.connect.return_value = True
        with self.subTest("VALID INIT"):
            handler = SyncImpProfHandler("rabbit")
            mock_publisher.assert_called_once()
            mock_publisher.return_value.connect.assert_called_once()
            mock_publisher.return_value.close.assert_called_once()
            self.assertIsNotNone(handler.formatter)

        mock_publisher.return_value.connect.side_effect = AMQPConnectorException()
        with self.subTest("INVALID INIT"):
            with self.assertRaises(RuntimeError):
                _ = SyncImpProfHandler("rabbit")

        mock_publisher.return_value.connect.side_effect = None
        with self.subTest("HANDLE"):
            records = [testing_data.test_handler_in, testing_data.test_handler_in]
            handler = SyncImpProfHandler("rabbit")
            handler.handle(records, "test_name")
            self.assertEqual(mock_publisher.return_value.publish.call_count, 2)
            mock_profiling.assert_called_once_with("test_name", records)

    @patch("phanos.publisher.BlockingPublisher")
    @patch("phanos.publisher.OutputFormatter.record_to_str")
    def test_log_error_profiling(self, mock_rec_to_str: MagicMock, mock_publisher: MagicMock):
        mock_rec_to_str.return_value = ""
        record = copy.deepcopy(testing_data.test_handler_in)
        records = [record, record]
        handler = SyncImpProfHandler("rabbit")

        handler.log_error_profiling("test_name", records)
        self.assertEqual(mock_rec_to_str.call_count, 2)
        mock_rec_to_str.assert_called_with("test_name", records[0])

        record["labels"]["error_raised"] = "False"
        mock_rec_to_str.reset_mock()
        handler.log_error_profiling("test_name", records)
        mock_rec_to_str.assert_not_called()

        _ = record["labels"].pop("error_raised", None)
        handler.log_error_profiling("test_name", records)
        mock_rec_to_str.assert_not_called()

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
