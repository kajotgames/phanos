import unittest
from test import test_metric

if __name__ == "__main__":
    test_classes = [
        test_metric.TestMetrics,
        test_metric.TestHandlers,
        test_metric.TestTree,
        test_metric.TestProfiling,
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
