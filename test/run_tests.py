import unittest
import sys
from os.path import dirname, abspath, join

path = join(join(dirname(__file__), ".."), "")
path = abspath(path)
if path not in sys.path:
    sys.path.insert(0, path)

from test import test_tree, test_handlers, test_metrics, test_config, test_async

if __name__ == "__main__":
    test_classes = [
        # test_tree.TestTree,
        # test_handlers.TestHandlers,
        # test_metrics.TestMetrics,
        # test_sync.TestProfiling,
        # test_config.TestConfig,
        test_async.TestAsyncProfile,
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
