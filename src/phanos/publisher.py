""" """
from __future__ import annotations

import inspect
import logging
import sys
import threading
import typing as tp
import warnings
from abc import abstractmethod, ABC
from datetime import datetime
from functools import wraps

from . import log
from .messaging import AsyncioPublisher, NETWORK_ERRORS, BlockingPublisher
from .tree import ContextTree, curr_node
from .metrics import MetricWrapper, TimeProfiler, ResponseSize
from .tree import MethodTreeNode
from .types import LoggerLike, Record

TIME_PROFILER = "time_profiler"
RESPONSE_SIZE = "response_size"

# type of callable, which is called before execution of profiled method
BeforeType = tp.Optional[tp.Callable[[tp.Callable[[...], tp.Any], tp.Tuple[tp.Any, ...], tp.Dict[str, tp.Any]], None]]
# type of callable, which is called after execution of profiled method
AfterType = tp.Optional[tp.Callable[[tp.Any, tp.List[tp.Any], tp.Dict[str, tp.Any]], None]]


class AbstractExtProfiler(ABC):  # pragma: no cover
    @abstractmethod
    def handle_records_clear(self) -> None:
        """Pass stored records to each registered Handler and delete stored records.
        This method DOES NOT clear MethodContext tree
        """
        raise NotImplementedError

    @abstractmethod
    def force_handle_records_clear(self) -> None:
        """Pass stored records to each registered Handler and delete stored records.

        As side effect clears all metrics and DOES CLEAR MethodContext tree
        """
        raise NotImplementedError

    @abstractmethod
    def async_inner(self, func: tp.Callable[..., tp.Any], *args, **kwargs) -> tp.Any:
        """Profiling behaviour for async callables

        :param func: function to profile
        :param args: function arguments
        :param kwargs: function keyword arguments
        """
        raise NotImplementedError

    @abstractmethod
    def sync_inner(self, func: tp.Callable[..., tp.Any], *args, **kwargs) -> tp.Any:
        """Profiling behaviour for sync callables

        :param func: function to profile
        :param args: function arguments
        :param kwargs: function keyword arguments
        """
        raise NotImplementedError


