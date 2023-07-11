import sys
from os.path import dirname, abspath, join

from . import (
    testing_data,
    dummy_api,
    test_metric,
    run_tests,
)

path = join(join(dirname(__file__), ".."), "src")
path = abspath(path)
sys.path.append(path)

path = join(join(dirname(__file__), ".."), "test")
path = abspath(path)
sys.path.append(path)
