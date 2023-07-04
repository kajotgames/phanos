import logging
import typing

LoggerLike = typing.Union[logging.Logger, logging.LoggerAdapter]


class InstanceLoggerMixin:
    """Adds method for instance logging"""
    __slots__ = (
        "logger",
        "logged_name",
    )
    logger: LoggerLike
    logged_name: str

    def __init__(
            self,
            *args,
            logged_name: typing.Optional[str] = None,
            logger: typing.Optional[LoggerLike] = None,
            logger_name: typing.Optional[str] = None,
            **kwargs,
    ) -> None:
        """
        Bind logger to class logger.

        :param logged_name: log messages are formatted as "{name} - {message}"
        :param logger: logger to use for logging
        :param logger_name: only if no logger object is given, get named logger from
            python logging. If none use name of class cls.__name___
        """
        self.logged_name = logged_name or type(self).__qualname__
        self.logger = logger or logging.getLogger(logger_name or self.logged_name)
        super().__init__(*args, **kwargs)

    def log(self, level: int, msg: typing.Any, *args, **kwargs) -> None:
        return self.logger.log(level, f"%s - {msg}", self.logged_name, *args, **kwargs)

    def debug(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.ERROR, msg, *args, **kwargs)

    def exception(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.CRITICAL, msg, *args, **kwargs)

    def fatal(self, msg: typing.Any, *args, **kwargs) -> None:
        return self.log(logging.FATAL, msg, *args, **kwargs)