class Profiler(log.InstanceLoggerMixin):
    """Base class for Profiler"""

    tree: ContextTree

    # NOTE: possible refactor make class MetricStorage (__setitem__, __getitem__, __delitem__, ...)
    metrics: tp.Dict[str, MetricWrapper]
    time_profile: tp.Optional[TimeProfiler]
    resp_size_profile: tp.Optional[ResponseSize]

    # NOTE: possible refactor make class HandlerStorage (__setitem__, __getitem__, __delitem__, ...)
    handlers: tp.Dict[str, tp.Union[SyncBaseHandler, AsyncBaseHandler]]

    job: str
    handle_records: bool
    _error_raised_label: bool

    # space for user specific profiling logic
    before_func: BeforeType
    after_func: AfterType
    before_root_func: BeforeType
    after_root_func: AfterType

    profile_ext: tp.Optional[tp.Union[AsyncExtProfiler, SyncExtProfiler]]

    RECORDS_ERR_LIMIT = 3000  # if records count exceed this limit, something is wrong; log error and clear records
    RECORDS_LEN_LIMIT = 100  # handle records after this limit or in root node

    def __init__(self) -> None:
        """Initialize Profiler

        Initialization just creates new instance. Profiler NEEDS TO BE configured.
        Use Profiler.config() or Profiler.dict_config() to configure it. Profiling won't start otherwise.
        """

        self.metrics = {}
        self.handlers = {}
        self.job = ""
        self.handle_records = False
        self._error_raised_label = True

        self.resp_size_profile = None
        self.time_profile = None

        self.before_func = None
        self.after_func = None
        self.before_root_func = None
        self.after_root_func = None

        super().__init__(logged_name="phanos")

    def dict_config(self, settings: dict[str, tp.Any]) -> None:
        """
        Configure profiler instance with dictionary config for use with sync handlers.
        Set up profiling from config file, instead of changing code for various environments.

        NOTE: can be used in async environment
        NOTE: use only if you are not planning to use any async handler, use `async_config` otherwise

        Example:
            ```
            {
                "job": "my_app",
                "logger": "my_app_debug_logger",
                "time_profile": True,
                "request_size_profile": False,
                "handle_records": True,
                "error_raised_label": True,
                "handlers": {
                    "stdout_handler": {
                        "class": "phanos.publisher.StreamHandler",
                        "handler_name": "stdout_handler",
                        "output": "ext://sys.stdout",
                    }
                }
            }
            ```

        Version 0.3.0:
            `request_size_profile` key DEPRECATED, use `response_size_profile` kwarg instead

        :param settings: dictionary of desired profiling set up
        """
        from . import config as phanos_config

        self._dict_cfg_sync(settings)
        self.profile_ext = SyncExtProfiler(self)
        if "handlers" in settings:
            try:
                named_handlers = phanos_config.create_handlers(settings["handlers"])
            except ValueError:
                self.error("Cannot create async handler in sync profiler")
                raise
            for handler in named_handlers.values():
                self.add_handler(handler)

    async def async_dict_config(self, settings: dict[str, tp.Any]) -> None:
        """
        Configure profiler instance with dictionary config for use with async handlers.
        Set up profiling from config file, instead of changing code for various environments.

        NOTE: cannot be used in purely sync environment
        NOTE: allows to use sync handlers as well

        Example:
            ```
            {
                "job": "my_app",
                "logger": "my_app_debug_logger",
                "time_profile": True,
                "request_size_profile": False,
                "handle_records": True,
                "error_raised_label": True,
                "handlers": {
                    "stdout_handler": {
                        "class": "phanos.publisher.StreamHandler",
                        "handler_name": "stdout_handler",
                        "output": "ext://sys.stdout",
                    }
                }
            }
            ```

        Version 0.3.0:
            `request_size_profile` key DEPRECATED, use `response_size_profile` kwarg instead

        :param settings: dictionary of desired profiling set up
        """
        from . import config as phanos_config

        self._dict_cfg_sync(settings)
        self.profile_ext = AsyncExtProfiler(self)
        if "handlers" in settings:
            named_handlers: tp.Dict[str, tp.Union[SyncBaseHandler, AsyncBaseHandler]]
            named_handlers = await phanos_config.create_async_handlers(settings["handlers"])
            for handler in named_handlers.values():
                self.add_handler(handler)

    def _dict_cfg_sync(self, settings: dict[str, tp.Any]) -> None:
        """common part for `dict_config` and `async_dict_config` methods

        :param settings: dictionary of desired profiling set up
        """
        if "logger" in settings:
            self.logger = logging.getLogger(settings["logger"])
        if "job" not in settings:
            self.logger.error("Job argument not found in config dictionary")
            raise KeyError("Job argument not found in config dictionary")
        self.job = settings["job"]
        if settings.get("time_profile"):
            self.create_time_profiler()
        # request_size_profile deprecated
        if settings.get("request_size_profile") or settings.get("response_size_profile"):
            if settings.get("request_size_profile"):
                warnings.warn("request_size_profile is deprecated, use response_size_profile", DeprecationWarning)
            self.create_response_size_profiler()
        self.error_raised_label = settings.get("error_raised_label", True)
        self.handle_records = settings.get("handle_records", True)
        self.tree = ContextTree(self.logger)

    def _config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = False,
        response_size_profile: bool = False,
        handle_records: bool = True,
        error_raised_label: bool = True,
        **kwargs,
    ) -> None:
        """common part for `config` and `async_config` methods

        :param error_raised_label: if record should have label signalizing error occurrence
        :param time_profile: if time profiling should be enabled
        :param job: name of job
        :param logger: logger instance
        :param request_size_profile: [DEPRECATED](use response_size_profile)
         should create instance of response size profiler
        :param response_size_profile: should create instance of response size profiler
        :param handle_records: should handle recorded records
        :param ** kwargs: additional parameters
        """
        _ = kwargs
        self.logger = logger or logging.getLogger(__name__)
        self.job = job

        self.handle_records = handle_records
        self.error_raised_label = error_raised_label

        self.tree = ContextTree(self.logger)
        # request_size_profile deprecated
        if request_size_profile or response_size_profile:
            if request_size_profile:
                warnings.warn("request_size_profile is deprecated, use response_size_profile", DeprecationWarning)
            self.create_response_size_profiler()
        if time_profile:
            self.create_time_profiler()

    def config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = False,
        response_size_profile: bool = False,
        handle_records: bool = True,
        error_raised_label: bool = True,
        **kwargs,
    ) -> None:
        """configure profiler instance for use with sync handlers

        NOTE: can be used in async environment
        NOTE: use only if you are not planning to use any async handler, use `async_config` otherwise

        Version 0.3.0:
            `request_size_profile` DEPRECATED, use `response_size_profile` kwarg instead

        :param error_raised_label: if record should have label signalizing error occurrence
        :param time_profile: if time profiling should be enabled
        :param job: name of job
        :param logger: logger instance
        :param request_size_profile: [DEPRECATED](use response_size_profile)
         should create instance of response size profiler
        :param response_size_profile: should create instance of response size profiler
        :param handle_records: should handle recorded records
        :param ** kwargs: additional parameters (currently not used)

        """
        self._config(
            logger,
            job,
            time_profile,
            request_size_profile,
            response_size_profile,
            handle_records,
            error_raised_label,
            **kwargs,
        )
        self.profile_ext = SyncExtProfiler(self)
        self.debug("Profiler configured successfully")

    def async_config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = False,
        response_size_profile: bool = False,
        handle_records: bool = True,
        error_raised_label: bool = True,
        **kwargs,
    ):
        """Configure profiler instance for use with async handlers

        NOTE: cannot be used in purely sync environment
        NOTE: allows to use sync handlers as well

        Version 0.3.0:
            `request_size_profile` deprecated, use `response_size_profile` kwarg instead

        :param error_raised_label: if record should have label signalizing error occurrence
        :param time_profile: if time profiling should be enabled
        :param job: name of job
        :param logger: logger instance
        :param request_size_profile: [DEPRECATED](use response_size_profile)
         should create instance of response size profiler
        :param response_size_profile: should create instance of response size profiler
        :param handle_records: should handle recorded records
        :param ** kwargs: additional parameters (currently not used)
        """
        self._config(
            logger,
            job,
            time_profile,
            request_size_profile,
            response_size_profile,
            handle_records,
            error_raised_label,
            **kwargs,
        )
        self.profile_ext = AsyncExtProfiler(self)
        self.debug("Profiler configured successfully")

    def needs_profiling(self) -> bool:
        return self.handlers and self.handle_records and self.metrics

    @property
    def error_raised_label(self) -> bool:
        return self._error_raised_label

    @error_raised_label.setter
    def error_raised_label(self, value: bool):
        self._error_raised_label = value
        if value is False:
            for metric in self.metrics.values():
                try:
                    _ = metric.label_names.remove("error_raised")
                except KeyError:
                    pass
        else:
            for metric in self.metrics.values():
                metric.label_names.add("error_raised")

    def create_time_profiler(self) -> None:
        """Create time profiling metric"""
        self.time_profile = TimeProfiler(TIME_PROFILER, job=self.job, logger=self.logger)
        self.add_metric(self.time_profile)
        self.debug("Phanos - time profiler created")

    def create_response_size_profiler(self) -> None:
        """Create response size profiling metric"""
        self.resp_size_profile = ResponseSize(RESPONSE_SIZE, job=self.job, logger=self.logger)
        self.add_metric(self.resp_size_profile)
        self.debug("Phanos - response size profiler created")

    def delete_metric(self, item: str) -> None:
        """Deletes one metric instance
        :param item: name of the metric instance
        :raises KeyError: if metric does not exist
        """
        try:
            _ = self.metrics.pop(item)
        except KeyError:
            self.warning(f"{self.delete_metric.__qualname__}: metric {item} do not exist")
            return
        if item == TIME_PROFILER:
            self.time_profile = None
        if item == RESPONSE_SIZE:
            self.resp_size_profile = None
        self.debug(f"metric {item} deleted")

    def delete_metrics(self, rm_time_profile: bool = False, rm_resp_size_profile: bool = False) -> None:
        """Deletes all custom metric instances and builtin metrics based on parameters

        :param rm_time_profile: should pre created time_profiler be deleted
        :param rm_resp_size_profile: should pre created response_size_profiler be deleted
        """
        names = list(self.metrics.keys())
        for name in names:
            if (name != TIME_PROFILER or rm_time_profile) and (name != RESPONSE_SIZE or rm_resp_size_profile):
                self.delete_metric(name)

    def clear(self) -> None:
        """Clear all records from all metrics, clear method tree and set curr_node to `tree.root`

        do NOT use during profiling
        """
        for metric in self.metrics.values():
            metric.cleanup()

        self.tree.clear()
        curr_node.set(self.tree.root)

    def add_metric(self, metric: MetricWrapper) -> None:
        """Adds new metric to profiling. If metric.name == existing metric name, existing metric will be overwritten.
        Side effect: if `self.error_raised_label` True then additional label 'error_raised' is added into metric.

        :param metric: metric instance
        """
        if self.metrics.get(metric.name, None):
            self.warning(
                f"{self.add_metric.__qualname__!r}: Metric {metric.name!r} already exist. Overwriting with new metric"
            )
        if self.error_raised_label:
            metric.label_names.add("error_raised")
        self.metrics[metric.name] = metric
        self.debug(f"Metric {metric.name!r} added to phanos profiler")

    def get_records_count(self) -> int:
        self.records_ = """Get count of records from all metrics.

        :returns: count of records
        """
        count = 0
        for metric in self.metrics.values():
            count += len(metric.values)

        return count

    def add_handler(self, handler: tp.Union[SyncBaseHandler, AsyncBaseHandler]) -> None:
        """Add handler to profiler. If handler.name == existing handler name, existing handler will be overwritten.

        Version 0.3.0:
            If handler is asynchronous and profiler is synchronous, ValueError is raised
            If profiler is not configured yet, RuntimeError is raised

        :param handler: handler instance profiler_name
        :raises RuntimeError: if profiler is not configured yet
        :raises ValueError: if handler is asynchronous and profiler is synchronous
        """
        if self.profile_ext is None:
            raise RuntimeError("Profiler not configured yet")
        if isinstance(handler, AsyncBaseHandler) and not isinstance(self.profile_ext, AsyncExtProfiler):
            raise ValueError(f"Handler {handler.handler_name!r} is asynchronous, but profiler is synchronous")
        if self.handlers.get(handler.handler_name, None):
            self.warning(
                f"{self.add_handler.__qualname__!r}:Handler {handler.handler_name!r} already exist. "
                f"Overwriting with new handler"
            )
        self.handlers[handler.handler_name] = handler
        self.debug(f"Handler {handler.handler_name!r} added to phanos profiler")

    def delete_handler(self, handler_name: str) -> None:
        """Delete handler from profiler

        :param handler_name: name of handler:
        :raises KeyError: if handler do not exist
        """
        try:
            _ = self.handlers.pop(handler_name)
        except KeyError:
            self.warning(f"{self.delete_handler.__qualname__!r}: handler {handler_name!r} do not exist")
            return
        self.debug(f"handler {handler_name!r} deleted")

    def delete_handlers(self) -> None:
        """delete all handlers"""
        self.handlers.clear()
        self.debug("all handlers deleted")

    def set_curr_node(self, func: tp.Callable) -> MethodTreeNode:
        """Set ContextVar `curr_node` to new node with given function and add it to MethodContext tree

        :param func: function to be added as node to MethodContext tree
        """
        try:
            current_node = curr_node.get()
        except LookupError:
            curr_node.set(self.tree.root)
            current_node = self.tree.root
        current_node = current_node.add_child(MethodTreeNode(func, self.logger))
        curr_node.set(current_node)
        return current_node

    def delete_curr_node(self, current_node: MethodTreeNode) -> None:
        """Set ContextVar `curr_node` to parent of current node and delete current node from MethodContext tree

        :param current_node: node to be deleted
        """
        curr_node.set(current_node.parent)
        found = self.tree.find_and_delete_node(current_node)
        if not found:  # this won't happen if nobody messes with tree
            self.warning(f"{self.tree.find_and_delete_node.__qualname__}: node {current_node.ctx!r} was not found")

    def measure_execution_start(self) -> tp.Optional[datetime]:
        """Measure execution start time and return it"""
        # phanos before each decorated function profiling
        start_ts = None
        if self.time_profile:
            start_ts = datetime.now()
        return start_ts

    def before_func_profiling(
        self, func: tp.Callable, args: tp.Tuple[tp.Any, ...], kwargs: tp.Dict[str, tp.Any]
    ) -> tp.Optional[datetime]:
        """Method for handling before function profiling chores

        :param func: function to be profiled
        :param args: function arguments
        :param kwargs: function keyword arguments
        """
        if curr_node.get().parent == self.tree.root:
            if callable(self.before_root_func):
                self.before_root_func(func, args, kwargs)
            # place for phanos before root profiling, if it will be needed
        if callable(self.before_func):
            self.before_func(func, args, kwargs)
        return self.measure_execution_start()

    def after_function_profiling(
        self,
        result: tp.Any,
        start_ts: datetime,
        args: tp.Tuple[tp.Any, ...],
        kwargs: tp.Dict[str, tp.Any],
    ) -> None:
        """Method for handling after function profiling chores

        :param result: result of profiled function
        :param start_ts: start time of function execution
        :param args: function arguments
        :param kwargs: function keyword arguments
        """
        if self.time_profile:
            self.time_profile.stop(start=start_ts, label_values={})
        if callable(self.after_func):
            # users custom metrics profiling after every decorated function if method passed
            self.after_func(result, args, kwargs)
        if curr_node.get().parent is self.tree.root:
            # phanos after root function profiling
            if self.resp_size_profile:
                self.resp_size_profile.rec(value=result, label_values={})
            if callable(self.after_root_func):
                # users custom metrics profiling after root function if method passed
                self.after_root_func(result, args, kwargs)

    def profile(self, func: tp.Callable[..., tp.Any]) -> tp.Callable[..., tp.Any]:
        """Decorator for profiling functions"""

        @wraps(func)
        def sync_inner(*args, **kwargs) -> tp.Any:
            """sync profiling"""
            return self.profile_ext.sync_inner(func, *args, **kwargs)

        @wraps(func)
        async def async_inner(*args, **kwargs) -> tp.Any:
            """async profiling"""
            return await self.profile_ext.async_inner(func, *args, **kwargs)

        if inspect.iscoroutinefunction(func):
            return async_inner
        return sync_inner


