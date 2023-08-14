# run with `python -m unittest -v test/test_config.py`
# or for coverage `python -m coverage run -m unittest -v test/test_config.py`
import unittest

import phanos.publisher
from src import phanos

STDOUT = "sys.stdout"
KWARGS_DICT = {"stream": "ext://sys.stdout", "value": 1}
HANDLER_NAME = "stdout_handler"
HANDLER_REFERENCE = "stdout_handler_ref"
HANDLERS_DICT = {
    HANDLER_REFERENCE: {
        "class": "src.phanos.publisher.StreamHandler",
        "handler_name": HANDLER_NAME,
        "output": "ext://sys.stdout",
    }
}

SETTING_DICT = {
    "job": "my_app",
    "logger": "my_app_debug_logger",
    "time_profile": True,
    "request_size_profile": True,
    "error_raised_label": False,
    "handle_records": True,
    "handlers": HANDLERS_DICT,
}


class TestConfig(unittest.TestCase):
    def test_external(self):
        std_out = phanos.config.import_external(STDOUT)
        import sys

        self.assertEqual(std_out, sys.stdout)

    def test_to_callable(self):
        # handle object name
        std_out_parsed = phanos.config._to_callable(STDOUT)
        import sys

        self.assertEqual(std_out_parsed, sys.stdout)
        # handle object
        std_out_parsed = phanos.config._to_callable(sys.stdout)
        self.assertEqual(std_out_parsed, sys.stdout)

    def test_parse_arguments(self):
        parsed_dict = phanos.config.parse_arguments(KWARGS_DICT)
        for key in KWARGS_DICT:
            self.assertIn(key, parsed_dict)
        self.assertEqual(parsed_dict["value"], KWARGS_DICT["value"])
        import sys

        self.assertEqual(parsed_dict["stream"], sys.stdout)

    def test_create_handlers(self):
        parsed = phanos.config.create_handlers(HANDLERS_DICT)
        for key in HANDLERS_DICT:
            self.assertIn(key, parsed)
        self.assertIsInstance(parsed[HANDLER_REFERENCE], phanos.publisher.StreamHandler)
        self.assertEqual(HANDLER_NAME, parsed[HANDLER_REFERENCE].handler_name)

    def test_dict_config(self):
        _test_profiler = phanos.publisher.Profiler()
        try:
            _test_profiler.dict_config(SETTING_DICT)
        except (KeyError, ValueError, IndexError, Exception) as e:
            self.assertIsNone(e)
        self.assertIsInstance(_test_profiler.handlers[HANDLER_NAME], phanos.publisher.StreamHandler)
        self.assertIn(HANDLER_NAME, _test_profiler.handlers)
        self.assertTrue(_test_profiler.resp_size_profile)

    def test_job_missing(self):
        _test_profiler = phanos.publisher.Profiler()
        no_job = SETTING_DICT.copy()
        no_job.pop("job")
        self.assertRaises(KeyError, _test_profiler.dict_config, no_job)
