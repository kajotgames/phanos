# run with `python -m unittest -v test/test_config.py`
# or for coverage `python -m coverage run -m unittest -v test/test_config.py`

import unittest

from src import phanos


class TestConfig(unittest.TestCase):
    STDOUT = "sys.stdout"
    KWARGS_DICT = {"stream": "ext://sys.stdout", "value": 1}
    CONF_DICT = {
        "stdout_handler": {
            "class": "src.phanos.publisher.StreamHandler",
            "handler_name": "stdout_handler",
            "output": "ext://sys.stdout",
        }
    }

    def test_external(self):
        std_out = phanos.config.import_external(self.STDOUT)
        import sys

        self.assertEqual(std_out, sys.stdout)

    def test_to_callable(self):
        # handle object name
        std_out_parsed = phanos.config._to_callable(self.STDOUT)
        import sys

        self.assertEqual(std_out_parsed, sys.stdout)
        # handle object
        std_out_parsed = phanos.config._to_callable(sys.stdout)
        self.assertEqual(std_out_parsed, sys.stdout)

    def test_parse_arguments(self):
        parsed_dict = phanos.config.parse_arguments(self.KWARGS_DICT)
        for key in self.KWARGS_DICT:
            self.assertIn(key, parsed_dict)
        self.assertEqual(parsed_dict["value"], self.KWARGS_DICT["value"])
        import sys

        self.assertEqual(parsed_dict["stream"], sys.stdout)

    def test_create_handlers(self):
        parsed = phanos.config.create_handlers(self.CONF_DICT)
        for key in self.CONF_DICT:
            self.assertIn(key, parsed)
        self.assertIsInstance(parsed["stdout_handler"], phanos.publisher.StreamHandler)
