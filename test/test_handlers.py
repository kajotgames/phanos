import logging
import sys
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

import phanos
from src.phanos import phanos_profiler
from phanos.publisher import BaseHandler, ImpProfHandler, LoggerHandler, NamedLoggerHandler, StreamHandler
from test import testing_data


class TestHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", time_profile=True, request_size_profile=False, error_raised_label=False)

    @classmethod
    def tearDownClass(cls) -> None:
        phanos_profiler.delete_handlers()
        phanos_profiler.delete_metrics(True, True)
        phanos_profiler.error_raised_label = False

    def tearDown(self) -> None:
        phanos_profiler.delete_handlers()

    def test_stream_handler(self):
        # base handler test
        base = BaseHandler("test_handler")
        self.assertRaises(NotImplementedError, base.handle, "test_profiler", {})
        # stream handler
        output = StringIO()
        str_handler = StreamHandler("str_handler", output)
        str_handler.handle(testing_data.test_handler_in, "test_name")
        str_handler.handle(testing_data.test_handler_in_no_lbl, "test_name")
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
        log_handler.handle(testing_data.test_handler_in, "test_name")
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        log_handler = LoggerHandler("log_handler1")
        self.assertEqual(log_handler.logger.name, "PHANOS")
        output.seek(0)
        result = output.read()
        self.assertEqual(result, testing_data.test_handler_out)
        sys.stdout = tmp

    def test_named_log_handler(self):
        log_handler = NamedLoggerHandler("log_handler", "logger_name")
        phanos.profiler.add_handler(log_handler)
        self.assertIn("log_handler", phanos.profiler.handlers)
        self.assertIs(log_handler, phanos.profiler.handlers["log_handler"])
        self.assertEqual(phanos.profiler.handlers["log_handler"].logger.name, "logger_name")
        phanos.profiler.delete_handler("log_handler")

    def test_handlers_management(self):
        length = len(phanos_profiler.handlers)
        log1 = LoggerHandler("log_handler1")
        phanos_profiler.add_handler(log1)
        log2 = LoggerHandler("log_handler2")
        phanos_profiler.add_handler(log2)
        self.assertEqual(len(phanos_profiler.handlers), length + 2)
        phanos_profiler.delete_handler("log_handler1")
        self.assertEqual(phanos_profiler.handlers.get("log_handler1"), None)
        phanos_profiler.delete_handlers()
        self.assertEqual(phanos_profiler.handlers, {})

        self.assertRaises(KeyError, phanos_profiler.delete_handler, "nonexistent")

        handler1 = StreamHandler("handler")
        handler2 = StreamHandler("handler")
        phanos_profiler.add_handler(handler1)
        self.assertEqual(handler1, phanos_profiler.handlers["handler"])
        phanos_profiler.add_handler(handler2)
        self.assertEqual(handler2, phanos_profiler.handlers["handler"])

    def test_rabbit_handler_connection(self):
        self.assertRaises(RuntimeError, ImpProfHandler, "handle")

    def test_rabbit_handler_publish(self):
        with patch("phanos.publisher.BlockingPublisher") as test_publisher:
            handler = ImpProfHandler("rabbit")
            test_publisher.assert_called()
            # noinspection PyDunderSlots,PyUnresolvedReferences
            test_publish = handler.publisher.publish = MagicMock(return_value=3)

            handler.handle(profiler_name="name", records=testing_data.test_handler_in)
            test_publish.assert_called()
