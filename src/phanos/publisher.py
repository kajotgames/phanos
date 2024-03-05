""" """
from __future__ import annotations

import inspect
import logging
import sys
import threading
import typing
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
ASYNC_HANDLERS = ("AsyncImpProfHandler",)

# type of callable, which is called before execution of profiled method
BeforeType = typing.Optional[
    typing.Callable[
        [
            typing.Callable[[...], typing.Any],
            typing.List[typing.Any],
            typing.Dict[str, typing.Any],
        ],
        None,
    ]
]
# type of callable, which is called after execution of profiled method
AfterType = typing.Optional[typing.Callable[[typing.Any, typing.List[typing.Any], typing.Dict[str, typing.Any]], None]]


# TODO: BaseProfiler - now Profiler, will have methods for managing
#       SyncProfiler(BaseProfiler) - methods from Profiler: config, dict_config, profile, handle_records_clear
#       AsyncProfiler(BaseProfiler) - async dict_config, async config, async profile, async handle_records_clear


class UnsupportedHandler(Exception):
    pass


class BaseProfiler(log.InstanceLoggerMixin, ABC):
    """Base class for Profiler"""

    tree: ContextTree

    metrics: typing.Dict[str, MetricWrapper]
    time_profile: typing.Optional[TimeProfiler]
    resp_size_profile: typing.Optional[ResponseSize]

    handlers: typing.Dict[str, typing.Union[SyncBaseHandler, AsyncBaseHandler]]

    job: str
    handle_records: bool
    _error_raised_label: bool

    # space for user specific profiling logic
    before_func: BeforeType
    after_func: AfterType
    before_root_func: BeforeType
    after_root_func: AfterType

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

    # TODO: need all of these methods to be implemented??
    @abstractmethod
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
        :param settings: dictionary of desired profiling set up
        """
        raise NotImplementedError

    @abstractmethod
    def profile(self, func: typing.Callable[..., typing.Any]) -> typing.Callable[..., typing.Any]:
        """
        Decorator specifying which methods should be profiled.
        Default profiler is time profiler which measures execution time of decorated methods

        Usage: decorate methods which you want to be profiled

        :param func: method or function which should be profiled
        """
        raise NotImplementedError

    @abstractmethod
    def before_func_profiling(self, func: typing.Callable, args, kwargs) -> typing.Optional[datetime]:
        """Method for handling before function profiling chores

        Creates new MethodTreeNode instance and sets it in ContextVar for current_node,
        makes measurements needed and executes user-defined function if exists

        :param func: profiled function
        :param args: positional arguments of profiled function
        :param kwargs: keyword arguments of profiled function
        :returns: timestamp of function execution start
        """
        raise NotImplementedError

    @abstractmethod
    def after_function_profiling(self, result: typing.Any, start_ts: datetime, args, kwargs) -> None:
        """Method for handling after function profiling chores

        Deletes current node and sets ContextVar to current_node.parent,
        makes measurements needed and executes user-defined function if exists and handle measured records

        :param result: result of profiled function
        :param start_ts: timestamp measured in `self.before_function_handling`
        :param args: positional arguments of profiled function
        :param kwargs: keyword arguments of profiled function
        """
        raise NotImplementedError

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
        # send records and log em
        self.debug("Forcing record handling")
        self.handle_records_clear()
        self.tree.clear()

    def _dict_cfg_sync(self, settings: dict[str, typing.Any]) -> None:
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
            self.create_response_size_profiler()
        self.error_raised_label = settings.get("error_raised_label", True)
        self.handle_records = settings.get("handle_records", True)
        self.tree = ContextTree(self.logger)

    def config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = False,
        handle_records: bool = True,
        error_raised_label: bool = True,
        **kwargs,
    ) -> None:
        """configure profiler instance
        :param error_raised_label: if record should have label signalizing error occurrence
        :param time_profile: if time profiling should be enabled
        :param job: name of job
        :param logger: logger instance
        :param request_size_profile: should create instance of response size profiler
        :param handle_records: should handle recorded records
        :param ** kwargs: additional parameters
        """
        self.logger = logger or logging.getLogger(__name__)
        self.job = job

        self.handle_records = handle_records
        self.error_raised_label = error_raised_label

        self.tree = ContextTree(self.logger)
        # request_size_profile deprecated
        if request_size_profile or kwargs.pop("response_size_profile", False):
            self.create_response_size_profiler()
        if time_profile:
            self.create_time_profiler()

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
        """Get count of records from all metrics.

        :returns: count of records
        """
        count = 0
        for metric in self.metrics.values():
            count += len(metric.values)

        return count

    def add_handler(self, handler: typing.Union[SyncBaseHandler, AsyncBaseHandler]) -> None:
        """Add handler to profiler. If handler.name == existing handler name, existing handler will be overwritten.

        :param handler: handler instance
        """
        if self.handlers.get(handler.handler_name, None):
            self.warning(
                f"{self.add_handler.__qualname__!r}:Handler {handler.handler_name!r} already exist. Overwriting with new handler"
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

    def set_curr_node(self, func: typing.Callable) -> MethodTreeNode:
        """Set current node in MethodContext tree to new node with given function"""
        try:
            current_node = curr_node.get()
        except LookupError:
            curr_node.set(self.tree.root)
            current_node = self.tree.root
        current_node = current_node.add_child(MethodTreeNode(func, self.logger))
        curr_node.set(current_node)
        return current_node

    def delete_curr_node(self, current_node: MethodTreeNode) -> None:
        if current_node.parent is not None:
            curr_node.set(current_node.parent)
            found = self.tree.find_and_delete_node(current_node)
            if not found:  # this won't happen if nobody messes with tree
                self.warning(f"{self.tree.find_and_delete_node.__qualname__}: node {current_node.ctx!r} was not found")

        else:  # this won't happen if nobody messes with tree
            self.error(f"{self.profile.__qualname__}: node {current_node.ctx!r} have no parent.")
            raise ValueError(f"{current_node.ctx!r} have no parent")

    def measure_execution_start(self) -> typing.Optional[datetime]:
        """Measure execution start time and return it"""
        # phanos before each decorated function profiling
        start_ts = None
        if self.time_profile:
            start_ts = datetime.now()
        return start_ts


class Profiler(BaseProfiler):
    """Class responsible for SYNC profiling and handling of measured values"""

    # space for user specific profiling logic
    before_func: BeforeType
    after_func: AfterType
    before_root_func: BeforeType
    after_root_func: AfterType

    def dict_config(self, settings: dict[str, typing.Any]) -> None:
        from . import config as phanos_config

        self._dict_cfg_sync(settings)
        if "handlers" in settings:
            try:
                named_handlers = phanos_config.create_handlers(settings["handlers"])
            except UnsupportedHandler:
                self.error(f"Cannot create async handler in sync profiler")
                raise
            for handler in named_handlers.values():
                self.add_handler(handler)

    def handle_records_clear(self) -> None:
        for metric in self.metrics.values():
            records = metric.to_records()
            metric.cleanup()
            if not records:
                continue
            for handler in self.handlers.values():
                self.debug("handler %s handling metric %s", handler.handler_name, metric.name)
                handler.handle(records, metric.name)

    def force_handle_records_clear(self) -> None:
        self.debug("Forcing record handling")
        self.handle_records_clear()
        self.tree.clear()

    def profile(self, func: typing.Callable[..., typing.Any]) -> typing.Callable[..., typing.Any]:
        @wraps(func)
        def sync_inner(*args, **kwargs) -> typing.Any:
            """sync profiling"""
            if not self.needs_profiling():
                return func(*args, **kwargs)  # this stays

            result = None
            start_ts = self.before_func_profiling(func, args, kwargs)  # this stays
            try:
                result: typing.Any = func(*args, **kwargs)
            except Exception:
                raise
            finally:
                self.after_function_profiling(result, start_ts, args, kwargs)
            return result

        @wraps(func)
        async def async_inner(*args, **kwargs) -> typing.Any:
            """async profiling"""
            if not self.needs_profiling():
                return await func(*args, **kwargs)

            result = None
            start_ts = self.before_func_profiling(func, args, kwargs)
            try:
                result: typing.Any = await func(*args, **kwargs)
            except Exception:
                raise
            finally:
                self.after_function_profiling(result, start_ts, args, kwargs)
            return result

        if inspect.iscoroutinefunction(func):
            return async_inner
        return sync_inner

    def before_func_profiling(self, func: typing.Callable, args, kwargs) -> typing.Optional[datetime]:
        """Method for handling before function profiling chores"""
        current_node = self.set_curr_node(func)
        if current_node.parent == self.tree.root:
            if callable(self.before_root_func):
                self.before_root_func(func, args, kwargs)
            # place for phanos before root profiling, if it will be needed
        if callable(self.before_func):
            self.before_func(func, args, kwargs)
        return self.measure_execution_start()

    def after_function_profiling(self, result: typing.Any, start_ts: datetime, args, kwargs) -> None:
        if self.time_profile:
            self.time_profile.stop(start=start_ts, label_values={})
        if callable(self.after_func):
            # users custom metrics profiling after every decorated function if method passed
            self.after_func(result, args, kwargs)

        current_node = curr_node.get()
        if current_node.parent is self.tree.root:
            # phanos after root function profiling
            if self.resp_size_profile:
                self.resp_size_profile.rec(value=result, label_values={})
            if callable(self.after_root_func):
                # users custom metrics profiling after root function if method passed
                self.after_root_func(result, args, kwargs)
            self.handle_records_clear()

        if self.get_records_count() >= 20:
            self.handle_records_clear()

        self.delete_curr_node(current_node)


class AsyncProfiler(BaseProfiler):
    async def dict_config(self, settings: dict[str, typing.Any]) -> None:
        from . import config as phanos_config

        self._dict_cfg_sync(settings)
        if "handlers" in settings:
            named_handlers: typing.Dict[str, typing.Union[SyncBaseHandler, AsyncBaseHandler]]
            named_handlers = await phanos_config.create_async_handlers(settings["handlers"])
            for handler in named_handlers.values():
                self.add_handler(handler)

    def profile(self, func: typing.Callable[..., typing.Any]) -> typing.Callable[..., typing.Any]:
        @wraps(func)
        def sync_inner(*args, **kwargs) -> typing.Any:
            """sync profiling"""
            if not self.needs_profiling():
                return func(*args, **kwargs)

            result = None
            _ = self.set_curr_node(func)# TODO: maybe pass current node to before_function_handling
            start_ts = self.before_func_profiling(func, args, kwargs)
            try:
                result: typing.Any = func(*args, **kwargs)
            except Exception:
                raise
            finally:
                self.after_function_profiling(result, start_ts, args, kwargs)
                self.delete_curr_node(curr_node.get())
            return result

        @wraps(func)
        async def async_inner(*args, **kwargs) -> typing.Any:
            """async profiling"""
            if not self.needs_profiling():
                return await func(*args, **kwargs)

            result = None
            _ = self.set_curr_node(func)
            start_ts = self.before_func_profiling(func, args, kwargs)
            try:
                result: typing.Any = await func(*args, **kwargs)
            except Exception:
                raise
            finally:
                self.after_function_profiling(result, start_ts, args, kwargs)
                await self.handle_records(curr_node.get())
            return result

        if inspect.iscoroutinefunction(func):
            return async_inner
        return sync_inner

    def before_func_profiling(self, func: typing.Callable, args, kwargs) -> typing.Optional[datetime]:
        if curr_node.get().parent == self.tree.root:
            if callable(self.before_root_func):
                self.before_root_func(func, args, kwargs)
            # place for phanos before root profiling, if it will be needed
        if callable(self.before_func):
            self.before_func(func, args, kwargs)
        return self.measure_execution_start()

    async def handle_records(self, current_node: MethodTreeNode) -> None:
        if current_node.parent is self.tree.root or self.get_records_count() >= 20:
            await self.handle_records_clear()
        self.delete_curr_node(current_node)

    def after_function_profiling(self, result: typing.Any, start_ts: datetime, args, kwargs) -> None:
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

    async def handle_records_clear(self) -> None:
        for metric in self.metrics.values():
            records = metric.to_records()
            metric.cleanup()
            if not records:
                continue
            for handler in self.handlers.values():
                self.debug("handler %s handling metric %s", handler.handler_name, metric.name)
                if isinstance(handler, AsyncBaseHandler):
                    await handler.handle(records, metric.name)
                else:
                    handler.handle(records, metric.name)

    async def force_handle_records_clear(self) -> None:
        self.debug("Forcing record handling")
        await self.handle_records_clear()
        self.tree.clear()


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


class BaseHandler:
    """base class for record handling"""

    handler_name: str

    def __init__(self, handler_name: str) -> None:
        """
        :param handler_name: name of handler. used for managing handlers"""
        self.handler_name = handler_name


class AsyncBaseHandler(BaseHandler, ABC):
    @classmethod
    @abstractmethod
    async def create(cls, handler_name: str, *args, **kwargs) -> AsyncBaseHandler:
        raise NotImplementedError

    @abstractmethod
    async def handle(
        self,
        records: typing.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        raise NotImplementedError


class SyncBaseHandler(BaseHandler, ABC):
    @abstractmethod
    def handle(
        self,
        records: typing.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        raise NotImplementedError


def log_error_profiling(
    name: str, formatter: OutputFormatter, logger: LoggerLike, records: typing.List[Record]
) -> None:
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


class SyncImpProfHandler(SyncBaseHandler):
    """Blocking RabbitMQ record handler"""

    publisher: BlockingPublisher
    formatter: OutputFormatter
    logger: typing.Optional[LoggerLike]

    def __init__(
        self,
        handler_name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: typing.Optional[str] = None,
        password: typing.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: str = "fanout",
        logger: typing.Optional[LoggerLike] = None,
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
            logger=logger,
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
        records: typing.List[Record],
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
    logger: typing.Optional[LoggerLike]

    def __init__(
        self,
        handler_name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: typing.Optional[str] = None,
        password: typing.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: str = "fanout",
        logger: typing.Optional[LoggerLike] = None,
        **kwargs,
    ) -> None:
        """
        Note: use `await AsyncImpProfHandler.create()` to create instance
        """
        super().__init__(handler_name)

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
            logger=logger,
            **kwargs,
        )

    @classmethod
    async def create(
        cls,
        handler_name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: typing.Optional[str] = None,
        password: typing.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: str = "fanout",
        logger: typing.Optional[LoggerLike] = None,
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
        self.formatter = OutputFormatter()
        self.logger.info("ImpProfHandler created successfully")

    async def handle(
        self,
        records: typing.List[Record],
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
        logger: typing.Optional[LoggerLike] = None,
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

    def handle(self, records: typing.List[Record], profiler_name: str = "profiler") -> None:
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

    def handle(self, records: typing.List[Record], profiler_name: str = "profiler") -> None:
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
    output: typing.TextIO

    _lock: threading.Lock

    def __init__(self, handler_name: str, output: typing.TextIO = sys.stdout) -> None:
        """

        :param handler_name: name of profiler
        :param output: stream output. Default 'sys.stdout'
        """
        super().__init__(handler_name)
        self.output = output
        self.formatter = OutputFormatter()
        self._lock = threading.Lock()

    def handle(self, records: typing.List[Record], profiler_name: str = "profiler") -> None:
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
