""" """
from __future__ import annotations
import logging
import sys
import typing
from datetime import datetime as dt
from functools import wraps

import aio_pika
from imp_prof.messaging.publisher import BlockingPublisher
from imp_prof.types import Record
from pika.exceptions import AMQPConnectionError
from flask import request, current_app as app

from logging import Logger


class MetricWrapper:
    """Wrapper around all Prometheus metric types"""

    item: str
    method: str
    job: str
    metric: str
    _values: typing.List[
        typing.Union[float, str, tuple[str, typing.Union[float, dict[str, typing.Any]]]]
    ]
    label_names: typing.Optional[typing.List[str]]
    _label_values: typing.Optional[typing.List[typing.Dict[str, str]]]
    operations: typing.Dict[str, typing.Callable]
    default_operation: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        self.item = item
        self.units = units
        self._values = []
        self.method = ""
        self.job = ""
        self.label_names = list(set(labels)) if labels else []
        self._label_values = []
        self.operations = {}
        self.default_operation = ""
        publisher.add_metric(self)

    def _to_records(self):
        """Convert measured values into Type Record
        :returns: List of records"""
        records = []
        for i in range(len(self._values)):
            record: Record = {
                "item": self.item,
                "metric": self.metric,
                "units": self.units,
                "job": self.job,
                "method": self.method,
                "labels": self._label_values[i],
                "value": self._values[i],
            }
            records.append(record)

        return records

    def _check_labels(self, labels):
        measurement_labels = (
            [label_name for label_name in labels.keys()] if labels else []
        )
        if sorted(measurement_labels) == sorted(self.label_names):
            return True
        return False

    def record_op(
        self,
        operation: str = None,
        value: typing.Optional[
            typing.Union[
                float, str, tuple[str, typing.Union[float, dict[str, typing.Any]]]
            ]
        ] = None,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
        *args,
        **kwargs,
    ) -> None:
        """Stores one record of the given operation

        method common for all metrics. Saves labels_values and call method specified
        in operation parameter.

        :param operation: string identifying operation
        :param value: measured value
        :param label_values: values of labels
        :param args: will be passed to specific operation of given metric
        :param kwargs: will be passed to specific operation of given metric
        :raise ValueError: if operation does not exist for given metric.
        """
        with app.app_context():
            if self.job == "":
                self.job = app.import_name.split(".")[0].upper()
            self.method = request.method
        try:
            print(label_values)
            labels_ok = self._check_labels(label_values)
            if labels_ok and label_values is not None:
                self._label_values.append(label_values)
            elif labels_ok:
                self._label_values.append({})
            else:
                raise ValueError("Unknown or missing label")
            if operation is None:
                operation = self.default_operation
            self.operations[operation](value, args, kwargs)
        except KeyError:
            raise ValueError("Unknown operation")

    def cleanup(self):
        """Cleanup after metrics was sent"""
        self._values = []
        self._label_values = []


class Histogram(MetricWrapper):
    """class representing histogram metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Histogram metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "histogram"
        self.default_operation = "observe"
        self.operations = {"observe": self._observe}

    def _observe(self, value: float, *args, **kwargs) -> None:
        """Method representing observe action of Histogram
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            raise TypeError("Value must be float")
        self._values.append(("observe", value))


class Summary(MetricWrapper):
    """class representing summary metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Summary metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "summary"
        self.default_operation = "observe"
        self.operations = {"observe": self._observe}

    def _observe(self, value: float, *args, **kwargs) -> None:
        """Method representing observe action of Summary
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            raise TypeError("Value must be float")
        self._values.append(("observe", value))


class Counter(MetricWrapper):
    """class representing counter metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Counter metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "counter"
        self.default_operation = "inc"
        self.operations = {"inc": self._inc}

    def _inc(self, value: float, *args, **kwargs) -> None:
        """Method representing inc action of counter
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            raise TypeError("Value must be float > 0")
        self._values.append(("inc", value))


class Info(MetricWrapper):
    """class representing info metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Info metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "info"
        self.default_operation = "info"
        self.operations = {"info": self._info}

    def _info(
        self, value: typing.Dict[typing.Any, typing.Any], *args, **kwargs
    ) -> None:
        """Method representing info action of info
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, dict):
            raise ValueError("Value must be dictionary")
        self._values.append(("info", value))


class Gauge(MetricWrapper):
    """class representing gauge metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Gauge metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "gauge"
        self.default_operation = "inc"
        self.operations = {
            "inc": self._inc,
            "dec": self._dec,
            "set": self._set,
        }

    def _inc(self, value: float, *args, **kwargs) -> None:
        """Method representing inc action of gauge
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            raise TypeError("Value must be float >= 0")
        self._values.append(("inc", value))

    def _dec(self, value: float, *args, **kwargs) -> None:
        """Method representing dec action of gauge
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            raise TypeError("Value must be float >= 0")
        self._values.append(("dec", value))

    def _set(self, value: float, *args, **kwargs) -> None:
        """Method representing set action of gauge
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            raise TypeError("Value must be float")
        self._values.append(("set", value))


