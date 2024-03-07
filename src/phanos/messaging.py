import logging
import time
import typing
from abc import ABC, abstractmethod

import aio_pika
import orjson
import pika.exceptions
from aio_pika import Message
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractRobustExchange
from pika import ConnectionParameters
from pika.adapters.blocking_connection import BlockingConnection, BlockingChannel
from pika.adapters.utils.connection_workflow import AMQPConnectorException
from pika.credentials import PlainCredentials

from . import types

__all__ = (
    "LoggerLike",
    "NETWORK_ERRORS",
    "AsyncioPublisher",
    "BlockingPublisher",
)

LoggerLike = typing.Union[logging.Logger, logging.LoggerAdapter]

NETWORK_ERRORS = (
    pika.exceptions.AMQPError,
    AMQPConnectorException,
    ConnectionError,
    IOError,
)


class BasePublisher(ABC):
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
    connection_parameters: ConnectionParameters
    connection: typing.Optional[typing.Union[BlockingConnection, AbstractRobustConnection]]
    channel: typing.Optional[typing.Union[BlockingChannel, AbstractRobustChannel]]
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
        :param kwargs: other connection params, like `tcp_options` goes here
        """
        self.logger = logger or logging.getLogger(__name__)
        self.connection = None
        self.channel = None
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type.value if isinstance(exchange_type, aio_pika.ExchangeType) else exchange_type
        self.retry = max(0, retry)
        self.connection_parameters = ConnectionParameters(
            host=host,
            port=port,
            credentials=PlainCredentials(
                username=user or "guest",
                password=password or "guest",
            ),
            heartbeat=heartbeat,
            connection_attempts=max(1, self.retry),
            retry_delay=retry_delay,
            blocked_connection_timeout=timeout,
            **kwargs,
        )

    def __bool__(self) -> bool:
        """Is publisher connected?"""
        return self.is_connected() and self._is_bound()

    def is_connected(self) -> bool:
        """Connection is established?"""
        return not (self.connection is None or self.connection.is_closed)

    def _is_bound(self) -> bool:
        """Channel is established?"""
        return not (self.channel is None or self.channel.is_closed)

    @abstractmethod
    def connect(self) -> None:
        """Connect to RabbitMQ"""
        raise NotImplementedError()

    @abstractmethod
    def close(self) -> None:
        """Close connection to RabbitMQ"""
        raise NotImplementedError()

    @abstractmethod
    def publish(self, records: typing.List[types.Record]) -> bool:
        """
        Push records to message queue.
        :param records: list of records dict
        :return: was record queued?
        """
        raise NotImplementedError()


class BlockingPublisher(BasePublisher):
    """Simple blocking AMQP consumer"""

    connection: typing.Optional[BlockingConnection]
    channel: typing.Optional[BlockingChannel]

    def close(self) -> None:
        if self.is_connected():
            if self._is_bound():
                self.channel.close()
            self.connection.close()
        self.connection = None
        self.channel = None
        self.logger.info(f"{type(self).__qualname__} - closed connection")

    def connect(self) -> None:
        self.connection = BlockingConnection(self.connection_parameters)
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
        """Check if connection is established, if not - reconnect."""
        if not self:
            self.reconnect()

    def publish(self, records: typing.List[types.Record]) -> bool:
        if not records:
            return True
        attempts_left = 1 + self.retry
        bin_message = orjson.dumps(records)
        is_published = False
        self.check_or_rebound()
        while attempts_left > 0 and not is_published:
            attempts_left -= 1
            try:
                self.channel.basic_publish(
                    exchange=self.exchange_name,
                    body=bin_message,
                    routing_key=records[0]["job"],
                )
                is_published = True
            except NETWORK_ERRORS as e:
                self.logger.warning(
                    f"{type(self).__qualname__} - exchange {self.exchange_name!r} cannot "
                    f"accept message {records!r} because {e!r}"
                )
                time.sleep(float(self.connection_parameters.retry_delay))
                self.reconnect(silent=True)
        return is_published


class AsyncioPublisher(BasePublisher):
    """Simple blocking AMQP consumer"""

    __slots__ = BasePublisher.__slots__ + ("exchange",)
    connection: typing.Optional[AbstractRobustConnection]
    channel: typing.Optional[AbstractRobustChannel]
    exchange: typing.Optional[AbstractRobustExchange]

    async def close(self) -> None:
        if self.is_connected():
            if self._is_bound():
                await self.channel.close()
            await self.connection.close()
        self.connection = None
        self.channel = None
        self.logger.info(f"{type(self).__qualname__} - closed connection")

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(
            host=self.connection_parameters.host,
            port=self.connection_parameters.port,
            login=self.connection_parameters.credentials.username,
            password=self.connection_parameters.credentials.password,
            heartbeat=self.connection_parameters.heartbeat,
            connection_attempts=self.connection_parameters.connection_attempts,
            retry_delay=self.connection_parameters.retry_delay,
            blocked_connection_timeout=self.connection_parameters.blocked_connection_timeout,
        )
        self.channel = await self.connection.channel()
        await self.channel.declare_exchange(
            name=self.exchange_name,
            type=self.exchange_type,
        )
        self.logger.info(f"{type(self).__qualname__} - connection established")

    async def reconnect(self, silent: bool = False) -> None:
        """Force reconnect to server"""
        await self.close()
        if not silent:
            await self.connect()
            return
        try:
            await self.connect()
        except NETWORK_ERRORS as e:
            self.logger.warning(f"{type(self).__qualname__} - connection failed on {e!r}")

    async def check_or_rebound(self) -> None:
        if not self:
            await self.reconnect()

    async def publish(self, records: typing.List[types.Record]) -> bool:
        if not records:
            return True
        attempts_left = 1 + self.retry
        bin_message = orjson.dumps(records)
        is_published = False
        await self.check_or_rebound()
        while attempts_left > 0 and not is_published:
            attempts_left -= 1
            try:
                await self.exchange.publish(
                    message=Message(
                        body=bin_message,
                        content_type="application/json",
                    ),
                    routing_key=records[0]["job"],
                )
                is_published = True
            except NETWORK_ERRORS as e:
                self.logger.warning(
                    f"{type(self).__qualname__} - exchange {self.exchange_name!r} cannot "
                    f"accept message {records!r} because {e!r}"
                )
                time.sleep(float(self.connection_parameters.retry_delay))
                await self.reconnect(silent=True)
        return is_published
