from __future__ import annotations

import logging
import sys
import typing
from datetime import datetime as dt

from flask import current_app as app
from imp_prof import Record
from . import log


class MetricWrapper(log.InstanceLoggerMixin):
    """Wrapper around all Prometheus metric types"""

    name: str
    item: typing.List[str]
    method: typing.List[str]
    job: str
    metric: str
    _values: typing.List[tuple[str, typing.Union[float, str, dict[str, typing.Any]]]]
    label_names: typing.List[str]
    _label_values: typing.List[typing.Dict[str, str]]
    operations: typing.Dict[str, typing.Callable]
    default_operation: str

    def __init__(
        self,
        name: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
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
        self._values = []
        self.method = []
        self.job = ""
        self.label_names = list(set(labels)) if labels else []
        self._label_values = []
        self.operations = {}
        self.default_operation = ""
        super().__init__(
            logged_name="phanos", logger=logger or logging.getLogger(__name__)
        )

    def to_records(self) -> typing.List[Record]:
        """Convert measured values into Type Record

        :returns: List of records
        :raises RuntimeError: if one of records would be incomplete
        """
        records = []
        if not (len(self.method) == len(self._values) == len(self._label_values)):
            self.error(
                f"{self.to_records.__qualname__}: one of records missing method || value || label_values"
            )
            raise RuntimeError(
                f"{len(self.method)}, {len(self._values)}, {len(self._label_values)}"
            )
        for i in range(len(self._values)):
            label_value = (
                self._label_values[i] if self._label_values is not None else {}
            )
            record: Record = {
                "item": self.method[i].split(":")[0],
                "metric": self.metric,
                "units": self.units,
                "job": self.job,
                "method": self.method[i],
                "labels": label_value,
                "value": self._values[i],
            }
            records.append(record)

        return records

    def _check_labels(self, labels: typing.List[str]) -> bool:
        """Check if labels of records == labels specified at init

        :param labels: label keys and values of one record
        """
        if sorted(labels) == sorted(self.label_names):
            return True
        return False

    def store_operation(
        self,
        method: str,
        operation: typing.Optional[str] = None,
        value: typing.Optional[
            typing.Union[
                float,
                str,
                dict[str, typing.Any],
                tuple[str, typing.Union[float, str, dict[str, typing.Any]]],
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
        :param method: measured method
        :param value: measured value
        :param label_values: values of labels
        :param args: will be passed to specific operation of given metric
        :param kwargs: will be passed to specific operation of given metric
        :raise ValueError: if operation does not exist for given metric.
        """
        try:
            with app.app_context():
                if self.job == "":
                    self.job = app.import_name
        except RuntimeError:
            pass

        if label_values is None:
            label_values = {}
        try:
            labels_ok = self._check_labels(list(label_values.keys()))
            if labels_ok:
                self._label_values.append(label_values)
            else:
                self.error(
                    f"{self.store_operation.__qualname__}: expected labels: {self.label_names}, "
                    f"labels given: {label_values.keys()}"
                )
                raise ValueError("Unknown or missing label")
            if operation is None:
                operation = self.default_operation
            self.method.append(method)
            self.debug(
                "metric %s stored operation %s, value %s", self.name, operation, value
            )
            self.operations[operation](value, args, kwargs)
        except KeyError as exc:
            self.error(
                f"{self.store_operation.__qualname__}: operation {operation} unknown."
                f"Known operations: {self.operations.keys()}"
            )
            raise ValueError("Unknown operation") from exc

    def cleanup(self) -> None:
        """Cleanup after all records was sent"""
        if self._values is not None:
            self._values.clear()
        if self._label_values is not None:
            self._label_values.clear()
        if self.method is not None:
            self.method.clear()
        if self.item is not None:
            self.item.clear()
        self.debug("%s: metric %s cleared", self.cleanup.__qualname__, self.name)


class Histogram(MetricWrapper):
    """class representing histogram metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize Histogram metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, units, labels, logger)
        self.metric = "histogram"
        self.default_operation = "observe"
        self.operations = {"observe": self._observe}

    def _observe(self, value: float, *args, **kwargs) -> None:
        """Method representing observe action of Histogram

        :param value: measured value
        :raises ValueError: if value is not float
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            self.error(f"{self._observe.__qualname__}: accepts only float values")
            raise TypeError("Value must be float")
        self._values.append(("observe", value))


class Summary(MetricWrapper):
    """class representing summary metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize Summary metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, units, labels, logger)
        self.metric = "summary"
        self.default_operation = "observe"
        self.operations = {"observe": self._observe}

    def _observe(self, value: float, *args, **kwargs) -> None:
        """Method representing observe action of Summary

        :param value: measured value
        :raises ValueError: if value is not float
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            self.error(f"{self._observe.__qualname__}: accepts only float values")
            raise TypeError("Value must be float")
        self._values.append(("observe", value))


class Counter(MetricWrapper):
    """class representing counter metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize Counter metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, units, labels, logger)
        self.metric = "counter"
        self.default_operation = "inc"
        self.operations = {"inc": self._inc}

    def _inc(self, value: float, *args, **kwargs) -> None:
        """Method representing inc action of counter

        :param value: measured value
        :raises ValueError: if value is not float >= 0
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            self.error(f"{self._inc.__qualname__}: accepts only float values >= 0")
            raise TypeError("Value must be float >= 0")
        self._values.append(("inc", value))


class Info(MetricWrapper):
    """class representing info metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize Info metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        if units is None:
            units = "info"
        super().__init__(name, units, labels, logger)
        self.metric = "info"
        self.default_operation = "info"
        self.operations = {"info": self._info}

    def _info(
        self, value: typing.Dict[typing.Any, typing.Any], *args, **kwargs
    ) -> None:
        """Method representing info action of info

        :param value: measured value
        :raises ValueError: if value is not dictionary
        """
        _ = args
        _ = kwargs
        if not isinstance(value, dict):
            self.error(f"{self._info.__qualname__}: accepts only dictionary values")
            raise ValueError("Value must be dictionary")
        self._values.append(("info", value))


class Gauge(MetricWrapper):
    """class representing gauge metric of Prometheus"""

    metric: str

    def __init__(
        self,
        name: str,
        units: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize Gauge metric and stores it into publisher instance

        Set values that are in Type Record.

        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, units, labels, logger)
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
        :raises ValueError: if value is not float >= 0
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            self.error(f"{self._inc.__qualname__}: accepts only float values >= 0")
            raise TypeError("Value must be float >= 0")
        self._values.append(("inc", value))

    def _dec(self, value: float, *args, **kwargs) -> None:
        """Method representing dec action of gauge

        :param value: measured value
        :raises ValueError: if value is not float >= 0
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float) or value < 0:
            self.error(f"{self._dec.__qualname__}: accepts only float values >= 0")
            raise TypeError("Value must be float >= 0")
        self._values.append(("dec", value))

    def _set(self, value: float, *args, **kwargs) -> None:
        """Method representing set action of gauge

        :param value: measured value
        :raises ValueError: if value is not float
        """
        _ = args
        _ = kwargs
        if not isinstance(value, float):
            self.error(f"{self._set.__qualname__}: accepts only float values")
            raise TypeError("Value must be float")
        self._values.append(("set", value))


class Enum(MetricWrapper):
    """class representing enum metric of Prometheus"""

    metric: str
    states: typing.List[str]

    def __init__(
        self,
        name: str,
        states: typing.List[str],
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
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
        super().__init__(name, units, labels, logger)
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
            self.warning(
                f"{self._state.__qualname__}: state  {value!r} not allowed for Enum {self.name!r}. "
                f"Allowed values: {self.states!r}"
            )
            raise ValueError("Invalid state for Enum metric")
        self._values.append(("state", value))


class TimeProfiler(Histogram):
    """class for measuring multiple time records in one endpoint.
     Used for measuring time consuming operations

    measured unit is milliseconds
    """

    _start_ts: typing.List[dt]

    def __init__(
        self,
        name: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        :param labels: label_names of metric viz. Type Record
        :raises RuntimeError: if start timestamps < number of stop measurement operation
        """
        super().__init__(name, "mS", labels, logger)
        self.operations = {"stop": self._stop}
        self.default_operation = "stop"
        self._start_ts = []
        self.debug("TimeProfiler metric initialized")

    # ############################### measurement operations -> checking labels, not sending records
    def _stop(self, *args, **kwargs) -> None:
        """Records time difference between last start_ts and now"""
        _ = args
        _ = kwargs
        try:
            method_time = dt.now() - self._start_ts.pop(-1)
            self._observe(
                method_time.total_seconds() * 1000.0,
            )
        except IndexError:
            self.error(
                f"{self._stop.__qualname__}: Cannot record operation. No start ts exists."
            )
            raise RuntimeError(
                "Number of start timestamps < number of stop measurement operations"
            )

    # ############################### helper operations -> not checking labels, not checking records
    def start(self, *args, **kwargs) -> None:
        """Starts time measurement - stores dt.now()"""
        _ = args
        _ = kwargs
        self._start_ts.append(dt.now())

    def cleanup(self) -> None:
        """Method responsible for cleanup after publishing records"""
        self._start_ts.clear()
        super().cleanup()


class ResponseSize(Histogram):
    """class for measuring response size from API

    measured in bytes
    """

    def __init__(
        self,
        name: str,
        labels: typing.Optional[typing.List[str]] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """
        :param labels: label_names of metric viz. Type Record
        """
        super().__init__(name, "B", labels, logger)
        self.operations = {"rec": self._rec}
        self.default_operation = "rec"
        self.debug("ResponseSize metric initialized")

    def _rec(self, value: str, *args, **kwargs) -> None:
        """records size of response"""
        _ = args
        _ = kwargs
        self._observe(float(sys.getsizeof(value)))
