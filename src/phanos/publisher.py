""" """
from __future__ import annotations
import logging
import sys
import threading
import typing
from abc import ABC, abstractmethod

import aio_pika
import imp_prof.messaging.publisher
from logging import Logger

from imp_prof.messaging.publisher import BlockingPublisher

from src.phanos.metrics import MetricWrapper, TimeProfiler, ResponseSize
from src.phanos.tree import MethodTree


TIME_PROFILER = "time_profiler"
RESPONSE_SIZE = "response_size"


class OutputFormatter:
    @staticmethod
    def record_to_str(record: imp_prof.Record):
        if isinstance(record["value"], tuple):
            value = record["value"][1]
        else:
            value = record["value"]
        if record.get("labels", {}).get("context") is not None:
            context = ", context: " + record["labels"]["context"]
            _ = record["labels"].pop("context")
        else:
            context = ""

        if record.get("labels") is not None and len(record["labels"]) > 0:
            labels = ",labels: "
            for name, value in record["labels"].items():
                labels += name + "=" + value + ", "
            labels = labels[:-2]
        else:
            labels = ""

        return (
            "profiler: " + record["item"] + context + ", value: " + str(value) + labels
        )


class BaseHandler:
    name: str

    def __init__(self, name):
        self.name = name

    @abstractmethod
    def handle(self, records: typing.List[imp_prof.Record]):
        pass


