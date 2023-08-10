""" Module with metric types corresponding with Prometheus metrics and custom Time profiling metric """
from __future__ import annotations

import datetime
import logging
import sys
import typing
from datetime import datetime as dt

from . import log
from .tree import curr_node
from .types import Record, LoggerLike


class MetricWrapper(log.InstanceLoggerMixin):
    """Wrapper around all Prometheus metric types"""

    name: str
    item: typing.List[str]
    method: typing.List[str]
    job: str
    metric: str
    values: typing.List[tuple[str, typing.Union[float, str, dict[str, typing.Any]]]]
    label_names: typing.List[str]
    label_values: typing.List[typing.Dict[str, str]]
    operations: typing.Dict[str, typing.Callable]
    default_operation: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        self.name = name
        self.item = []
        self.units = units
        self.values = []
        self.method = []
        self.job = job
        self.label_names = list(set(labels)) if labels else []
        self.label_values = []
        self.operations = {}
        self.default_operation = ""
        super().__init__(logged_name="phanos", logger=logger or logging.getLogger(__name__))

    def to_records(self) -> typing.List[Record]:
        """Convert measured values into Type Record

        :returns: List of records
        :raises RuntimeError: if one of records would be incomplete
        """
        records = []
        if not len(self.method) == len(self.values) == len(self.label_values):
            self.error(f"{self.to_records.__qualname__}: one of records missing method || value || label_values")
            raise RuntimeError(f"{len(self.method)}, {len(self.values)}, {len(self.label_values)}")
        for i in range(len(self.values)):
            label_value = self.label_values[i] if self.label_values is not None else {}
            record: Record = {
                "item": self.method[i].split(":")[0],
                "metric": self.metric,
                "units": self.units,
                "job": self.job,
                "method": self.method[i],
                "labels": label_value,
                "value": self.values[i],
            }
            records.append(record)

        return records

    def check_labels(self, labels: typing.List[str]) -> bool:
        """Check if labels of records == labels specified at initialization

        :param labels: label keys and values of one record
        """
        if sorted(labels) == sorted(self.label_names):
            return True
        return False

    def cleanup(self) -> None:
        """Cleanup after all records was sent

        Clears metrics `self.values`, `self.label_values`, `self.method` and `self.item`
        `self.job` and `self.units` are same during whole existence of metric instance
        """
        if self.values is not None:
            self.values.clear()
        if self.label_values is not None:
            self.label_values.clear()
        if self.method is not None:
            self.method.clear()
        if self.item is not None:
            self.item.clear()
        self.debug("%s: metric %s cleared", self.cleanup.__qualname__, self.name)


ValueTypes = typing.Union[
    float,
    str,
    dict[str, typing.Any],
    tuple[str, typing.Union[float, str, dict[str, typing.Any]]],
]
OperationCallable = typing.Callable[["MetricWrapper", ValueTypes, typing.Optional[typing.Dict[str, str]]], None]


