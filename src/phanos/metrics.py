""" Module with metric types corresponding with Prometheus metrics and custom Time profiling metric """
from __future__ import annotations

import datetime
import logging
import sys
import typing
from datetime import datetime as dt

from . import log
from .tree import MethodTreeNode
from .types import Record, LoggerLike


class InvalidValueError(Exception):
    """Raised when invalid value is given to metric"""

    pass


class MetricWrapper(log.InstanceLoggerMixin):
    """Wrapper around all Prometheus metric types"""

    name: str
    method: typing.List[str]
    job: str
    metric: str
    values: typing.List[tuple[str, typing.Union[float, str, dict[str, typing.Any]]]]
    label_names: typing.Set[str]
    label_values: typing.List[typing.Dict[str, str]]
    operations: typing.Dict[str, typing.Callable]
    default_operation: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.Set[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        Initialize Metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        self.name = name
        self.units = units
        self.values = []
        self.method = []
        self.job = job
        self.label_names = labels if labels else set()
        self.label_values = []
        self.operations = {}
        self.default_operation = ""
        super().__init__(logged_name="phanos", logger=logger or logging.getLogger(__name__))

    def to_records(self) -> typing.Optional[typing.List[Record]]:
        """Convert measured values into Type Record

        :returns: List of records or None if any of records is incomplete
        """
        records = []
        if not len(self.method) == len(self.values) == len(self.label_values):
            self.error(
                f"{self.to_records.__qualname__!r}: Metric {self.name!r} "
                f"- one of records is incomplete ... skipping publishing"
            )
            return None
        for i in range(len(self.values)):
            record: Record = {
                "item": self.method[i].split(":")[0],
                "metric": self.metric,
                "units": self.units,
                "job": self.job,
                "method": self.method[i],
                "labels": self.label_values[i],
                "value": self.values[i],
            }
            records.append(record)

        return records

    def eq_labels(self, labels: typing.Set[str]) -> bool:
        """Check if labels of records == labels specified at initialization

        :param labels: label keys and values of one record
        """
        return labels == self.label_names

    def cleanup(self) -> None:
        """Cleanup after all records was sent

        Clears metrics `self.values`, `self.label_values`, `self.method`
        `self.job` and `self.units` are same during whole existence of metric instance
        """
        self.values.clear()
        self.label_values.clear()
        self.method.clear()
        self.debug("%s: metric %s cleared", self.cleanup.__qualname__, self.name)


ValueTypes = typing.Union[
    float,
    str,
    dict[str, typing.Any],
    tuple[str, typing.Union[float, str, dict[str, typing.Any]]],
]

OperationCallable = typing.Callable[
    ["MetricWrapper", ValueTypes, MethodTreeNode, typing.Optional[typing.Dict[str, str]]], None
]


class StoreOperationDecorator:
    """Decorator class used for all of Prometheus metrics measurement methods.

    This decorator handles checking of all values that will be inserted into Record and
    calls one of metrics operation method f.e. `Counter.inc`
    """

    operation: OperationCallable

    def __init__(self, operation: OperationCallable):
        """
        :param operation: measurement method of one of basic Prometheus metrics
        """
        self.operation = operation

    def __get__(
        self, instance: MetricWrapper, owner: type[MetricWrapper]
    ) -> typing.Callable[[ValueTypes, MethodTreeNode, typing.Optional[typing.Dict[str, str]]], None]:
        """

        :param instance: instance of basic Prometheus metric
        :param owner: class of basic Prometheus metric
        :return: wrapper
        """
        return lambda value, current_node, label_values=None: self.wrapper(instance, value, current_node, label_values)

    def wrapper(
        self,
        instance: MetricWrapper,
        value: ValueTypes,
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """
        wrapper check if given labels are same as labels given at initialization of metric,
        saves label_values, current method, and given operation with value. If any error occurs,
        record is not saved.

        :param current_node: current node from ContextVar
        :param instance:instance of basic Prometheus metric
        :param value: measured value to be inserted
        :param label_values: values of labels in format {'label_name': 'label_value'}
        """
        if label_values is None:
            label_values = {}
        if "error_raised" in instance.label_names:
            label_values["error_raised"] = sys.exc_info()[0] is not None
        labels_ok = instance.eq_labels(set(label_values.keys()))
        if not labels_ok:
            instance.error(
                f"{self.operation.__qualname__!r}: metric {instance.name!r} expected labels: {instance.label_names}, "
                f"labels given: {set(label_values.keys())}"
            )
            return
        instance.label_values.append(label_values)

        instance.method.append(current_node.ctx.value)

        try:
            self.operation(instance, value, current_node, label_values)
        except InvalidValueError as e:
            instance.error(f"{self.operation.__qualname__!r}: metric {instance.name!r} accepts only values {e}")
            _ = instance.method.pop(-1)
            _ = instance.label_values.pop(-1)
            return

        if not len(instance.method) == len(instance.values):
            instance.warning(f"{self.operation.__qualname__!r}: metric {instance.name!r} did not store any value")
            _ = instance.method.pop(-1)
            _ = instance.label_values.pop(-1)
            return

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
        labels: typing.Optional[typing.Set[str]] = None,
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
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing observe action of Histogram

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of labels and its values
        :raises InvalidValueError: if value is not float
        """
        _ = label_values
        _ = current_node
        if not isinstance(value, float):
            raise InvalidValueError("Float")
        self.values.append(("observe", value))


class Summary(MetricWrapper):
    """class representing summary metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.Set[str]] = None,
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
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing observe action of Summary

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value is not float
        """
        _ = label_values
        _ = current_node
        if not isinstance(value, float):
            raise InvalidValueError("Float")
        self.values.append(("observe", value))


class Counter(MetricWrapper):
    """class representing counter metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.Set[str]] = None,
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
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing inc action of counter

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value is not float >= 0
        """

        _ = label_values
        _ = current_node
        if not isinstance(value, float) or value < 0:
            raise InvalidValueError("Float >= 0")
        self.values.append(("inc", value))


class Info(MetricWrapper):
    """class representing info metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.Set[str]] = None,
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
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing info action of info

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value is not dictionary
        """
        _ = label_values
        _ = current_node
        if not isinstance(value, dict):
            raise InvalidValueError("Dict")
        self.values.append(("info", value))


class Gauge(MetricWrapper):
    """class representing gauge metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        job: str,
        units: str,
        labels: typing.Optional[typing.Set[str]] = None,
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
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing inc action of gauge

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value is not float >= 0
        """
        _ = label_values
        _ = current_node
        if not isinstance(value, float) or value < 0:
            raise InvalidValueError("Float >= 0")
        self.values.append(("inc", value))

    @StoreOperationDecorator
    def dec(
        self,
        value: float,
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing dec action of gauge

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value is not float >= 0
        """
        _ = label_values
        _ = current_node
        if not isinstance(value, float) or value < 0:
            raise InvalidValueError("Float >= 0")
        self.values.append(("dec", value))

    @StoreOperationDecorator
    def set(
        self,
        value: float,
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing set action of gauge

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value is not float
        """
        _ = label_values
        _ = current_node
        if not isinstance(value, float):
            raise InvalidValueError("Float")
        self.values.append(("set", value))


class Enum(MetricWrapper):
    """class representing enum metric of Prometheus"""

    metric: str
    states: typing.Set[str]

    def __init__(
        self,
        name: str,
        job: str,
        states: typing.Set[str],
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.Set[str]] = None,
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
        current_node: MethodTreeNode,
        label_values: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        """Method representing state action of enum

        :param value: measured value
        :param current_node: current node from ContextVar
        :param label_values: dictionary of key:value = 'label_name':'label_value'
        :raises InvalidValueError: if value not in states at initialization
        """
        _ = label_values
        _ = current_node
        if value not in self.states:
            raise InvalidValueError(f"in {self.states}")
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
        labels: typing.Optional[typing.Set[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, "mS", labels, logger)
        self.debug("TimeProfiler metric initialized")

    # ############################### measurement operations -> checking labels, not sending records
    def stop(self, start: datetime.datetime, current_node: MethodTreeNode, label_values: typing.Dict[str, str]) -> None:
        """Records time difference between last start_ts and now"""
        method_time = dt.now() - start
        self.observe(
            round(method_time.total_seconds() * 1000.0, 2),
            current_node,
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
        labels: typing.Optional[typing.Set[str]] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, job, "B", labels, logger)
        self.debug("ResponseSize metric initialized")

    def rec(self, value: str, current_node: MethodTreeNode, label_values: typing.Dict[str, str]) -> None:
        """records size of response"""
        self.observe(float(sys.getsizeof(value)), current_node, label_values)
