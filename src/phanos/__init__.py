"""Library for profiling"""
from . import (
    log,
    publisher,
    tree,
    metrics,
    handlers,
    config,
)

sync_profiler: publisher.Profiler
async_profiler: publisher.Profiler
phanos_profiler: publisher.Profiler

# default instance
sync_profiler = publisher.Profiler()
async_profiler = publisher.Profiler()
# deprecated; for backward compatibility,
phanos_profiler = sync_profiler

# default instance profile method
sync_profile = sync_profiler.profile
async_profile = async_profiler.profile
