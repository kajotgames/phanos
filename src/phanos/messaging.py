import logging
import time
import typing

import aio_pika
import orjson
import pika
import pika.exceptions
from pika.adapters.utils.connection_workflow import AMQPConnectorException

from . import types

__all__ = ("LoggerLike", "NETWORK_ERRORS", "BlockingPublisher")

LoggerLike = typing.Union[logging.Logger, logging.LoggerAdapter]

NETWORK_ERRORS = (
    pika.exceptions.AMQPError,
    AMQPConnectorException,
    ConnectionError,
    IOError,
)


class BlockingPublisher:
    """Simple blocking AMQP consumer"""

    __slots__ = (
        "exchange_name",
        "exchange_type",
        "connection_parameters",
        "connection",
        "channel",
        "retry",
        "logger",
    )
    exchange_name: str
    exchange_type: str
    connection_parameters: pika.ConnectionParameters
    connection: typing.Optional[pika.BlockingConnection]
    channel: typing.Optional[pika.adapters.blocking_connection.BlockingChannel]
    retry: int
    logger: LoggerLike

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5672,
        user: typing.Optional[str] = None,
        password: typing.Optional[str] = None,
        heartbeat: int = 47,
        timeout: float = 23,
        retry_delay: float = 0.137,
        retry: int = 3,
        exchange_name: str = "profiling",
        exchange_type: typing.Union[str, aio_pika.ExchangeType] = aio_pika.ExchangeType.FANOUT,
        logger: typing.Optional[LoggerLike] = None,
        **kwargs,
    ) -> None:
        """
        Define publisher. Connection is not established yet. See `self.publish` or `self.connect`.

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
        """
        _ = kwargs
        self.logger = logger or logging.getLogger(__name__)
        self.connection = None
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type.value if isinstance(exchange_type, aio_pika.ExchangeType) else exchange_type
        self.retry = max(0, retry)
        self.connection_parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=pika.credentials.PlainCredentials(
                username=user or "guest",
                password=password or "guest",
            ),
            heartbeat=heartbeat,
            connection_attempts=max(1, self.retry),
            retry_delay=retry_delay,
            blocked_connection_timeout=timeout,
        )

    def __bool__(self) -> bool:
        return self.is_connected() and self._is_bound()

    def is_connected(self) -> bool:
        return not (self.connection is None or not self.connection.is_open)

    def _is_bound(self) -> bool:
        return not (self.channel is None or not self.channel.is_open)

    def close(self) -> None:
        if self.is_connected():
            if self._is_bound():
                self.channel.close()
            self.connection.close()
        self.connection = None
        self.channel = None
        self.logger.info(f"{type(self).__qualname__} - closed connection")

    def connect(self) -> None:
        self.connection = pika.BlockingConnection(self.connection_parameters)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(
            exchange=self.exchange_name,
            exchange_type=self.exchange_type,
        )
        self.logger.info(f"{type(self).__qualname__} - connection established")

    def reconnect(self, silent: bool = False) -> None:
        """Force reconnect to server"""
        self.close()
        if not silent:
            self.connect()
            return
        try:
            self.connect()
        except NETWORK_ERRORS as e:
            self.logger.warning(f"{type(self).__qualname__} - connection failed on {e!r}")

    def check_or_rebound(self) -> None:
        if not self:
            self.close()
            self.connect()

    def publish(self, record: types.Record) -> bool:
        """
        Push record to message queue.
        :param record: record dict
        :return: was record queued?
        """
        attempts_left = 1 + self.retry
        bin_message = orjson.dumps(record)
        is_published = False
        self.check_or_rebound()
        while attempts_left > 0 and not is_published:
            attempts_left -= 1
            try:
                self.channel.basic_publish(
                    exchange=self.exchange_name,
                    body=bin_message,
                    routing_key=record["job"],
                )
                is_published = True
            except NETWORK_ERRORS as e:
                self.logger.warning(
                    f"{type(self).__qualname__} - exchange {self.exchange_name!r} cannot "
                    f"accept message {record!r} because {e!r}"
                )
                time.sleep(float(self.connection_parameters.retry_delay))
                self.reconnect(silent=True)
        return is_published
