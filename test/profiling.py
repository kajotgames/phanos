#!/usr/bin/env python
import sys
import cProfile
from time import sleep
from typing import List

import pyperf

sys.path.append("/home/mirek/git/phanos/src")

import phanos

# Setup code for pyperf benchmarks
setup_code = """
from __main__ import Benchmark, LOG_CONF, imp_handler
from io import StringIO
import logging
import logging.config

logger = logging.getLogger("fastapi")
phanos_logger = logging.getLogger("fastapi.phanos")
phanos_logger.setLevel(logging.CRITICAL)
phanos_logger.disabled = True
logger.setLevel(logging.CRITICAL)
logger.disabled = True
logging.config.dictConfig(LOG_CONF)
logger.handlers[0].stream = output = StringIO()
imp_handler.publisher.connect()
"""

# Configuration for logger
LOG_CONF = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "brief": {"format": "CLACKS: %(message)s"},
        "precise": {
            "format": "CLACKS: %(asctime)s.%(msecs)03d " " %(levelname)-8s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {"docker": {"class": "logging.StreamHandler", "formatter": "precise", "stream": "ext://sys.stdout"}},
    "loggers": {"fastapi": {"level": "DEBUG", "handlers": ["docker"], "propagate": False}},
}

# Configuration for phanos
PHANOS_CONF = {
    "job": "CLACKS",
    "logger": "fastapi.phanos",
    "time_profile": True,
    "handle_records": True,
    "request_size_profile": False,
    "error_raised_label": True,
    "handlers": {},
}

LOG_HANDLER = {"handler_name": "log", "logger_name": "fastapi", "level": 20}
log_handler = phanos.publisher.NamedLoggerHandler(**LOG_HANDLER)

IMP_HANDLER = {"handler_name": "imp"}
imp_handler = phanos.publisher.ImpProfHandler(**IMP_HANDLER)


profiler_ = phanos.publisher.Profiler()
profiler_.dict_config(PHANOS_CONF)

# Benchmark parameters
SLEEP_ = 0.0000000
RECURSION_DEPTH = 0
NO_OF_CALLS = 1000


class Benchmark:
    @classmethod
    @profiler_.profile
    def dummy_w_profile(cls, num):
        """Dummy method with profiling"""
        sleep(SLEEP_)
        if num <= 0:
            return
        cls.dummy_w_profile(num - 1)

    @classmethod
    def dummy_wo_profile(cls, num):
        """Dummy method without profiling"""
        sleep(SLEEP_)
        if num <= 0:
            return
        cls.dummy_wo_profile(num - 1)


# All benchmark cases
BENCHMARK_CASES = [
    ("empty_wo_profile", Benchmark.dummy_wo_profile, []),  #  without phanos
    ("empty_w_profile", Benchmark.dummy_w_profile, []),  # with phanos, but no handlers
    ("log", Benchmark.dummy_w_profile, [log_handler]),  # with log handler
    ("imp", Benchmark.dummy_w_profile, [imp_handler]),  # with imp_prof handler
    ("both", Benchmark.dummy_w_profile, [log_handler, imp_handler]),  # with both handlers
]


def cprofile_benchmark(name_, method_):
    """Run one benchmark with cProfile

    :param method_: method to benchmark
    :param name_: name of the benchmark
    """
    # cProfile with snakeviz visualization
    time_prof = cProfile.Profile()
    method_(RECURSION_DEPTH)
    time_prof.enable()
    method_(RECURSION_DEPTH)
    time_prof.disable()
    time_prof.dump_stats(f"./benchmark/handler_{name_}.prof")


def cprofile_benchmarks():
    """Run all benchmarks with cProfile"""
    for name_, method_, handlers_ in BENCHMARK_CASES:
        set_handlers(handlers_)
        cprofile_benchmark(name_, method_)


def pyperf_benchmark(name_, method_, runner_):
    """Run one benchmark with pyperf

    :param name_: name of the benchmark
    :param method_: method to benchmark
    :param runner_: pyperf runner
    """
    runner_.timeit(name=name_, stmt=f"{method_.__qualname__}({RECURSION_DEPTH})", setup=setup_code)


def pyperf_benchmarks():
    """Run all benchmarks with pyperf"""
    runner = pyperf.Runner()
    for name_, method_, handlers_ in BENCHMARK_CASES:
        set_handlers(handlers_)
        pyperf_benchmark(name_, method_, runner)


def set_handlers(handlers_: List[phanos.publisher.SyncBaseHandler]):
    """Set handlers for profiler"""
    profiler_.delete_handlers()
    for handler in handlers_:
        profiler_.add_handler(handler)


if __name__ == "__main__":
    # NOTE: need rabbitmq running

    # NOTE: run only one of these
    # pyperf_benchmarks()
    cprofile_benchmarks()

""" cProfile results: viz benchmark folder `snakeviz ./benchmark/handler_{name}.prof` after running cprofile_benchmarks"""

""" pyperf results
.....................
empty_wo_profile: Mean +- std dev: 52.1 us +- 0.3 us
.....................
empty_w_profile: Mean +- std dev: 52.3 us +- 0.2 us
.....................
log: Mean +- std dev: 69.7 us +- 3.1 us
.....................
imp: Mean +- std dev: 127 us +- 7 us
.....................
both: Mean +- std dev: 132 us +- 6 us
"""

""" possible performance boosts.
  - add_child?
  - reduce calls to parent()?
  - change find_and_delete_node in sync with delete_node(curr_node)?
  - StoreOperation.wrapper ?
  
  Biggest performance boost in ImpProfHandler would be to use nonblocking publisher.
  - nonblocking publisher other than AsyncIO
  - now imp_prof sends in root node. maybe make bigger batches
"""