class SyncExtProfiler(log.InstanceLoggerMixin, AbstractExtProfiler):
    """Class responsible for SYNC profiling and handling of measured values"""

    base_profiler: Profiler

    def __init__(self, base_profiler: Profiler) -> None:
        self.base_profiler = base_profiler
        super().__init__(logger=base_profiler.logger)

    def handle_records_clear(self) -> None:
        for metric in self.base_profiler.metrics.values():
            records = metric.to_records()
            metric.cleanup()
            if not records:
                continue
            for handler in self.base_profiler.handlers.values():
                self.debug("handler %s handling metric %s", handler.handler_name, metric.name)
                handler.handle(records, metric.name)

    def force_handle_records_clear(self) -> None:
        self.debug("Forcing record handling")
        self.handle_records_clear()
        self.base_profiler.tree.clear()

    def sync_inner(self, func: tp.Callable[..., tp.Any], *args, **kwargs) -> tp.Any:
        if not self.base_profiler.needs_profiling():
            return func(*args, **kwargs)

        result = None
        current_node = self.base_profiler.set_curr_node(func)
        start_ts = self.base_profiler.before_func_profiling(func, args, kwargs)
        try:
            result: tp.Any = func(*args, **kwargs)
        except Exception:
            raise
        finally:
            self.base_profiler.after_function_profiling(result, start_ts, args, kwargs)
            if (
                current_node.parent is self.base_profiler.tree.root
                or self.base_profiler.get_records_count() >= Profiler.RECORDS_LEN_LIMIT
            ):
                self.handle_records_clear()
            self.base_profiler.delete_curr_node(current_node)

        return result

    async def async_inner(self, func: tp.Callable[..., tp.Any], *args, **kwargs) -> tp.Any:
        if not self.base_profiler.needs_profiling():
            return await func(*args, **kwargs)

        result = None
        current_node = self.base_profiler.set_curr_node(func)
        start_ts = self.base_profiler.before_func_profiling(func, args, kwargs)
        try:
            result: tp.Any = await func(*args, **kwargs)
        except Exception:
            raise
        finally:
            self.base_profiler.after_function_profiling(result, start_ts, args, kwargs)
            if (
                current_node.parent is self.base_profiler.tree.root
                or self.base_profiler.get_records_count() >= Profiler.RECORDS_LEN_LIMIT
            ):
                self.handle_records_clear()
            self.base_profiler.delete_curr_node(current_node)

        return result


