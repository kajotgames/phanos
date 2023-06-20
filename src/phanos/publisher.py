""" """
from __future__ import annotations
import logging
import sys
import typing
from abc import abstractmethod

import aio_pika
from pika.exceptions import AMQPConnectionError
from logging import Logger

from imp_prof.messaging.publisher import BlockingPublisher

from src.phanos.metrics import Record, MetricWrapper, TimeProfiler, ResponseSize
from src.phanos.tree import MethodTree


TIME_PROFILER = "time_profiler"
RESPONSE_SIZE = "response_size"


class AbsHandler:
    @abstractmethod
    def handle(self, records: typing.List[Record]):
        raise NotImplementedError


class RabbitMQHandler(AbsHandler):
    """RabbitMQ Handler for Records"""

    _publisher: typing.Optional.BlockingPublisher

    def __init__(
        self,
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
        self._logger = logger or logging.getLogger(__name__)
        try:
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
            self._publisher.connect()
        except AMQPConnectionError:
            self._logger.error("ipm_prof RabbitMQ publisher cannot connect")
            raise RuntimeError("ipm_prof RabbitMQ publisher cannot connect")
        self._logger.info("ipm_prof RabbitMQ publisher connected")
        self._publisher.close()

    # TODO: need this?
    def disconnect(self) -> None:
        """disconnects from RabbitMQ"""
        self._publisher.close()

    # TODO: log unsuccessfull publish
    def handle(self, records: typing.List[Record]):
        for record in records:
            published = self._publisher.publish(record)
            print(f"imp-prof: {record}")
            if not published:
                print("was not published")


# TODO: typing, files?
#       FileHandler?
class StrHandler(AbsHandler):
    """String handler of Records."""

    def __init__(self, output: typing.TextIO = sys.stdout):
        self.output = output

    # TODO: format output
    def handle(self, records: typing.List[Record]):
        for record in records:
            print(record, file=self.output)


class LoggerHandler(AbsHandler):
    def __init__(self, logger: logging.Logger, level: int = 10):
        pass

    def handle(self, records: typing.List[Record]):
        # TODO: write by level
        pass


# TODO: Do not need.
class VoidHandler(AbsHandler):
    def handle(self, records: typing.List[Record]):
        pass


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

    _handlers: typing.List[AbsHandler]
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
        self._handlers = []

        self.request_size_profile = None
        self.time_profile = None

        if time_profile:
            self.create_time_profiler()
        if request_size_profile:
            self.create_response_size_profiler()

        self._root = MethodTree("")
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
        self._metrics = {}
        if rm_time_profile:
            self.time_profile = None
        if rm_resp_size_profile:
            self.resp_size_profile = None

    def add_metric(self, metric: MetricWrapper) -> None:
        """adds new metric"""
        self._metrics[metric.item] = metric

    def add_handler(self, handler: AbsHandler):
        """Add handler to profiler"""
        self._handlers.append(handler)

    # TODO: todo
    def delete_handlers(self, handler: AbsHandler):
        self._handlers = []

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

    # TODO: check this, maybe edit
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
                label_values={"context": self._current_node.method},
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
                operation="stop", label_values={"context": self._current_node.method}
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
            for handler in self._handlers:
                handler.handle(records)
            metric.cleanup()
