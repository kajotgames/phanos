"""Library for profiling"""
from . import (
    types,
    log,
    publisher,
    tree,
    metrics,
    handlers,
    config,
)
from .tree import MethodTreeNode


profiler: publisher.Profiler
phanos_profiler: publisher.Profiler

# default instance
profiler = publisher.Profiler()
# deprecated; for backward compatibility,
phanos_profiler = profiler

# default instance profile method
profile = profiler.profile