class AsyncExtProfiler(log.InstanceLoggerMixin, AbstractExtProfiler):
    base_profiler: Profiler

    def __init__(self, base_profiler: Profiler) -> None:
        self.base_profiler = base_profiler

        super().__init__(logger=base_profiler.logger)

    async def handle_records_clear(self) -> None:
        for metric in self.base_profiler.metrics.values():
            records = metric.to_records()
            metric.cleanup()
            if not records:
                continue
            for handler in self.base_profiler.handlers.values():
                self.debug("handler %s handling metric %s", handler.handler_name, metric.name)
                if isinstance(handler, AsyncBaseHandler):
                    await handler.handle(records, metric.name)
                else:
                    handler.handle(records, metric.name)

    async def force_handle_records_clear(self) -> None:
        self.debug("Forcing record handling")
        await self.handle_records_clear()
        self.base_profiler.tree.clear()

    def sync_inner(self, func: tp.Callable[..., tp.Any], *args, **kwargs) -> tp.Any:
        if not self.base_profiler.needs_profiling():
            return func(*args, **kwargs)

        result = None
        current_node = self.base_profiler.set_curr_node(func)
        start_ts = self.base_profiler.before_func_profiling(func, args, kwargs)
        try:
            result: tp.Any = func(*args, **kwargs)
        except Exception:
            raise
        finally:
            self.base_profiler.after_function_profiling(result, start_ts, args, kwargs)
            if self.base_profiler.get_records_count() >= Profiler.RECORDS_ERR_LIMIT:
                self.error("Too many records, clearing records")
                for metric in self.base_profiler.metrics.values():
                    metric.cleanup()
            self.base_profiler.delete_curr_node(current_node)

        return result

    async def async_inner(self, func: tp.Callable[..., tp.Any], *args, **kwargs) -> tp.Any:
        if not self.base_profiler.needs_profiling():
            return await func(*args, **kwargs)

        result = None
        current_node = self.base_profiler.set_curr_node(func)
        start_ts = self.base_profiler.before_func_profiling(func, args, kwargs)
        try:
            result: tp.Any = await func(*args, **kwargs)
        except Exception:
            raise
        finally:
            self.base_profiler.after_function_profiling(result, start_ts, args, kwargs)
            if (
                current_node.parent is self.base_profiler.tree.root
                or self.base_profiler.get_records_count() >= Profiler.RECORDS_LEN_LIMIT
            ):
                await self.handle_records_clear()
            self.base_profiler.delete_curr_node(current_node)
        return result


