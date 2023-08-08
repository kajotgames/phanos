from __future__ import annotations

import logging
import sys
import threading
import typing
from abc import abstractmethod


from .messaging import BlockingPublisher, NETWORK_ERRORS
from .types import Record, LoggerLike


class OutputFormatter:
    """class for converting Record type into profiling string"""

    @staticmethod
    def record_to_str(name: str, record: Record) -> str:
        """converts Record type into profiling string

        :param name: name of profiler
        :param record: metric record which to convert
        """
        value = record["value"][1]
        if not record.get("labels"):
            return f"profiler: {name}, " f"method: {record.get('method')}, " f"value: {value} {record.get('units')}"
        # format labels as this "key=value, key2=value2"
        labels = ", ".join(f"{k}={v}" for k, v in record["labels"].items())
        return (
            f"profiler: {name}, "
            f"method: {record.get('method')}, "
            f"value: {value} {record.get('units')}, "
            f"labels: {labels}"
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

        self.logger.info("ImpProfHandler created successfully")
        self.publisher.close()

    def handle(
        self,
        records: typing.List[Record],
        profiler_name: str = "profiler",
    ) -> None:
        """Sends list of records to rabitMq queue

        :param profiler_name: name of profiler (not used)
        :param records: list of records to publish
        """

        _ = profiler_name
        for record in records:
            _ = self.publisher.publish(record)


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
