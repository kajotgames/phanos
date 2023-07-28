""" """
from __future__ import annotations

import logging
import typing
from datetime import datetime

from .handlers import BaseHandler
from .metrics import MetricWrapper, TimeProfiler, ResponseSize, AsyncTimeProfiler
from .tree import MethodTreeNode, ContextTree
from . import log

TIME_PROFILER = "time_profiler"
RESPONSE_SIZE = "response_size"


class Profiler(log.InstanceLoggerMixin):
    """Class responsible for sending records to IMP_prof RabbitMQ publish queue"""

    metrics: typing.Dict[str, MetricWrapper]

    tree: ContextTree

    time_profile: typing.Optional[typing.Union[TimeProfiler, AsyncTimeProfiler]]
    resp_size_profile: typing.Optional[ResponseSize]

    before_func: typing.Optional[typing.Callable]
    after_func: typing.Optional[typing.Callable]
    before_root_func: typing.Optional[typing.Callable]
    after_root_func: typing.Optional[typing.Callable]

    handlers: typing.Dict[str, BaseHandler]
    handle_records: bool
    job: str
    error_occurred: bool

    def __init__(self) -> None:
        """Initialize ProfilesPublisher

        Initialization just creates new instance!!

        """

        self.metrics = {}
        self.handlers = {}
        self.job = ""
        self.error_occurred = False

        self.resp_size_profile = None
        self.time_profile = None

        self.before_func = None
        self.after_func = None
        self.before_root_func = None
        self.after_root_func = None
        super().__init__(logged_name="phanos")

    def config(
        self,
        logger=None,
        job: str = "",
        request_size_profile: bool = True,
        handle_records: bool = True,
    ) -> None:
        """configure PhanosProfiler
        :param job: name of job
        :param logger: logger instance
        :param request_size_profile: should create instance of request size profiler
        :param handle_records: should handle recorded records
        """
        self.logger = logger or logging.getLogger(__name__)
        self.job = job
        if request_size_profile:
            self.create_response_size_profiler()

        self.handle_records = handle_records

        self.tree = ContextTree(self.logger)

    def create_response_size_profiler(self) -> None:
        """create response size profiling metric"""
        self.resp_size_profile = ResponseSize(RESPONSE_SIZE, job=self.job, logger=self.logger)
        self.add_metric(self.resp_size_profile)
        self.debug("Phanos - response size profiler created")

    def delete_metric(self, item: str) -> None:
        """deletes one metric instance
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
        """deletes all custom metric instances

        :param rm_time_profile: should pre created time_profiler be deleted
        :param rm_resp_size_profile: should pre created response_size_profiler be deleted
        """
        names = list(self.metrics.keys())
        for name in names:
            if (name != TIME_PROFILER or rm_time_profile) and (name != RESPONSE_SIZE or rm_resp_size_profile):
                self.delete_metric(name)

    def clear(self):
        """clear all records from all metrics and clear method tree"""
        for metric in self.metrics.values():
            metric.cleanup()

        self.tree.current_node = self.tree.root
        self.tree.clear()

    def add_metric(self, metric: MetricWrapper) -> None:
        """adds new metric to profiling

        :param metric: metric instance
        """
        if self.metrics.get(metric.name, None):
            self.warning(f"Metric {metric.name} already exist. Overwriting with new metric")
        self.metrics[metric.name] = metric
        self.debug(f"Metric {metric.name} added to phanos profiler")

    def add_handler(self, handler: BaseHandler) -> None:
        """Add handler to profiler

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
        """Pass records to each registered Handler and clear stored records
        method DO NOT clear MethodContext tree
        """
        # send records and log em
        for metric in self.metrics.values():
            records = metric.to_records()
            for handler in self.handlers.values():
                self.debug(f"handler %s handling metric %s", handler.handler_name, metric.name)
                handler.handle(records, metric.name)
            metric.cleanup()

    def force_handle_records_clear(self) -> None:
        """Method to force records handling

        forces record handling. As side effect clears all metrics and clears MethodContext tree
        """
        # send records and log em
        self.debug("Forcing record handling")
        self.handle_records_clear()
        self.tree.current_node = self.tree.root
        self.tree.clear()


