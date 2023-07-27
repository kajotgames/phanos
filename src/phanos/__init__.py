"""Library for profiling"""
from . import (
    log,
    publisher,
    tree,
    metrics,
    config,
)

profiler: publisher.PhanosProfiler
phanos_profiler: publisher.PhanosProfiler

# default instance
profiler = publisher.PhanosProfiler()

# deprecated; for backward compatibility,
phanos_profiler = profiler

# default instance profile method
profile = profiler.profile
