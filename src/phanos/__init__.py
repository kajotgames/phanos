"""Library for profiling"""
from . import (
    log,
    profilers,
    tree,
    metrics,
    handlers,
)

sync_profiler: profilers.SyncProfiler
async_profiler: profilers.AsyncProfiler
phanos_profiler: profilers.SyncProfiler

# default instance
sync_profiler = profilers.SyncProfiler()
async_profiler = profilers.AsyncProfiler()
# deprecated; for backward compatibility,
phanos_profiler = sync_profiler

# default instance profile method
sync_profile = sync_profiler.profile
async_profile = async_profiler.profile
