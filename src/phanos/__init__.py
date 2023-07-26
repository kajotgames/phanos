"""Library for profiling"""
from . import (
    log,
    publisher,
    tree,
    metrics,
)

profiler: publisher.SyncProfiler
phanos_profiler: publisher.SyncProfiler

# default instance
profiler = publisher.SyncProfiler()

# deprecated; for backward compatibility,
phanos_profiler = profiler

# default instance profile method
profile = profiler.profile