class Enum(MetricWrapper):
    """class representing enum metric of Prometheus"""

    metric: str
    states: typing.List[str]

    def __init__(
        self,
        item: str,
        units: str,
        states: typing.List[str],
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Enum metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param states: states which can enum have
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "enum"
        self.default_operation = "state"
        self.states = states
        self.operations = {"state": self._state}

    def _state(self, value: str, *args, **kwargs) -> None:
        """Method representing state action of enum
        :param value: measured value
        :raises ValueError: if value not in states at initialization
        """
        _ = args
        _ = kwargs
        if value not in self.states:
            raise TypeError(
                f"State  {value} not allowed for this Enum. Allowed values: {self.states}"
            )
        self._values.append(value)


class TimeProfiler(Histogram):
    """class for measuring multiple time records in one endpoint.
     Used for measuring time consuming operations

    measured unit is milliseconds
    """

    def __init__(
        self,
        item: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        :param item: name of metric instance viz. Type Record
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, "mS", labels)
        self.operations = {"rec": self._rec, "reset": self._reset}
        self.default_operation = "rec"
        self.start: typing.Optional[dt] = None
        self._last_stamp: typing.Optional[dt] = None
        self._tmp: typing.Optional[dt] = None
        # records in histogram.value
        self.label_names.append("action")

    def _reset(self, *args, **kwargs) -> None:
        """Resets time measurement"""
        _ = args
        _ = kwargs
        self._last_stamp = dt.now()

    def _rec(self, action: str, *args, **kwargs) -> None:
        """Records time difference between last timestamp and now
        :param action: name of measured action
        """
        _ = args
        _ = kwargs
        if self.start is None:
            self.start = dt.now()
            self._last_stamp = dt.now()
        self._tmp = dt.now()

        self._label_values[-1]["action"] = action
        print(self._label_values[-1]["action"])
        self._observe(
            (self._tmp - self._last_stamp).total_seconds() * 1000.0,
        )
        self._last_stamp = self._tmp

    def _check_labels(self, labels):
        labels_to_check = labels.append({"action": 1}) if labels else {"action": 1}
        measurement_labels = [label_name for label_name in labels_to_check.keys()]
        if sorted(measurement_labels) == sorted(self.label_names):
            return True
        return False

    def cleanup(self):
        super().cleanup()
        self._last_stamp = None
        self.start = None
        self._tmp = None

    def __str__(self):
        full_name = self.item or "n-a"
        actions_timestamps = ", ".join(
            (
                "{} {}".format(self._label_values[i]["action"], self._values[i][1])
                for i in range(len(self._values))
            )
        )
        return "profile %s - %s - total %s - steps %s" % (
            self.start,
            full_name,
            ((self._last_stamp - self.start).total_seconds() * 1000.0),
            actions_timestamps,
        )


class ResponseSize(Histogram):
    def __init__(
        self,
        item: str,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        :param item: name of metric instance viz. Type Record
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, "B", labels)
        self.operations = {"rec": self._rec}
        self.default_operation = "rec"

    def _rec(self, value: bytes, *args, **kwargs):
        _ = args
        _ = kwargs
        with app.app_context():
            self._observe(float(sys.getsizeof(value)))

    def __str__(self):
        return "Response size record: %s" % self._values


class ProfilesPublisher:
    """Class responsible for sending records to IMP_prof RabbitMQ publish queue

    Example of usage: ..
        ...
        from phanos import publisher
        ...
        publisher.connect(**connection_params)
        ...
        *metrics initialization*
        ...
        @publisher.send_profiling()
        def get(self):
            ...
            publisher["measure_db_access"].record_op("rec", 5.1, "post_item", [asd,asd])
            ...
            publisher["next_metric"].record_op("inc", 2, [asd,asd])
            ...
            return {'success': 1}, 200
    """

    _logger: typing.Optional[Logger]
    _publisher: typing.Optional.BlockingPublisher
    _metrics: typing.Dict[str, MetricWrapper]

    def __init__(
        self,
    ) -> None:
        """Initialize ProfilesPublisher

        Initialization just creates new instance!! for connection to IMP_prof use connect method!
        """
        self._logger = None
        self._publisher = None
        self._metrics = {}

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
        self._metrics["response_size"] = ResponseSize("response_size")
        return self

    def disconnect(self):
        """disconnects the RabbitMQ and delete all metric instances"""
        self._publisher.close()
        # self.delete_metrics()

    def delete_metric(self, item: str):
        """deletes one metric instance"""
        _ = self._metrics.pop(item, None)

    def delete_metrics(self):
        """deletes all metric instances"""
        self._metrics = {}

    def add_metric(self, metric: MetricWrapper):
        """adds new metric"""
        self._metrics[metric.item] = metric

    def publish(self, record):
        """send one record to RabbitMQ  queue"""
        return self._publisher.publish(record)

    def send_profiling(self, measure_response_size: bool = False):
        """
        Decorator used for automated sending of  measured records to IMP-prof

        If you decorate endpoint method, all measured records will be sent to imp-prof after request.
        If class of metric have __str__() method defined or inherit one != Object.__str__, it will be
        logged after request. All measured records will be deleted after publishing
        Decorate endpoint method where you want to make measurements and use with combination with
        record_op() method.
        :param measure_response_size: Should response size be automatically sent?
        """

        def _send_profiling(func):
            @wraps(func)
            def inner(ep_class, *args, **kwargs):
                result = func(ep_class, *args, **kwargs)
                if measure_response_size:
                    self._metrics["response_size"].record_op("rec", str(result[0]))
                for metric in self._metrics.values():
                    records = metric._to_records()
                    self._logger.debug(
                        f"Sending records of metric: {metric.item}_{metric.metric}_{metric.units}"
                    )
                    for record in records:
                        print(record)
                        publish_res = self._publisher.publish(record)
                        if not publish_res:
                            self._logger.info(f"Failed to publish record")
                    if type(metric).__str__ is not object.__str__:
                        self._logger.info(f"{str(metric)}")
                    metric.cleanup()
                return result

            return inner

        return _send_profiling

    def __getitem__(self, item):
        return self._metrics[item]


publisher: ProfilesPublisher = ProfilesPublisher()
