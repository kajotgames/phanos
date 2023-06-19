import unittest
import metric_tests


test_classes = [metric_tests.TestTimeProfiling]

if __name__ == "__main__":
    loader = unittest.TestLoader()
    class_suites = []
    for class_ in test_classes:
        suite = loader.loadTestsFromTestCase(class_)
        class_suites.append(suite)

    suite_ = unittest.TestSuite(class_suites)
    runner = unittest.TextTestRunner()
    results = runner.run(suite_)
    exit()
