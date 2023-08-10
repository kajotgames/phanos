import logging
import typing

LoggerLike = typing.Union[logging.Logger, logging.LoggerAdapter]


class Record(typing.TypedDict):
    """One profiling log record."""

    item: str  # name of object measured
    metric: str  # metric used to measure item
    units: str  # units of metric used to measure item
    value: typing.Union[tuple[str, typing.Union[float, str, dict[str, typing.Any]]]]  # value to record in
    # metric, in given units
    job: str  # label marking who created the record
    method: str  # which method of item is measured
    labels: typing.Optional[typing.Dict[str, str]]  # labels with values to categorise record correctly