class SyncProfiler(Profiler):
    """Class responsible for sending records to IMP_prof RabbitMQ publish queue"""

    # TODO: refactor sync profiler
    def __init__(self) -> None:
        """Initialize ProfilesPublisher

        Initialization just creates new instance!!

        """

        super().__init__()

    def config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = True,
        handle_records: bool = True,
    ) -> None:
        if time_profile:
            self.create_time_profiler()
        super().config(logger, job, request_size_profile, handle_records)

    def create_time_profiler(self) -> None:
        """Create time profiling metric"""
        self.time_profile = TimeProfiler(TIME_PROFILER, job=self.job, logger=self.logger)
        self.add_metric(self.time_profile)
        self.debug("Phanos - time profiler created")

    def profile(self, func: typing.Callable) -> typing.Callable:
        """
        Decorator specifying which methods should be profiled.
        Default profiler is time profiler which measures execution time of decorated methods

        Usage: decorate methods which you want to be profiled

        :param func: method or function which should be profiled
        """

        def sync_inner(*args, **kwargs) -> typing.Any:
            """sync decorator version"""
            if self.handlers and self.handle_records:
                if self.tree.current_node is self.tree.root:
                    self.error_occurred = False

                self.tree.current_node = self.tree.current_node.add_child(MethodTreeNode(func, self.logger))

                if self.tree.current_node.parent is self.tree.root:
                    self._before_root_func(func, args, kwargs)
                self._before_func(func, args, kwargs)
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                # in case of exception handle measured records, cleanup and reraise
                self.force_handle_records_clear()
                self.error_occurred = True
                raise e
            if self.handlers and self.handle_records:
                self._after_func(result, args, kwargs)

                if self.tree.current_node.parent is self.tree.root:
                    self._after_root_func(result, args, kwargs)
                    self.handle_records_clear()
                if self.tree.current_node.parent and not self.error_occurred:
                    self.tree.current_node = self.tree.current_node.parent
                    self.tree.current_node.delete_child()
                elif not self.error_occurred:
                    self.error(f"{self.profile.__qualname__}: node {self.tree.current_node.ctx!r} have no parent.")
                    raise ValueError(f"{self.tree.current_node.ctx!r} have no parent")
            return result

        return sync_inner

    def _before_root_func(self, *args, func=None, **kwargs) -> None:
        """method executing before root function

        :param function: root function
        """
        # users custom metrics operation recording
        if callable(self.before_root_func):
            self.before_root_func(*args, func=func, **kwargs)
        # place for phanos metrics if needed

    def _after_root_func(self, fn_result, args, kwargs) -> None:
        """method executing after the root function


        :param fn_result: result of function
        """
        # phanos metrics
        if self.resp_size_profile:
            self.resp_size_profile.store_operation(
                method=self.tree.current_node.ctx.context, operation="rec", value=fn_result, label_values={}
            )
        # users custom metrics operation recording
        if callable(self.after_root_func):
            self.after_root_func(fn_result, args, kwargs)

    def _before_func(self, func, args, kwargs) -> None:
        # users custom metrics operation recording
        if callable(self.before_func):
            self.before_func(func, args, kwargs)
        # phanos metrics
        if self.time_profile:
            self.time_profile.start()

    def _after_func(self, fn_result, args, kwargs) -> None:
        # phanos metrics
        if self.time_profile and not self.error_occurred:
            self.time_profile.store_operation(
                method=self.tree.current_node.ctx.context, operation="stop", label_values={}
            )
        # users custom metrics operation recording
        if callable(self.after_func):
            self.after_func(fn_result, args, kwargs)


class AsyncProfiler(Profiler):
    """Class responsible for sending records to IMP_prof RabbitMQ publish queue"""

    def __init__(self) -> None:
        """Initialize ProfilesPublisher

        Initialization just creates new instance!!

        """

        super().__init__()

    def config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = True,
        handle_records: bool = True,
    ) -> None:
        if time_profile:
            self.create_time_profiler()
        super().config(logger, job, request_size_profile, handle_records)

    def create_time_profiler(self) -> None:
        """Create time profiling metric"""
        self.time_profile = AsyncTimeProfiler(TIME_PROFILER, job=self.job, logger=self.logger)
        self.add_metric(self.time_profile)
        self.debug("Phanos - time profiler created")

    def profile(self, func: typing.Callable) -> typing.Callable:
        """
        Decorator specifying which methods should be profiled.
        Default profiler is time profiler which measures execution time of decorated methods

        Usage: decorate methods which you want to be profiled

        :param func: method or function which should be profiled
        """

        async def async_inner(*args, **kwargs) -> typing.Any:
            """async decorator version"""
            current_node = None
            start_ts = None
            if self.handlers and self.handle_records:
                if not self.tree.root.children:
                    self.error_occurred = False
                current_node = MethodTreeNode(func, self.logger)
                creation_ts = current_node.ctx.creation_ts
                self.tree.find_context_and_insert(current_node)

                if current_node.parent == self.tree.root:
                    self._before_root_func(func, args, kwargs)
                self._before_func(func, args, kwargs)
                start_ts = datetime.now()

            try:
                result = await func(*args, **kwargs)
            except Exception as e:
                # in case of exception handle measured records, cleanup and reraise
                self.force_handle_records_clear()
                self.error_occurred = True
                raise e

            if self.handlers and self.handle_records:
                self.time_profile.store_operation(
                    method=str(current_node.ctx),
                    operation="stop",
                    label_values={},
                    start=start_ts,
                )
                self._after_func(result, args, kwargs)

                if current_node.parent == self.tree.root:
                    self._after_root_func(result, args, kwargs)
                    self.handle_records_clear()
                if not self.error_occurred:
                    self.tree.delete_node(current_node)

            return result

        return async_inner

    def _before_root_func(self, func, args, kwargs) -> None:
        """method executing before root function

        :param func: root function
        """
        # users custom metrics operation recording
        if callable(self.before_root_func):
            self.before_root_func(func, args, kwargs)
        # place for phanos metrics if needed

    def _after_root_func(self, fn_result, args, kwargs) -> None:
        """method executing after the root function


        :param fn_result: result of function
        """
        # phanos metrics
        if self.resp_size_profile:
            self.resp_size_profile.store_operation(
                method=self.tree.current_node.context, operation="rec", value=fn_result, label_values={}
            )
        # users custom metrics operation recording
        if callable(self.after_root_func):
            self.after_root_func(fn_result, args, kwargs)

    def _before_func(self, func, args, kwargs) -> None:
        # users custom metrics operation recording
        if callable(self.before_func):
            self.before_func(func, args, kwargs)
        # phanos metrics

    def _after_func(self, fn_result, args, kwargs) -> None:
        # phanos metrics
        # users custom metrics operation recording
        if callable(self.after_func):
            self.after_func(fn_result, args, kwargs)

    def force_handle_records_clear(self) -> None:
        """Method to force records handling

        forces record handling. As side effect clears all metrics and clears MethodContext tree
        """
        # send records and log em
        self.debug("Forcing record handling")
        self.handle_records_clear()
        self.tree.clear()
