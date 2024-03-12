"""Library for profiling"""
import warnings

from . import (
    types,
    log,
    publisher,
    tree,
    metrics,
    config,
)
from .tree import MethodTreeNode


profiler: publisher.Profiler
phanos_profiler: publisher.Profiler

# default instance
profiler = publisher.Profiler()


def _deprecated():
    warnings.warn("phanos_profiler is deprecated; use profiler instead", DeprecationWarning)
    return profiler


# deprecated; for backward compatibility,
phanos_profiler = _deprecated()

# default instance profile method
profile = profiler.profile
