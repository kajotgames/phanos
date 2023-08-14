import sys
from os.path import join, dirname

src_path = join(join(join(dirname(__file__), ".."), "src"), "")
test_path = join(join(join(dirname(__file__), ".."), "test"), "")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
if test_path not in sys.path:
    sys.path.insert(0, test_path)

from . import (
    testing_data,
    dummy_api,
    test_sync,
    test_async,
    test_config,
    test_tree,
    test_metrics,
    test_handlers,
    run_tests,
)
