""" """
from __future__ import annotations
import logging
import typing
from datetime import datetime as dt

#from imp_prof.messaging.publisher import BlockingPublisher
#from imp_prof.types import Record
from pika.exceptions import AMQPConnectionError
from flask import request, current_app as app


# method to add
# TODO: record_op: default operation
# TODO: check if kwargs args needed
# TODO: arguments in kwargs
# TODO: explain how to do measure operations
# TODO: what next
# TODO: documentation how to make own metric
# TODO: fix string
class MetricWrapper:
    """Wrapper around all Prometheus metric types"""

    item: str
    method: str
    job: str
    metric: str
    values: typing.List[
        typing.Union[float, str, tuple[str, typing.Union[float, dict[str, typing.Any]]]]
    ]
    label_names: typing.Optional[typing.List[str]]
    label_values: typing.Optional[typing.List[typing.List[str]]]
    operations: typing.Dict[str, typing.Callable]

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
        self.values = []
        self.method = ""
        self.job = ""
        self.label_names = labels or []
        self.label_values = []
        self.operations = {}
        publisher._add_metric(self)

    def to_records(self):
        """Convert measured values into Type Record
        :returns: List of records"""
        records = []
        for i in range(len(self.values)):
            record: Record = {
                "item": self.item,
                "metric": self.metric,
                "units": self.units,
                "job": self.job,
                "method": self.method,
                "labels": dict(zip(self.label_names, self.label_values[i])),
                "value": self.values[i],
            }
            records.append(record)

        return records

    def record_op(
        self,
        operation: str,
        value: typing.Optional[
            typing.Union[
                float, str, tuple[str, typing.Union[float, dict[str, typing.Any]]]
            ]
        ] = None,
        label_values: typing.Optional[typing.List[str]] = None,
        *args,
        **kwargs,
    ) -> None:
        """Stores one record of the given operation

        method common for all metrics. Saves label_values and call method specified
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
            if label_values is not None:
                self.label_values.extend(label_values)
            else:
                self.label_values.append([])
            print(self.label_values)
            self.operations[operation](value, args, kwargs)
        except KeyError:
            # TODO: if not raise error -> delete last label values!!!!!!
            raise ValueError("Unknown operation")


class Histogram(MetricWrapper):
    """class representing histogram metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.Dict[str, str]] = None,
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
        self.operations = {"observe": self._observe}

    def _observe(self, value: float, *args, **kwargs) -> None:
        """Method representing observe action of Histogram
        :param value: measured value
        """
        _ = args
        _ = kwargs
        print(type(value))
        if not isinstance(value, float):
            raise TypeError("Value must be float")
        self.values.append(("observe", value))


class Summary(MetricWrapper):
    """class representing summary metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.Dict[str, str]] = None,
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
        self.operations = {"observe": self._observe}

    def _observe(self, value: float, *args, **kwargs) -> None:
        """Method representing observe action of Summary
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            raise TypeError("Value must be float")
        self.values.append(("observe", value))


class Counter(MetricWrapper):
    """class representing counter metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.Dict[str, str]] = None,
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
        self.operations = {"inc": self._inc}

    def _inc(self, value: float, *args, **kwargs) -> None:
        """Method representing inc action of counter
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            raise TypeError("Value must be float > 0")
        self.values.append(("inc", value))


class Info(MetricWrapper):
    """class representing info metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.Dict[str, str]] = None,
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
        self.operations = {"info": self._info}

    def _info(
        self,
        value: typing.Dict[typing.Any, typing.Any],
        *args,
        **kwargs,
    ) -> None:
        """Method representing info action of info
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, dict):
            raise ValueError("Value must be dictionary")
        self.values.append(("info", value))


