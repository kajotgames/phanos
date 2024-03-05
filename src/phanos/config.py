import copy
import importlib
import typing

import phanos.publisher

"""
example_config = {
    "job": "my_app", 
    "logger": "my_app_debug_logger", 
    "time_profile": True, 
    "request_size_profile": False,
    "handle_records": True, 
     "error_raised_label": True,
    "handlers": {
        "stdout_handler_ref": {
                "class": "phanos.publisher.StreamHandler", 
                "handler_name": "stdout_handler", 
                "output": "ext://sys.stdout"
            }
        }
}
"""

EXTERNAL_PREFIX = "ext://"


def import_external(full_name: str) -> typing.Any:
    """
    Import dynamically any module or submodule f.e.:`"sys.stdout"` returns `stdout`

    :param full_name: string path to module or submodule or its member
    :return: object described in full_name
    """
    parts = full_name.split(".")
    module = importlib.import_module(parts[0])

    for part in parts[1:]:
        module = getattr(module, part)

    return module


TC = typing.TypeVar("TC", phanos.publisher.AsyncBaseHandler, phanos.publisher.SyncBaseHandler)


def _to_callable(elem: typing.Union[str, TC]) -> TC:
    if isinstance(elem, str):
        return import_external(elem)
    return elem


def parse_arguments(arguments: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """
    This is simple kwargs parse.
    In future add this method to class, so we can do self referencing of config by names.

    :param arguments:
    :return: dict of parsed arguments
    """
    parsed = {}
    for name, arg in arguments.items():
        if isinstance(arg, str) and arg.startswith(EXTERNAL_PREFIX):
            parsed[name] = import_external(arg.lstrip(EXTERNAL_PREFIX))
        else:
            parsed[name] = arg
    return parsed


# TODO: refactor create_handlers and create_async_handlers
def create_handlers(configs: dict) -> typing.Dict[str, phanos.publisher.SyncBaseHandler]:
    """
    Factory to create handlers based on dict config.

    :param configs: serialized handler config;
        Example:
            ```
            conf = {
                "stdout_handler": {
                    "class": "phanos.publisher.StreamHandler",
                    "handler_name": "stdout_handler",
                    "output": "ext://sys.stdout",
                }
            }
            ```
    :return: `{"stdout_handler": <StreamHandler instance>}`
    """
    new_handlers = {}
    for ref_name, config in configs.items():
        original_kw_args = copy.deepcopy(config)
        cls_handler: typing.Type[TC] = _to_callable(original_kw_args.pop("class"))
        if issubclass(cls_handler, phanos.publisher.AsyncBaseHandler):
            raise phanos.publisher.UnsupportedHandler("Use create_async_handlers for async handlers")
        kw_args = parse_arguments(original_kw_args)
        new_handlers[ref_name] = cls_handler(**kw_args)
    return new_handlers


async def create_async_handlers(
    configs: dict,
) -> typing.Dict[str, typing.Union[phanos.publisher.AsyncBaseHandler, phanos.publisher.SyncBaseHandler]]:
    new_handlers = {}
    for ref_name, config in configs.items():
        original_kw_args = copy.deepcopy(config)
        cls_handler: typing.Type[TC] = _to_callable(original_kw_args.pop("class"))
        kw_args = parse_arguments(original_kw_args)
        if issubclass(cls_handler, phanos.publisher.AsyncBaseHandler):
            new_handlers[ref_name] = await cls_handler.create(**kw_args)
        else:
            new_handlers[ref_name] = cls_handler(**kw_args)

    return new_handlers