class RabbitMQHandler(BaseHandler):
    """RabbitMQ Handler for Records"""

    _publisher: typing.Optional.BlockingPublisher
    _logger: logging.Logger

    def __init__(
        self,
        name: str,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: str = None,
        password: str = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: typing.Union[
            str, aio_pika.ExchangeType
        ] = aio_pika.ExchangeType.FANOUT,
        logger: typing.Optional[Logger] = None,
        **kwargs,
    ) -> None:
        """Creates BlockingPublisher instance (connection not established yet),
         sets logger and create time profiler and response size profiler

        :param host: RabbitMQ server host
        :param port: RabbitMQ server port
        :param user: RabbitMQ username
        :param password: RabbitMQ user password
        :param heartbeat:
        :param timeout:
        :param retry_delay:
        :param retry:
        :param exchange_name:
        :param exchange_type:
        :param logger: logger
        """
        super().__init__(name)

        self._logger = logger or logging.getLogger(__name__)
        self._publisher = BlockingPublisher(
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
            self._publisher.connect()
        except imp_prof.messaging.publisher.NETWORK_ERRORS as e:
            self._logger.error(
                f"RabbitMQHandler cannot connect to RabbitMQ because of {e}"
            )
            raise RuntimeError("Cannot connect to RabbitMQ")
        self._logger.info("RabbitMQHandler created successfully")
        self._publisher.close()

    def reconnect(self, silent: bool = False) -> None:
        """Force reconnect RabbitMQ"""
        self._publisher.reconnect(silent)

    def handle(self, records: typing.List[imp_prof.Record]):
        for record in records:
            _ = self._publisher.publish(record)


class LoggerHandler(BaseHandler):
    _logger: logging.Logger
    _formatter: OutputFormatter
    level: int

    def __init__(self, name, logger: logging.Logger = None, level: int = 10):
        super().__init__(name)
        if logger is not None:
            self._logger = logger
        else:
            self._logger = logging.getLogger(__name__)  # ???
            self._logger.setLevel(10)
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(10)
            self._logger.addHandler(handler)
        self.level = level
        self._formatter = OutputFormatter()

    def handle(self, records: typing.List[imp_prof.Record]):
        for record in records:
            self._logger.log(self.level, self._formatter.record_to_str(record))


class StreamHandler(BaseHandler):
    """String handler of Records."""

    _formatter: OutputFormatter
    output: typing.TextIO
    _lock: threading.Lock

    def __init__(self, name, output: typing.TextIO = sys.stdout):
        super().__init__(name)
        self.output = output
        self._formatter = OutputFormatter()
        self._lock = threading.Lock()

    def handle(self, records: typing.List[imp_prof.Record]):
        for record in records:
            with self._lock:
                print(
                    self._formatter.record_to_str(record), file=self.output, flush=True
                )


class PhanosProfiler:
    """Class responsible for sending records to IMP_prof RabbitMQ publish queue"""

    _logger: Logger
    _metrics: typing.Dict[str, MetricWrapper]

    _root: MethodTree
    _current_node: MethodTree

    time_profile: typing.Optional[TimeProfiler]
    resp_size_profile: typing.Optional[ResponseSize]

    before_func: typing.Optional[typing.Callable]
    after_func: typing.Optional[typing.Callable]
    before_root_func: typing.Optional[typing.Callable]
    after_root_func: typing.Optional[typing.Callable]

    _handlers: typing.Dict[str, BaseHandler]
    handle_records: bool

    def __init__(
        self,
        logger=None,
        time_profile: bool = True,
        request_size_profile: bool = True,
        handle_records: bool = True,
    ) -> None:
        """Initialize ProfilesPublisher

        Initialization just creates new instance!!
        for BlockingPublisher initialization call create_publisher(args)
        """

        self._logger = logger or logging.getLogger(__name__)
        self._metrics = {}
        self._handlers = {}

        self.request_size_profile = None
        self.time_profile = None

        if time_profile:
            self.create_time_profiler()
        if request_size_profile:
            self.create_response_size_profiler()

        self._root = MethodTree()
        self._current_node = self._root

        self.before_func = None
        self.after_func = None
        self.before_root_func = None
        self.after_root_func = None

        self.handle_records = handle_records

    def create_time_profiler(self):
        """Create time profiling metric"""
        self.time_profile = TimeProfiler(TIME_PROFILER, labels=["context"])
        self.add_metric(self.time_profile)

    def create_response_size_profiler(self):
        """create response size profiling metric"""
        self.resp_size_profile = ResponseSize(RESPONSE_SIZE, labels=["context"])
        self.add_metric(self.resp_size_profile)

    def delete_metric(self, item: str) -> None:
        """deletes one metric instance"""
        _ = self._metrics.pop(item, None)
        if item == "time_profiler":
            self.time_profile = None
        if item == "response_size":
            self.resp_size_profile = None

    def delete_metrics(
        self, rm_time_profile: bool = False, rm_resp_size_profile: bool = False
    ) -> None:
        """deletes all custom metric instances

        :param rm_time_profile: should pre created time_profiler be deleted
        :param rm_resp_size_profile: should pre created response_size_profiler be deleted
        """
        self._metrics.clear()
        if rm_time_profile:
            self.time_profile = None
        if rm_resp_size_profile:
            self.resp_size_profile = None

    def add_metric(self, metric: MetricWrapper) -> None:
        """adds new metric"""
        self._metrics[metric.item] = metric

    def add_handler(self, handler: BaseHandler):
        """Add handler to profiler"""
        self._handlers[handler.name] = handler

    def delete_handler(self, handler_name: str) -> None:
        _ = self._handlers.pop(handler_name, None)

    def delete_handlers(self):
        self._handlers.clear()

    def profile(self, func):
        """
        Decorator specifying which methods should be profiled.
        Default profiler is time profiler which measures execution time of decorated methods

        Usage: decorate methods which you want to be profiled
        """

        # TODO: check this with own metric
        def inner(*args, **kwargs):
            if self._handlers != [] and self.handle_records:
                if self._current_node.parent == self._root:
                    self._before_root_func(func)

                self._current_node = self._current_node.add_child(MethodTree(func))

                self._before_func(func)

            result = func(*args, **kwargs)

            if self._handlers != [] and self.handle_records:
                self._after_func(result)

                if self._current_node.parent == self._root:
                    self._after_root_func(result)
                    self.handle_records_clear()

                self._current_node = self._current_node.parent
                self._current_node.delete_child()
            return result

        return inner

    # TODO: check this later, maybe edit
    def _before_root_func(self, function: typing.Callable):
        # custom
        if callable(self.before_root_func):
            self.before_root_func(function=function)
        # here mine if needed

    def _after_root_func(self, fn_result):
        # mine
        if self.resp_size_profile:
            self.resp_size_profile.store_operation(
                operation="rec",
                value=fn_result,
                label_values={"context": self._current_node.context},
            )
        # user custom function
        if callable(self.after_root_func):
            self.after_root_func(fn_result=fn_result)

    def _before_func(self, func):
        # user custom
        if callable(self.before_func):
            self.before_func(function=func)
        # mine
        if self.time_profile:
            self.time_profile.start()

    def _after_func(self, fn_result: typing.Any):
        # mine
        if self.time_profile:
            self.time_profile.store_operation(
                operation="stop", label_values={"context": self._current_node.context}
            )
        # custom
        if callable(self.after_func):
            self.after_func(fn_result=fn_result)

    # TODO: make this better
    def handle_records_clear(self):
        """Pass records to each registered Handler and clear stored records"""
        # send records and log em
        for metric in self._metrics.values():
            records = metric._to_records()
            for handler in self._handlers.values():
                handler.handle(records)
            metric.cleanup()
