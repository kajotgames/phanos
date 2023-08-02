import unittest
import sys
from os.path import dirname, abspath, join

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)

from test import test_metric, test_config

if __name__ == "__main__":
    test_classes = [
        test_metric.TestMetrics,
        test_metric.TestHandlers,
        test_metric.TestTree,
        test_metric.TestProfiling,
        test_metric.TestAsync,
        test_config.TestConfig,
    ]

    loader = unittest.TestLoader()
    class_suites = []
    for class_ in test_classes:
        suite = loader.loadTestsFromTestCase(class_)
        class_suites.append(suite)

    suite_ = unittest.TestSuite(class_suites)
    runner = unittest.TextTestRunner()
    results = runner.run(suite_)
    exit()