class StoreOperationDecorator:
    """Decorator class used for all of Prometheus metrics measurement methods.

    This decorator handles checking of all values that will be inserted into Record and
    calls one of metrics operation method f.e. `Counter.inc`
    """

    def __init__(self, operation: OperationCallable):
        """
        :param operation: measurement method of one of basic Prometheus metrics
        """
        self.operation = operation

    def __get__(
        self, instance: MetricWrapper, owner: type[MetricWrapper]
    ) -> typing.Callable[[ValueTypes, typing.Optional[typing.Dict[str, str]]], None]:
        """

        :param instance: instance of basic Prometheus metric
        :param owner: class of basic Prometheus metric
        :return: wrapper
        """
        return lambda value, label_values=None: self.wrapper(instance, value, label_values)

    def wrapper(
        self,
        instance: MetricWrapper,
        value: ValueTypes,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """
        wrapper check if given labels are same as labels given at initialization of metric,
        saves label_values, current method, and given operation with value. If any error occurs,
        record is not saved.

        :param instance:instance of basic Prometheus metric
        :param value: measured value to be inserted
        :param label_values: values of labels in format {'label_name': 'label_value'}
        :raise ValueError: if any of label names are not known or missing, or if `self.operation`method did not
        store any value.

        """
        if label_values is None:
            label_values = {}
        if "error_raised" in instance.label_names:
            label_values["error_raised"] = sys.exc_info()[0] is not None
        labels_ok = instance.check_labels(list(label_values.keys()))
        if not labels_ok:
            instance.error(
                f"{self.operation.__qualname__}: expected labels: {instance.label_names}, "
                f"labels given: {label_values.keys()}"
            )
            raise ValueError("Unknown or missing label")
        instance.label_values.append(label_values)
        try:
            instance.method.append(curr_node.get().ctx.value)
        except LookupError:
            instance.error(f"{self.operation.__qualname__}: cannot get context from current node")
            instance.method.append("Missing:method")

        self.operation(instance, value, label_values)

        if not len(instance.method) == len(instance.values):
            instance.method.pop(-1)
            instance.label_values.pop(-1)
            raise ValueError("No operation stored")

        if instance.values:
            instance.debug("%r stored value %s", instance.name, instance.values[-1])


class Histogram(MetricWrapper):
    """class representing histogram metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Histogram metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, units, labels, logger)
        self.metric = "histogram"

    @StoreOperationDecorator
    def observe(
        self,
        value: float,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing observe action of Histogram

        :param value: measured value
        :param label_values: dictionary of labels and its values
        :raises ValueError: if value is not float
        """
        _ = label_values
        if not isinstance(value, float):
            self.error(f"{self.observe.__qualname__}: accepts only float values")
            raise TypeError("Value must be float")
        self.values.append(("observe", value))


class Summary(MetricWrapper):
    """class representing summary metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Summary metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, units, labels, logger)
        self.metric = "summary"

    @StoreOperationDecorator
    def observe(
        self,
        value: float,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing observe action of Summary

        :param value: measured value
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value is not float
        """
        _ = label_values
        if not isinstance(value, float):
            self.error(f"{self.observe.__qualname__}: accepts only float values")
            raise TypeError("Value must be float")
        self.values.append(("observe", value))


class Counter(MetricWrapper):
    """class representing counter metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Counter metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, units, labels, logger)
        self.metric = "counter"

    @StoreOperationDecorator
    def inc(
        self,
        value: float,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing inc action of counter

        :param value: measured value
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value is not float >= 0
        """

        _ = label_values
        if not isinstance(value, float) or value < 0:
            self.error(f"{self.inc.__qualname__}: accepts only float values >= 0")
            raise TypeError("Value must be float >= 0")
        self.values.append(("inc", value))


class Info(MetricWrapper):
    """class representing info metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Info metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement

        :param labels: label_names of metric viz. Type Record
        """
        if units is None:
            units = "info"
        super().__init__(name, job, units, labels, logger)
        self.metric = "info"

    @StoreOperationDecorator
    def info_(
        self,
        value: typing.Dict[typing.Any, typing.Any],
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing info action of info

        :param value: measured value
                :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value is not dictionary
        """
        _ = label_values
        if not isinstance(value, dict):
            self.error(f"{self.info_.__qualname__}: accepts only dictionary values")
            raise ValueError("Value must be dictionary")
        self.values.append(("info", value))


class Gauge(MetricWrapper):
    """class representing gauge metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Gauge metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, units, labels, logger)
        self.metric = "gauge"

    @StoreOperationDecorator
    def inc(
        self,
        value: float,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing inc action of gauge

        :param value: measured value
                :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value is not float >= 0
        """
        _ = label_values
        if not isinstance(value, float) or value < 0:
            self.error(f"{self.inc.__qualname__}: accepts only float values >= 0")
            raise TypeError("Value must be float >= 0")
        self.values.append(("inc", value))

    @StoreOperationDecorator
    def dec(
        self,
        value: float,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing dec action of gauge

        :param value: measured value
                :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value is not float >= 0
        """
        _ = label_values
        if not isinstance(value, float) or value < 0:
            self.error(f"{self.dec.__qualname__}: accepts only float values >= 0")
            raise TypeError("Value must be float >= 0")
        self.values.append(("dec", value))

    @StoreOperationDecorator
    def set(
        self,
        value: float,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing set action of gauge

        :param value: measured value
                :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value is not float
        """
        _ = label_values
        if not isinstance(value, float):
            self.error(f"{self.set.__qualname__}: accepts only float values")
            raise TypeError("Value must be float")
        self.values.append(("set", value))


class Enum(MetricWrapper):
    """class representing enum metric of Prometheus"""

    metric: str
    states: typing.List[str]

    def __init__(
        self,
        name: str,
        job: str,
        states: typing.List[str],
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Enum metric and stores it into publisher instance

        Set values that are in Type Record

        :param units: units of measurement
        :param states: states which can enum have
        :param labels: label_names of metric viz. Type Record
        """
        if units is None:
            units = "enum"
        super().__init__(name, job, units, labels, logger)
        self.metric = "enum"
        self.states = states

    @StoreOperationDecorator
    def state(
        self,
        value: str,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing state action of enum

        :param value: measured value
                :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises ValueError: if value not in states at initialization
        """
        _ = label_values
        if value not in self.states:
            self.warning(
                f"{self.state.__qualname__}: state  {value!r} not allowed for Enum {self.name!r}. "
                f"Allowed values: {self.states!r}"
            )
            raise ValueError("Invalid state for Enum metric")
        self.values.append(("state", value))


class TimeProfiler(Histogram):
    """Class for measuring multiple time records in one endpoint.
    Used for measuring time-consuming operations

    measured unit is milliseconds
    """

    def __init__(
        self,
        name: str,
        job: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        :param labels: label_names of metric viz. Type Record
        :raises RuntimeError: if start timestamps < number of stop measurement operation
        """
        super().__init__(name, job, "mS", labels, logger)
        self.operations = {"stop": self.stop}
        self.default_operation = "stop"
        self.debug("TimeProfiler metric initialized")

    # ############################### measurement operations -> checking labels, not sending records
    def stop(self, start: datetime.datetime, label_values: typing.Dict[str, str]) -> None:
        """Records time difference between last start_ts and now"""
        method_time = dt.now() - start
        self.observe(
            method_time.total_seconds() * 1000.0,
            label_values,
        )


class ResponseSize(Histogram):
    """class for measuring response size from API

    measured in bytes
    """

    def __init__(
        self,
        name: str,
        job: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, "B", labels, logger)
        self.operations = {"rec": self.rec}
        self.default_operation = "rec"
        self.debug("ResponseSize metric initialized")

    def rec(self, value: str, label_values: typing.Dict[str, str]) -> None:
        """records size of response"""
        self.observe(float(sys.getsizeof(value)), label_values)
