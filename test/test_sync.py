import unittest
from io import StringIO
import sys
from os.path import dirname, abspath, join

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)

from src.phanos import publisher
from src.phanos import phanos_profiler
from phanos.publisher import StreamHandler
from test import testing_data, dummy_api
from test.dummy_api import app, DummyDbAccess
from src.phanos.metrics import (
    Histogram,
)


class TestProfiling(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST")
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        phanos_profiler.create_time_profiler()
        phanos_profiler.create_response_size_profiler()
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        phanos_profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        phanos_profiler.delete_handlers()
        phanos_profiler.delete_metrics(True, True)
        phanos_profiler.before_root_func = None
        phanos_profiler.after_root_func = None
        phanos_profiler.before_func = None
        phanos_profiler.after_func = None
        self.output.close()

    def test_metric_management(self):
        length = len(phanos_profiler.metrics)
        # create metrics
        hist = Histogram("name", "TEST", "units")
        phanos_profiler.add_metric(hist)
        hist1 = Histogram("name1", "TEST", "units")
        phanos_profiler.add_metric(hist1)
        self.assertEqual(len(phanos_profiler.metrics), length + 2)
        # delete metric
        phanos_profiler.delete_metric("name")
        self.assertEqual(len(phanos_profiler.metrics), length + 1)
        self.assertEqual(phanos_profiler.metrics.get("name"), None)
        # delete time_profiling metric
        phanos_profiler.delete_metric(publisher.TIME_PROFILER)
        self.assertEqual(phanos_profiler.metrics.get(publisher.TIME_PROFILER), None)
        self.assertEqual(phanos_profiler.time_profile, None)
        # delete response size metric
        phanos_profiler.delete_metric(publisher.RESPONSE_SIZE)
        self.assertEqual(phanos_profiler.metrics.get(publisher.RESPONSE_SIZE), None)
        self.assertEqual(phanos_profiler.resp_size_profile, None)
        # create response size metric
        phanos_profiler.create_response_size_profiler()
        self.assertIsNotNone(phanos_profiler.resp_size_profile)
        self.assertEqual(len(phanos_profiler.metrics), 2)

        # delete all metrics (without response size and time profiling metrics)
        phanos_profiler.delete_metrics()
        self.assertEqual(len(phanos_profiler.metrics), 1)
        self.assertIsNotNone(phanos_profiler.resp_size_profile, None)
        self.assertIsNotNone(phanos_profiler.metrics.get(publisher.RESPONSE_SIZE))
        phanos_profiler.delete_metrics(rm_time_profile=True, rm_resp_size_profile=True)
        self.assertEqual(phanos_profiler.metrics, {})
        self.assertEqual(phanos_profiler.metrics.get(publisher.RESPONSE_SIZE), None)

        self.assertRaises(KeyError, phanos_profiler.delete_metric, "nonexistent")

        metric1 = Histogram("hist", "TEST", "xz")
        metric2 = Histogram("hist", "TEST", "xz")
        phanos_profiler.add_metric(metric1)
        self.assertEqual(metric1, phanos_profiler.metrics["hist"])
        phanos_profiler.add_metric(metric2)
        self.assertEqual(metric2, phanos_profiler.metrics["hist"])

    def test_profiling(self):
        # do not handle records
        phanos_profiler.handle_records = False
        _ = self.client.get("http://localhost/api/dummy/one")
        self.output.seek(0)
        lines = self.output.readlines()
        self.assertEqual(lines, [])

        # test of api call inside same api call with error risen
        phanos_profiler.handle_records = True
        _ = self.client.post("http://localhost/api/dummy/one")
        self.output.seek(0)
        self.assertEqual(len(self.output.readlines()), 4)
        self.output.truncate(0)
        self.output.seek(0)
        # cleanup assertion
        for metric in phanos_profiler.metrics.values():
            self.assertEqual(metric.values, [])
            self.assertEqual(metric.label_values, [])
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.item, [])

        # profiling after request, where error_occurred
        _ = self.client.get("http://localhost/api/dummy/one")
        self.output.seek(0)
        lines = self.output.readlines()
        time_lines = lines[:-1]
        size_line = lines[-1]
        for i in range(len(time_lines)):
            line = time_lines[i][:-1]
            value = line.split("value: ")[1][:-3]
            self.assertEqual(
                (float(value)) // 100,
                testing_data.profiling_out[i]["value"],
            )
            method = line.split(", ")[1][8:]
            self.assertEqual(
                method,
                testing_data.profiling_out[i]["method"],
            )

        size_line = size_line[:-1]
        value = size_line.split("value: ")[1][:-2]
        self.assertEqual(
            (float(value)),
            testing_data.profiling_out[-1]["value"],
        )
        method = size_line.split(", ")[1][8:]
        self.assertEqual(
            method,
            testing_data.profiling_out[-1]["method"],
        )

        self.assertEqual(phanos_profiler.tree.root.children, [])

        access = dummy_api.DummyDbAccess()
        self.output.truncate(0)
        self.output.seek(0)

        # error raised tree and metrics should be raised normally and error should be reraised
        self.assertRaises(RuntimeError, access.raise_access)
        self.output.seek(0)
        self.assertEqual(len(self.output.readlines()), 3)

        # cleanup assertion
        for metric in phanos_profiler.metrics.values():
            self.assertEqual(metric.values, [])
            self.assertEqual(metric.label_values, [])
            self.assertEqual(metric.method, [])
            self.assertEqual(metric.item, [])

        self.assertEqual(phanos_profiler.tree.root.children, [])

    def test_custom_profile_addition(self):
        hist = Histogram("test_name", "TEST", "test_units", ["place"])
        self.assertEqual(len(phanos_profiler.metrics), 2)
        phanos_profiler.add_metric(hist)
        self.assertEqual(len(phanos_profiler.metrics), 3)
        phanos_profiler.delete_metric(publisher.TIME_PROFILER)
        phanos_profiler.delete_metric(publisher.RESPONSE_SIZE)

        def before_root_func(func, args, kwargs):
            hist.observe(
                1.0,
                {"place": "before_root"},
            )

        phanos_profiler.before_root_func = before_root_func

        def before_func(func, args, kwargs):
            _ = args
            _ = kwargs
            _ = func
            hist.observe(
                2.0,
                {"place": "before_func"},
            )

        phanos_profiler.before_func = before_func

        def after_func(fn_result, args, kwargs):
            _ = args
            _ = kwargs
            _ = fn_result
            hist.observe(
                3.0,
                {"place": "after_func"},
            )

        phanos_profiler.after_func = after_func

        def after_root_func(fn_result, args, kwargs):
            _ = args
            _ = kwargs
            _ = fn_result
            hist.observe(
                4.0,
                {"place": "after_root"},
            )

        phanos_profiler.after_root_func = after_root_func

        dummy_access = DummyDbAccess()
        _ = dummy_access.second_access()
        self.output.seek(0)
        logs = self.output.readlines()
        for i in range(len(logs)):
            line = logs[i].split(", ")
            method = line[1][8:]
            value = line[2][7:10]
            place = line[3][14:-1]
            self.assertEqual(method, testing_data.custom_profile_out[i]["method"])
            self.assertEqual(float(value), testing_data.custom_profile_out[i]["value"])
            self.assertEqual(place, testing_data.custom_profile_out[i]["place"])
