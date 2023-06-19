""" """
from __future__ import annotations
import logging
import time
import typing

import aio_pika
from pika.exceptions import AMQPConnectionError
from logging import Logger

# from imp_prof.messaging.publisher import BlockingPublisher

from src.phanos.metrics import Record, MetricWrapper, TimeProfiler, ResponseSize
from src.phanos.tree import MethodTree


class ProfilesPublisher:
    """Class responsible for sending records to IMP_prof RabbitMQ publish queue"""

    _logger: typing.Optional[Logger]
    _publisher: typing.Optional.BlockingPublisher
    _metrics: typing.Dict[str, MetricWrapper]
    root: MethodTree
    current_node: MethodTree
    time_profile: TimeProfiler
    resp_size_profile: ResponseSize

    def __init__(
        self,
    ) -> None:
        """Initialize ProfilesPublisher

        Initialization just creates new instance!! for connection to IMP_prof use connect method!
        """
        self._logger = None
        self._publisher = None
        self._metrics = {}
        self.root = MethodTree("")
        self.current_node = self.root

        # TODO: DELETE LATER
        self._metrics["response_size"] = self.resp_size_profile = ResponseSize(
            "response_size", labels=["context"]
        )
        self._metrics["time_profiler"] = self.time_profile = TimeProfiler(
            "time_profiler", labels=["context"]
        )

    def connect(
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
    ) -> ProfilesPublisher:
        """Creates connection to Imp_prof rabbitmq queue and sets logger
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

        self._metrics["response_size"] = self.resp_size_profile = ResponseSize(
            "response_size"
        )
        self._metrics["time_profiler"] = self.time_profile = TimeProfiler(
            "time_profiler", labels=["context"]
        )
        return self

    def disconnect(self) -> None:
        """disconnects the RabbitMQ and delete all metric instances"""
        self._publisher.close()
        self.delete_metrics()

    def delete_metric(self, item: str) -> None:
        """deletes one metric instance"""
        _ = self._metrics.pop(item, None)

    def delete_metrics(self) -> None:
        """deletes all metric instances"""
        self._metrics = {}

    def add_metric(self, metric: MetricWrapper) -> None:
        """adds new metric"""
        self._metrics[metric.item] = metric

    def publish(self, record: Record) -> bool:
        """send one record to RabbitMQ  queue"""
        return self._publisher.publish(record)

    def profile(self, func):
        """
        Decorator specifying which methods should be profiled.
        Default profiler is time profiler which measures execution time of decorated methods

        Usage: decorate methods which you want to be profiled
        """

        def inner(*args, **kwargs):
            # before request
            self.current_node = self.current_node.add_child(MethodTree(func))
            self.time_profile.start()
            # request
            result = func(*args, **kwargs)
            # after request
            self.time_profile.record_op(
                operation="stop", label_values={"context": self.current_node.method}
            )
            print(self.time_profile)
            # after request of root method
            if self.current_node.parent == self.root:
                self.resp_size_profile.record_op(
                    operation="rec", label_values={"context": self.current_node.method}
                )
                print(self.resp_size_profile)
                records = self.time_profile._to_records()
                for record in records:
                    # TODO: modify when profiler RabbitMq is available
                    print(f"Sending record: {record}")
                    try:
                        publish_res = self.publish(record)
                    except Exception:
                        publish_res = True
                    if not publish_res:
                        print(f"Failed to publish record")
                self.time_profile.cleanup()

            self.current_node = self.current_node.parent
            _ = self.current_node.children.pop(0)
            return result

        return inner

    def __getitem__(self, item: str) -> MetricWrapper:
        return self._metrics[item]


publisher: ProfilesPublisher = ProfilesPublisher()


class DummyResource:
    @publisher.profile
    def first(self):
        time.sleep(0.2)

    @publisher.profile
    def second(self):
        self.first()
        self.first()
        self.no_record()
        self.no_record()

    @publisher.profile
    def third(self):
        self.second()

    def no_record(self):
        time.sleep(0.2)
        pass

    @publisher.profile
    def post(self):
        self.second()
        self.first()
        self.third()


if __name__ == "__main__":
    test = DummyResource()
    test.post()
