import logging
import typing

LoggerLike = typing.Union[logging.Logger, logging.LoggerAdapter]


class Record(typing.TypedDict):
    """
    class to hold one metric measurement

    Attributes:

    - **item** --> the name of object measured
    - **metric** --> metric used to measure item
    - **units** --> units of metric used to measure item
    - **value** --> {'metric operation': 'measured value'}
    - **job** --> label marking who created the record
    - **method** --> which method of item is measured
    - **labels** --> labels with values to categorise record correctly
    """

    item: str
    metric: str
    units: str
    value: typing.Union[tuple[str, typing.Union[float, str, dict[str, typing.Any]]]]
    job: str
    method: str
    labels: typing.Optional[typing.Dict[str, str]]