class OutputFormatter:
    """class for converting Record type into profiling string"""

    @staticmethod
    def record_to_str(name: str, record: Record) -> str:
        """converts Record type into profiling string

        :param name: name of profiler
        :param record: metric record which to convert
        """
        value = record["value"][1]
        labels = record.get("labels")
        if not labels:
            return f"profiler: {name}, " f"method: {record.get('method')}, " f"value: {value} {record.get('units')}"
        # format labels as this "key=value, key2=value2"
        str_labels = ""
        if isinstance(labels, dict):
            str_labels = "labels: " + ", ".join(f"{k}={v}" for k, v in labels.items())
        return (
            f"profiler: {name}, "
            f"method: {record.get('method')}, "
            f"value: {value} {record.get('units')}, "
            f"{str_labels}"
        )


class BaseHandler(ABC):
    """base class for record handling"""

    handler_name: str

    def __init__(self, handler_name: str) -> None:
        """
        :param handler_name: name of handler. used for managing handlers"""
        self.handler_name = handler_name


class AsyncBaseHandler(BaseHandler, ABC):  # pragma: no cover
    @classmethod
    @abstractmethod
    async def create(cls, handler_name: str, *args, **kwargs) -> AsyncBaseHandler:
        """AsyncBaseHandler factory method, used for asynchronous handler creation

        :param handler_name: name of handler. used for managing handlers
        :param args: other positional arguments
        :param kwargs: other keyword arguments
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(
        self,
        records: tp.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        """Handle records asynchronously

        :param records: list of records to handle
        :param profiler_name: name of profiler
        """
        raise NotImplementedError


class SyncBaseHandler(BaseHandler, ABC):  # pragma: no cover
    @abstractmethod
    def handle(
        self,
        records: tp.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        """Handle records

        :param records: list of records to handle
        :param profiler_name: name of profiler
        """
        raise NotImplementedError


def log_error_profiling(name: str, formatter: OutputFormatter, logger: LoggerLike, records: tp.List[Record]) -> None:
    """Logs records only if some of profiled methods raised error and error_raised label is present in records

    :param name: name of profiler
    :param formatter: instance of OutputFormatter
    :param logger: logger
    :param records: list of records
    """
    if not records or records[0].get("labels", {}).get("error_raised") is None:
        return
    error_raised = False
    for record in records:
        if record.get("labels", {}).get("error_raised", "False") == "True":
            error_raised = True
            break

    if error_raised:
        converted = []
        for record in records:
            converted.append(formatter.record_to_str(name, record))
        out = "\n".join(converted)
        logger.debug(out)


class ImpProfHandler(SyncBaseHandler):
    """Blocking RabbitMQ record handler"""

    publisher: BlockingPublisher
    formatter: OutputFormatter
    logger: tp.Optional[LoggerLike]

    def __init__(
        self,
        handler_name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: tp.Optional[str] = None,
        password: tp.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: str = "fanout",
        logger: tp.Optional[tp.Union[LoggerLike, str]] = None,
        **kwargs,
    ) -> None:
        """Creates BlockingPublisher instance (connection not established yet),
         sets logger and create time profiler and response size profiler

        :param handler_name: name of handler. used for managing handlers
        :param host: rabbitMQ server host
        :param port: rabbitMQ server port
        :param user: rabbitMQ login username
        :param password: rabbitMQ user password
        :param exchange_name: exchange name to bind queue with
        :param exchange_type: exchange type to bind queue with
        :param logger: loging object to use
        :param retry: how many times to retry publish event
        :param int|float retry_delay: Time to wait in seconds, before the next
        :param timeout: If not None,
            the value is a non-negative timeout, in seconds, for the
            connection to remain blocked (triggered by Connection.Blocked from
            broker); if the timeout expires before connection becomes unblocked,
            the connection will be torn down, triggering the adapter-specific
            mechanism for informing client app about the closed connection (
            e.g., on_close_callback or ConnectionClosed exception) with
            `reason_code` of `InternalCloseReasons.BLOCKED_CONNECTION_TIMEOUT`.
        :param kwargs: other connection params, like `timeout goes here`
        :param logger: logger
        """
        super().__init__(handler_name)
        if isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger or logging.getLogger(__name__)

        self.publisher = BlockingPublisher(
            host=host,
            port=port,
            user=user,
            password=password,
            heartbeat=heartbeat,
            timeout=timeout,
            retry_delay=retry_delay,
            retry=retry,
            exchange_name=exchange_name,
            exchange_type=exchange_type,
            logger=self.logger,
            **kwargs,
        )
        try:
            self.publisher.connect()
        except NETWORK_ERRORS as err:
            self.logger.error(f"ImpProfHandler cannot connect to RabbitMQ because of {err}")
            raise RuntimeError("Cannot connect to RabbitMQ") from err

        self.publisher.close()
        self.formatter = OutputFormatter()
        self.logger.info("ImpProfHandler created successfully")

    def handle(
        self,
        records: tp.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        """Sends list of records to rabitMq queue

        :param profiler_name: name of profiler (not used)
        :param records: list of records to publish
        """

        _ = self.publisher.publish(records)
        log_error_profiling(profiler_name, self.formatter, self.logger, records)


class AsyncImpProfHandler(AsyncBaseHandler):
    """Async RabbitMQ record handler"""

    publisher: AsyncioPublisher
    formatter: OutputFormatter
    logger: LoggerLike

    def __init__(
        self,
        handler_name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: tp.Optional[str] = None,
        password: tp.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: str = "fanout",
        logger: tp.Optional[tp.Union[LoggerLike, str]] = None,
        **kwargs,
    ) -> None:
        """
        Note: use `await AsyncImpProfHandler.create()` to create instance
        """
        super().__init__(handler_name)
        if isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger or logging.getLogger(__name__)
        self.publisher = AsyncioPublisher(
            host=host,
            port=port,
            user=user,
            password=password,
            heartbeat=heartbeat,
            timeout=timeout,
            retry_delay=retry_delay,
            retry=retry,
            exchange_name=exchange_name,
            exchange_type=exchange_type,
            logger=self.logger,
            **kwargs,
        )
        self.formatter = OutputFormatter()

    @classmethod
    async def create(
        cls,
        handler_name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: tp.Optional[str] = None,
        password: tp.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: str = "fanout",
        logger: tp.Optional[LoggerLike] = None,
        **kwargs,
    ) -> AsyncImpProfHandler:
        """Creates AsyncioPublisher instance (connection not established yet),
         sets logger and create time profiler and response size profiler

        :param handler_name: name of handler. used for managing handlers
        :param host: rabbitMQ server host
        :param port: rabbitMQ server port
        :param user: rabbitMQ login username
        :param password: rabbitMQ user password
        :param heartbeat: heartbeat interval
        :param exchange_name: exchange name to bind queue with
        :param exchange_type: exchange type to bind queue with
        :param logger: loging object to use
        :param retry: how many times to retry publish event
        :param int|float retry_delay: Time to wait in seconds, before the next
        :param timeout: If not None,
            the value is a non-negative timeout, in seconds, for the
            connection to remain blocked (triggered by Connection.Blocked from
            broker); if the timeout expires before connection becomes unblocked,
            the connection will be torn down, triggering the adapter-specific
            mechanism for informing client app about the closed connection (
            e.g., on_close_callback or ConnectionClosed exception) with
            `reason_code` of `InternalCloseReasons.BLOCKED_CONNECTION_TIMEOUT`.
        :param kwargs: other connection params, like `timeout goes here`
        :param logger: logger
        """
        instance = cls(
            handler_name,
            host,
            port,
            user,
            password,
            heartbeat,
            timeout,
            retry_delay,
            retry,
            exchange_name,
            exchange_type,
            logger,
            **kwargs,
        )
        await instance._post_init()
        return instance

    async def _post_init(self):
        """Connects to RabbitMQ and closes connection to check if it is possible"""
        try:
            await self.publisher.connect()
        except NETWORK_ERRORS as err:
            self.logger.error(f"ImpProfHandler cannot connect to RabbitMQ because of {err}")
            raise RuntimeError("Cannot connect to RabbitMQ") from err

        await self.publisher.close()
        self.logger.info("ImpProfHandler created successfully")

    async def handle(
        self,
        records: tp.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        """Sends list of records to rabitMq queue

        :param profiler_name: name of profiler (not used)
        :param records: list of records to publish
        """

        _ = await self.publisher.publish(records)
        log_error_profiling(profiler_name, self.formatter, self.logger, records)


class LoggerHandler(SyncBaseHandler):
    """logger handler"""

    logger: LoggerLike
    formatter: OutputFormatter
    level: int

    def __init__(
        self,
        handler_name: str,
        logger: tp.Optional[LoggerLike] = None,
        level: int = 10,
    ) -> None:
        """

        :param handler_name: name of handler. used for managing handlers
        :param logger: logger instance if none -> creates new with name PHANOS
        :param level: level of logger in which prints records. default is DEBUG
        """
        super().__init__(handler_name)
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("PHANOS")
            self.logger.setLevel(10)
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(10)
            self.logger.addHandler(handler)
        self.level = level
        self.formatter = OutputFormatter()

    def handle(self, records: tp.List[Record], profiler_name: str = "profiler") -> None:
        """logs list of records

        :param profiler_name: name of profiler
        :param records: list of records
        """
        converted = []
        for record in records:
            converted.append(self.formatter.record_to_str(profiler_name, record))
        out = "\n".join(converted)
        self.logger.log(self.level, out)


class NamedLoggerHandler(SyncBaseHandler):
    """Logger handler initialised with name of logger rather than passing object"""

    logger: LoggerLike
    formatter: OutputFormatter
    level: int

    def __init__(
        self,
        handler_name: str,
        logger_name: str,
        level: int = logging.DEBUG,
    ) -> None:
        """
        Initialise handler and find logger by name.

        :param handler_name: name of handler. used for managing handlers
        :param logger_name: find this logger `logging.getLogger(logger_name)`
        :param level: level of logger in which prints records. default is DEBUG
        """
        super().__init__(handler_name)
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.formatter = OutputFormatter()

    def handle(self, records: tp.List[Record], profiler_name: str = "profiler") -> None:
        """logs list of records

        :param profiler_name: name of profiler
        :param records: list of records
        """
        converted = []
        for record in records:
            converted.append(self.formatter.record_to_str(profiler_name, record))
        out = "\n".join(converted)
        self.logger.log(self.level, out)


class StreamHandler(SyncBaseHandler):
    """Stream handler of Records."""

    formatter: OutputFormatter
    output: tp.TextIO

    _lock: threading.Lock

    def __init__(self, handler_name: str, output: tp.TextIO = sys.stdout) -> None:
        """

        :param handler_name: name of profiler
        :param output: stream output. Default 'sys.stdout'
        """
        super().__init__(handler_name)
        self.output = output
        self.formatter = OutputFormatter()
        self._lock = threading.Lock()

    def handle(self, records: tp.List[Record], profiler_name: str = "profiler") -> None:
        """logs list of records

        :param profiler_name: name of profiler
        :param records: list of records
        """
        for record in records:
            with self._lock:
                print(
                    self.formatter.record_to_str(profiler_name, record),
                    file=self.output,
                    flush=True,
                )
