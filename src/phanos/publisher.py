""" """
from __future__ import annotations

import inspect
import logging
import sys
import threading
import typing
from abc import abstractmethod
from datetime import datetime
from functools import wraps

from . import log
from .messaging import BlockingPublisher, NETWORK_ERRORS
from .tree import ContextTree, curr_node
from .metrics import MetricWrapper, TimeProfiler, ResponseSize
from .tree import MethodTreeNode
from .types import LoggerLike, Record

TIME_PROFILER = "time_profiler"
RESPONSE_SIZE = "response_size"

BeforeType = typing.Optional[
    typing.Callable[[typing.Callable[[...], typing.Any], typing.List[typing.Any], typing.Dict[str, typing.Any]], None]
]
AfterType = typing.Optional[typing.Callable[[typing.Any, typing.List[typing.Any], typing.Dict[str, typing.Any]], None]]


class Profiler(log.InstanceLoggerMixin):
    """Class responsible for profiling and handling of measured values"""

    tree: ContextTree

    metrics: typing.Dict[str, MetricWrapper]
    time_profile: typing.Optional[TimeProfiler]
    resp_size_profile: typing.Optional[ResponseSize]

    handlers: typing.Dict[str, BaseHandler]

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

    def config(
        self,
        logger=None,
        job: str = "",
        time_profile: bool = True,
        request_size_profile: bool = False,
        handle_records: bool = True,
        error_raised_label: bool = True,
    ) -> None:
        """configure profiler instance
        :param error_raised_label: if record should have label signalizing error occurrence
        :param time_profile: if time profiling should be enabled
        :param job: name of job
        :param logger: logger instance
        :param request_size_profile: should create instance of response size profiler
        :param handle_records: should handle recorded records
        """
        self.logger = logger or logging.getLogger(__name__)
        self.job = job

        self.handle_records = handle_records
        self.error_raised_label = error_raised_label

        self.tree = ContextTree(self.logger)

        if request_size_profile:
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
        from . import config as phanos_config

        if "logger" in settings:
            self.logger = logging.getLogger(settings["logger"])
        if "job" not in settings:
            self.logger.error("Job argument not found in config dictionary")
            raise KeyError("Job argument not found in config dictionary")
        self.job = settings["job"]
        if settings.get("time_profile"):
            self.create_time_profiler()
        if settings.get("request_size_profile"):
            self.create_response_size_profiler()
        self.error_raised_label = settings.get("error_raised_label", True)
        self.handle_records = settings.get("handle_records", True)
        if "handlers" in settings:
            named_handlers = phanos_config.create_handlers(settings["handlers"])
            for handler in named_handlers.values():
                self.add_handler(handler)

        self.tree = ContextTree(self.logger)

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

        self.tree.clear()

    def add_metric(self, metric: MetricWrapper) -> None:
        """Adds new metric to profiling. If metric.name == existing metric name, existing metric will be overwritten.
        Side effect: if `self.error_raised_label` True then additional label 'error_raised' is added into metric.

        :param metric: metric instance
        """
        if self.metrics.get(metric.name, None):
            self.warning(f"Metric {metric.name} already exist. Overwriting with new metric")
        if self.error_raised_label:
            metric.label_names.append("error_raised")
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
                self.debug("handler %s handling metric %s", handler.handler_name, metric.name)
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

    def profile(self, func: typing.Callable[..., typing.Any]) -> typing.Callable[..., typing.Any]:
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
            except BaseException as err:
                # in case of exception handle measured records, cleanup and reraise
                if self.handlers and self.handle_records:
                    self.after_function_handling(None, start_ts, args, kwargs)
                raise err
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
            except BaseException as err:
                if self.handlers and self.handle_records:
                    self.after_function_handling(None, start_ts, args, kwargs)
                raise err
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

    def after_function_handling(self, result: typing.Any, start_ts: datetime, args, kwargs) -> None:
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
            self.time_profile.stop(start=start_ts, label_values={})

        if callable(self.after_func):
            # users custom metrics profiling after every decorated function if method passed
            self.after_func(result, args, kwargs)

        if current_node.parent() is self.tree.root:
            # phanos after root function profiling
            if self.resp_size_profile:
                self.resp_size_profile.rec(value=result, label_values={})
            if callable(self.after_root_func):
                # users custom metrics profiling after root function if method passed
                self.after_root_func(result, args, kwargs)
            self.handle_records_clear()

        if self.get_records_count() >= 20:
            self.handle_records_clear()

        if current_node.parent is not None:
            curr_node.set(current_node.parent())
            found = self.tree.find_and_delete_node(current_node)
            if not found:
                self.debug(f"{self.tree.find_and_delete_node.__qualname__}: node {current_node.ctx!r} was not found")

        else:
            self.error(f"{self.profile.__qualname__}: node {current_node.ctx!r} have no parent.")
            raise ValueError(f"{current_node.ctx!r} have no parent")

    @property
    def error_raised_label(self) -> bool:
        return self._error_raised_label

    @error_raised_label.setter
    def error_raised_label(self, value: bool):
        self._error_raised_label = value
        if not value:
            for metric in self.metrics.values():
                try:
                    _ = metric.label_names.remove("error_raised")
                except ValueError:
                    pass
        else:
            for metric in self.metrics.values():
                if "error_raised" not in metric.label_names:
                    metric.label_names.append("error_raised")


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

    @abstractmethod
    def handle(
        self,
        records: typing.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        """
        method for handling records

        :param profiler_name: name of profiler
        :param records: list of records to handle
        """
        raise NotImplementedError


class ImpProfHandler(BaseHandler):
    """RabbitMQ record handler"""

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

        for record in records:
            _ = self.publisher.publish(record)
        self.log_error_profiling(profiler_name, records)

    def log_error_profiling(self, name: str, records: typing.List[Record]):
        error_raised = False
        for record in records:
            if record.get("labels", {}).get("error_raised"):
                error_raised = True
        if error_raised:
            for record in records:
                self.logger.debug(self.formatter.record_to_str(name, record))


class LoggerHandler(BaseHandler):
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
        for record in records:
            self.logger.log(self.level, self.formatter.record_to_str(profiler_name, record))


class NamedLoggerHandler(BaseHandler):
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
        for record in records:
            self.logger.log(self.level, self.formatter.record_to_str(profiler_name, record))


class StreamHandler(BaseHandler):
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
