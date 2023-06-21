from __future__ import annotations

import sys
import typing
from datetime import datetime as dt

from flask import current_app as app, request
from imp_prof import Record


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
        """Check if labels of records == labels specified at init

        :param labels: label keys and values of one record
        """
        if sorted(labels) == sorted(self.label_names):
            return True
        return False

    def store_operation(
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
        try:
            with app.app_context():
                if self.job == "":
                    self.job = app.import_name.split(".")[0].upper()
                self.method = request.method
        except RuntimeError:
            self.job = ""
            self.method = ""

        if label_values is None:
            label_values = {}
        try:
            labels_ok = self._check_labels(label_values.keys())
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
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Info metric and stores it into publisher instance

        Set values that are in Type Record.

        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param labels: label_names of metric viz. Type Record
        """
        if units is None:
            units = "info"
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
        states: typing.List[str],
        units: typing.Optional[str] = None,
        labels: typing.Optional[typing.List[str]] = None,
    ) -> None:
        """
        Initialize Enum metric and stores it into publisher instance

        Set values that are in Type Record

        :param item: name of metric instance viz. Type Record
        :param units: units of measurement
        :param states: states which can enum have
        :param labels: label_names of metric viz. Type Record
        """
        if units is None:
            units = "enum"
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
        self._values.append(("state", value))


class TimeProfiler(Histogram):
    """class for measuring multiple time records in one endpoint.
     Used for measuring time consuming operations

    measured unit is milliseconds
    """

    start_ts: typing.List[dt]

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
        self.operations = {"stop": self._stop}
        self.default_operation = "stop"
        self._start_ts = []

    # ############################### measurement operations -> checking labels, not sending records
    def _stop(self, *args, **kwargs) -> None:
        """Records time difference between last start_ts and now"""
        _ = args
        _ = kwargs
        method_time = dt.now() - self._start_ts.pop(-1)

        self._observe(
            method_time.total_seconds() * 1000.0,
        )

    # ############################### helper operations -> not checking labels, not checking records
    def start(self, *args, **kwargs) -> None:
        """Starts time measurement - stores dt.now()"""
        _ = args
        _ = kwargs
        self._start_ts.append(dt.now())

    def cleanup(self) -> None:
        """Method responsible for cleanup after publishing records"""
        super().cleanup()
        self._start_ts = []

    def __str__(self):
        return (
            "profiler: "
            + self.item
            + ", context: "
            + self._label_values[-1]["context"]
            + ", value: "
            + str(self._values[-1][1])
            + " ms"
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

    def _rec(self, value: str, *args, **kwargs) -> None:
        """records size of response"""
        _ = args
        _ = kwargs
        try:
            with app.app_context():
                self._observe(float(sys.getsizeof(value)))
        except RuntimeError:
            pass

    def __str__(self):
        return (
            "profiler: "
            + self.item
            + ", context: "
            + self._label_values[-1]["context"]
            + ", value: "
            + str(self._values[0][1])
            + "B"
        )
