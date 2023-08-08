""" """
from __future__ import annotations

# contextvars package is builtin but PyCharm do not recognize it
# noinspection PyPackageRequirements
import contextvars
import inspect
import logging
import typing
from datetime import datetime
from functools import wraps

from .handlers import BaseHandler
from .metrics import MetricWrapper, ResponseSize, TimeProfiler
from .tree import MethodTreeNode, ContextTree
from . import log

TIME_PROFILER = "time_profiler"
RESPONSE_SIZE = "response_size"

# context var storing currently processed node. Is not part of MethodTree because of async
curr_node = contextvars.ContextVar("curr_node")


class Profiler(log.InstanceLoggerMixin):
    """Class responsible for profiling and handling of measured values"""

    tree: ContextTree

    metrics: typing.Dict[str, MetricWrapper]
    time_profile: typing.Optional[TimeProfiler]
    resp_size_profile: typing.Optional[ResponseSize]

    handlers: typing.Dict[str, BaseHandler]

    job: str
    handle_records: bool

    # space for user specific profiling logic
    before_func: typing.Optional[typing.Callable]
    after_func: typing.Optional[typing.Callable]
    before_root_func: typing.Optional[typing.Callable]
    after_root_func: typing.Optional[typing.Callable]

    def __init__(self) -> None:
        """Initialize Profiler

        Initialization just creates new instance. Profiler NEEDS TO BE configured.
        Use Profiler.config() or Profiler.dict_config() to configure it. Profiling won't start otherwise.
        """

        self.metrics = {}
        self.handlers = {}
        self.job = ""
        self.handle_records = False

        self.resp_size_profile = None
        self.time_profile = None

        self.before_func = None
        self.after_func = None
        self.before_root_func = None
        self.after_root_func = None

        super().__init__(logged_name="phanos")

    def config(
        self,
        logger: typing.Optional[log.LoggerLike] = None,
        job: str = "",
        time_profile: bool = True,
        response_size_profile: bool = True,
        handle_records: bool = True,
    ) -> None:
        """configure profiler instance
        :param time_profile:
        :param job: name of job
        :param logger: logger instance
        :param response_size_profile: should create instance of response size profiler
        :param handle_records: should handle recorded records
        """
        self.logger = logger or logging.getLogger(__name__)
        self.job = job
        self.handle_records = handle_records

        self.tree = ContextTree(self.logger)

        if response_size_profile:
            self.create_response_size_profiler()
        if time_profile:
            self.create_time_profiler()

        self.debug("Profiler configured successfully")

    def dict_config(self, settings: dict[str, typing.Any]) -> None:
        """
        Configure profiler instance with dictionary config.
        Set up profiling from config file, instead of changing code for various environments.

        Example:
            ```
            {
                "job": "my_app",
                "logger": "my_app_debug_logger",
                "time_profile": True,
                "handle_records": True,
                "handlers": {
                    "stdout_handler": {
                        "class": "phanos.handlers.StreamHandler",
                        "handler_name": "stdout_handler",
                        "output": "ext://sys.stdout",
                    }
                }
            }
            ```
        :param settings: dictionary of desired profiling set up
        """
        from . import config as phanos_config

        if "logger" in settings:
            self.logger = logging.getLogger(settings["logger"])
        if "job" in settings:
            self.job = settings["job"]
        if settings.get("time_profile"):
            self.create_time_profiler()
        self.handle_records = settings.get("handle_records", True)
        if "handlers" in settings:
            named_handlers = phanos_config.create_handlers(settings["handlers"])
            for handler in named_handlers.values():
                self.add_handler(handler)

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
            self.error(f"{self.delete_metric.__qualname__}: metric {item} do not exist")
            raise KeyError(f"metric {item} do not exist")

        if item == "time_profiler":
            self.time_profile = None
        if item == "response_size":
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
        """Clear all records from all metrics and clear method tree"""
        for metric in self.metrics.values():
            metric.cleanup()

        self.tree.current_node = self.tree.root
        self.tree.clear()

    def add_metric(self, metric: MetricWrapper) -> None:
        """Adds new metric to profiling. If metric.name == existing metric name, existing metric will be overwritten.

        :param metric: metric instance
        """
        if self.metrics.get(metric.name, None):
            self.warning(f"Metric {metric.name} already exist. Overwriting with new metric")
        self.metrics[metric.name] = metric
        self.debug(f"Metric {metric.name} added to phanos profiler")

    def get_records_count(self) -> int:
        """Get count of records from all metrics.

        :returns: count of records
        """
        count = 0
        for metric in self.metrics.values():
            count += len(metric.values)

        return count

    def add_handler(self, handler: BaseHandler) -> None:
        """Add handler to profiler. If handler.name == existing handler name, existing handler will be overwritten.

        :param handler: handler instance
        """
        if self.handlers.get(handler.handler_name, None):
            self.warning(f"Handler {handler.handler_name} already exist. Overwriting with new handler")
        self.handlers[handler.handler_name] = handler
        self.debug(f"Handler {handler.handler_name} added to phanos profiler")

    def delete_handler(self, handler_name: str) -> None:
        """Delete handler from profiler

        :param handler_name: name of handler:
        :raises KeyError: if handler do not exist
        """
        try:
            _ = self.handlers.pop(handler_name)
        except KeyError:
            self.error(f"{self.delete_handler.__qualname__}: handler {handler_name} do not exist")
            raise KeyError(f"handler {handler_name} do not exist")
        self.debug(f"handler {handler_name} deleted")

    def delete_handlers(self) -> None:
        """delete all handlers"""
        self.handlers.clear()
        self.debug("all handlers deleted")

    def handle_records_clear(self) -> None:
        """Pass stored records to each registered Handler and delete stored records.
        This method DO NOT clear MethodContext tree
        """
        # send records and log em
        for metric in self.metrics.values():
            records = metric.to_records()
            for handler in self.handlers.values():
                self.debug(f"handler %s handling metric %s", handler.handler_name, metric.name)
                handler.handle(records, metric.name)
            metric.cleanup()

    def force_handle_records_clear(self) -> None:
        """Pass stored records to each registered Handler and delete stored records.

        As side effect clears all metrics and DO CLEAR MethodContext tree
        """
        # send records and log em
        self.debug("Forcing record handling")
        self.handle_records_clear()
        self.tree.clear()

    def profile(self, func: typing.Union[typing.Coroutine, typing.Callable]) -> typing.Callable:
        """
        Decorator specifying which methods should be profiled.
        Default profiler is time profiler which measures execution time of decorated methods

        Usage: decorate methods which you want to be profiled

        :param func: method or function which should be profiled
        """

        @wraps(func)
        def sync_inner(*args, **kwargs) -> typing.Any:
            """sync profiling"""
            start_ts: typing.Optional[datetime] = None
            if self.handlers and self.handle_records:
                start_ts = self.before_function_handling(func, args, kwargs)
            try:
                result: typing.Any = func(*args, **kwargs)
            except BaseException as e:
                # in case of exception handle measured records, cleanup and reraise
                if self.handlers and self.handle_records:
                    self.after_function_handling(None, start_ts, args, kwargs)
                raise e
            if self.handlers and self.handle_records:
                self.after_function_handling(result, start_ts, args, kwargs)
            return result

        @wraps(func)
        async def async_inner(*args, **kwargs) -> typing.Any:
            """async async profiling"""
            start_ts: typing.Optional[datetime] = None
            if self.handlers and self.handle_records:
                start_ts = self.before_function_handling(func, args, kwargs)
            try:
                result: typing.Any = await func(*args, **kwargs)
            except BaseException as e:
                if self.handlers and self.handle_records:
                    self.after_function_handling(None, start_ts, args, kwargs)
                raise e
            if self.handlers and self.handle_records:
                self.after_function_handling(result, start_ts, args, kwargs)
            return result

        if inspect.iscoroutinefunction(func):
            return async_inner
        return sync_inner

    def before_function_handling(self, func: typing.Callable, args, kwargs) -> typing.Optional[datetime]:
        """Method for handling before function profiling chores

        Creates new MethodTreeNode instance and sets it in ContextVar for current_node,
        makes measurements needed and executes user-defined function if exists

        :param func: profiled function
        :param args: positional arguments of profiled function
        :param kwargs: keyword arguments of profiled function
        :returns: timestamp of function execution start
        """

        try:
            current_node = curr_node.get()
        except LookupError:
            curr_node.set(self.tree.root)
            current_node = self.tree.root

        current_node = current_node.add_child(MethodTreeNode(func, self.logger))
        curr_node.set(current_node)

        if current_node.parent() == self.tree.root:
            if callable(self.before_root_func):
                # users custom metrics profiling before root function if method passed
                self.before_root_func(func, args, kwargs)
            # place for phanos before root function profiling, if it will be needed

        if callable(self.before_func):
            # users custom metrics profiling before each decorated function if method passed
            self.before_func(func, args, kwargs)

        # phanos before each decorated function profiling
        start_ts: typing.Optional[datetime] = None
        if self.time_profile:
            start_ts = datetime.now()

        return start_ts

    def after_function_handling(self, result, start_ts, args, kwargs) -> None:
        """Method for handling after function profiling chores

        Deletes current node and sets ContextVar to current_node.parent,
        makes measurements needed and executes user-defined function if exists and handle measured records

        :param result: result of profiled function
        :param start_ts: timestamp measured in `self.before_function_handling`
        :param args: positional arguments of profiled function
        :param kwargs: keyword arguments of profiled function
        """
        current_node = curr_node.get()

        if self.time_profile:
            # phanos after each decorated function profiling
            self.time_profile.store_operation(
                method=current_node.ctx.value, operation="stop", label_values={}, start=start_ts
            )

        if callable(self.after_func):
            # users custom metrics profiling after every decorated function if method passed
            self.after_func(result, args, kwargs)

        if current_node.parent() is self.tree.root:
            # phanos after root function profiling
            if self.resp_size_profile:
                self.resp_size_profile.store_operation(
                    method=current_node.ctx.value, operation="rec", value=result, label_values={}
                )
            if callable(self.after_root_func):
                # users custom metrics profiling after root function if method passed
                self.after_root_func(result, args, kwargs)
            self.handle_records_clear()

        if self.get_records_count() >= 20:
            self.handle_records_clear()

        if current_node.parent is not None:
            curr_node.set(current_node.parent())
            self.tree.find_and_delete_node(current_node)
            # self.tree.find_and_delete_node(current_node, current_node)
        else:
            self.error(f"{self.profile.__qualname__}: node {current_node.ctx!r} have no parent.")
            raise ValueError(f"{current_node.ctx!r} have no parent")
