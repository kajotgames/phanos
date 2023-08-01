"""Library for profiling"""
from . import (
    log,
    publisher,
    tree,
    metrics,
    handlers,
    config,
)

sync_profiler: publisher.SyncProfiler
async_profiler: publisher.AsyncProfiler
phanos_profiler: publisher.SyncProfiler

# default instance
sync_profiler = publisher.SyncProfiler()
async_profiler = publisher.AsyncProfiler()
# deprecated; for backward compatibility,
phanos_profiler = sync_profiler

# default instance profile method
sync_profile = sync_profiler.profile
async_profile = async_profiler.profile
