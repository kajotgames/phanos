#!/usr/bin/env python
import cProfile
import gc
import logging
import logging.config
import sys
from time import sleep
from timeit import timeit
import pstats
from io import StringIO
import snakeviz

sys.path.append("/home/mirek/git/phanos/src")

import phanos


LOG_CONF = {  # see https://www.python.org/dev/peps/pep-0391/
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "brief": {"format": "CLACKS: %(message)s"},
        "precise": {
            "format": "CLACKS: %(asctime)s.%(msecs)03d " " %(levelname)-8s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "docker": {
            "class": "logging.StreamHandler",
            "formatter": "precise",
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        "fastapi": {
            "level": "DEBUG",
            "handlers": ["docker"],
            "propagate": False,
        },
    },
}
CFG = {
    "job": "CLACKS",
    "logger": "fastapi.phanos",
    "time_profile": True,
    "handle_records": True,
    "request_size_profile": False,
    "error_raised_label": True,
    "handlers": {},
}

LOG_HANDLER = {
    "handler_name": "log",
    "logger_name": "fastapi",
    "level": 20,
}
log_handler = phanos.publisher.NamedLoggerHandler(**LOG_HANDLER)

IMP_HANDLER = {
    "handler_name": "imp",
}
imp_handler = phanos.publisher.ImpProfHandler(**IMP_HANDLER)

SLEEP_ = 0.0000001
NO_OF_CALLS = 10000
RECURSION_DEPTH = 9

profiler_ = phanos.publisher.Profiler()
profiler_.dict_config(CFG)


class Dummy:
    @classmethod
    @profiler_.profile
    def dummy(cls, num):
        if num <= 0:
            return
        cls.dummy(num - 1)
        sleep(SLEEP_)


def profile_phanos(handlers):
    global profiler_
    profiler_.delete_handlers()
    for handler in handlers:
        profiler_.add_handler(handler)
    time_prof = cProfile.Profile()
    time_prof.enable()
    Dummy.dummy(RECURSION_DEPTH)
    time_prof.disable()
    time_prof.print_stats(sort="cumulative")
    time_prof.dump_stats("example.prof")
    duration = timeit(f"Dummy.dummy({RECURSION_DEPTH})", globals=globals(), number=NO_OF_CALLS)
    print(f"{((duration / (NO_OF_CALLS * (RECURSION_DEPTH+1))) - SLEEP_) * 10**6} microseconds per call")


if __name__ == "__main__":
    logger = logging.getLogger("fastapi")
    phanos_logger = logging.getLogger("fastapi.phanos")
    phanos_logger.setLevel(logging.CRITICAL)
    phanos_logger.disabled = True
    logger.setLevel(logging.CRITICAL)
    logger.disabled = True

    logging.config.dictConfig(LOG_CONF)
    logger.handlers[0].stream = StringIO()
    gc.disable()

    # profile_phanos([log_handler])
    profile_phanos([imp_handler])
    profile_phanos([imp_handler])
    # profile_phanos([log_handler, imp_handler])
    # TODO: possible performance boosts.
    #   reduce calls to parent()
    #   change find_and_delete_node in sync with delete_node(curr_node)
    #   now imp_prof sends in root node. maybe make bigger batches
    #   wrapper -