class Gauge(MetricWrapper):
    """class representing gauge metric of Prometheus"""

    metric: str

    def __init__(
        self,
        item: str,
        units: str,
        labels: typing.Optional[typing.Dict[str, str]] = None,
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
        self.values.append(("inc", value))

    def _dec(self, value: float, *args, **kwargs) -> None:
        """Method representing dec action of gauge
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            raise TypeError("Value must be float >= 0")
        self.values.append(("dec", value))

    def _set(self, value: float, *args, **kwargs) -> None:
        """Method representing set action of gauge
        :param value: measured value
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            raise TypeError("Value must be float")
        self.values.append(("set", value))


class Enum(MetricWrapper):
    """class representing enum metric of Prometheus"""

    metric: str
    states: typing.List[str]

    def __init__(
        self,
        item: str,
        units: str,
        states: typing.List[str],
        labels: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """
        Initialize Enum metric and stores it into publisher instance

        Set values that are in Type Record.
        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param states: state which can be used
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, units, labels)
        self.metric = "enum"
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
        self.values.append(value)


class TimeProfiler(Histogram):
    """class for measuring multiple time records in one endpoint. Used for measuring time consuming operations

    measured unit is milliseconds
    """

    def __init__(
        self,
        item: str,
        labels: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """
        :param item: name of metric instance viz. Type Record
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(item, "mS", labels)
        self.operations = {"rec": self._rec, "reset": self._reset}
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

    def _rec(self, action, *args, **kwargs) -> None:
        """Records time difference between last timestamp and now
        :param action: name of measured action
        """
        _ = args
        _ = kwargs
        if self.start is None:
            self.start = dt.now()
            self._last_stamp = self.start
            self._tmp = self.start
        self._tmp = dt.now()
        print(self.label_values)

        self.label_values[-1].append(action)
        self._observe(
            (self._tmp - self._last_stamp).total_seconds() * 1000.0,
        )
        self._last_stamp = self._tmp

    def __str__(self, *args, **kwargs):
        full_name = self.item or "n-a"
        print(self.item)
        print(self.start)
        print(self._last_stamp)
        actions_timestamps = ", ".join(
            (
                "{} {}".format(self.label_values[i][-1], self.values[i])
                for i in range(len(self.values))
            )
        )
        return (
            "profile %s - %s - total %s - steps %s",
            self.start,
            full_name,
            ((self._last_stamp - self.start).microseconds / 1000.0),
            actions_timestamps,
        )


class ProfilesPublisher:
    """class responsible for sending records to IMP_prof RabbitMQ publish queue"""

    _logger: typing.Optional[logging.Logger]
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
        exchange_type: str = "fanout",
        logger: typing.Optional[logging.Logger] = None,
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
        return self

    def disconnect(self):
        """disconnects the RabbitMQ and delete all metric instances"""
        self._publisher.close()
        self.delete_metrics()
        pass

    def delete_metrics(self):
        """deletes all metric instances"""
        self._metrics = {}

    def _add_metric(self, metric: MetricWrapper):
        """adds new metric"""
        self._metrics[metric.item] = metric

    def publish(self, record):
        """send one record to RabbitMQ  queue"""
        return self._publisher.publish(record)

    # these can be used in profiler
    def send_profiling(self, func):
        """
        Decorator used for sending measured records to IMP-prof

        If you decorate endpoint method, all measured records will be send to imp-prof
        if class of metric have __str__ defined. It will be loged after request. All measured
        records will be deleted after publishing
        Decorate endpoint method where you want to make measurements and use with combination with
        record_op() method.

            'example
                ...
                from phanos import profiler
                ...
                @profiler.send_profiling
                def get(self):
                    ...
                    profiler["measure_db_access"].record_op("rec", 5.1, "post_item", [asd,asd])
                    ...
                    profiler["next_metric"].record_op("inc", 2, [asd,asd])
                    ...
                    return {'success': 1}, 200'
        """

        def inner(ep_class):
            result = func(ep_class)
            for metric in self._metrics.values():
                records = metric.to_records()
                self._logger.debug(
                    f"Sending records of metric: {metric.item}_{metric.metric}_{metric.units}"
                )
                for record in records:
                    print(record)
                    publish_res = self._publisher.publish(record)
                    if not publish_res:
                        self._logger.info(f"Failed to publish record")
                print(callable(getattr(metric, "__str__", None)))
                if callable(getattr(metric, "__str__", None)):
                    self._logger.info(metric)
                metric.values = []
                metric.label_values = []
            return result

        return inner

    def __getitem__(self, item):
        return self._metrics[item]


# TODO: response size profiler???

publisher: ProfilesPublisher = ProfilesPublisher()
