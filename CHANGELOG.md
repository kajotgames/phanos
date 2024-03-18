# Changelog

All notable changes to [phanos](https://github.com/kajotgames/phanos) project will be documented in
this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## Unreleased

### Changed

 - `ContextTree.delete_node` method now returns `bool` if node was deleted or not



## [0.3.0] - 2024-03-13

### Added

 - `Profiler.async_config`, `Profiler.async_dict_config` to support async handlers
 - `AsyncImpProfHandler` for non-blocking messaging


### Changed
 - `Profiler` functionality for handling records and profiling moved to `SyncExtProfiler` and `AsyncExtProfiler` due
    to support of async handlers, without breaking changes
 - `MetricWrapper.label_names` are now `Set` instead of `List`
 - `StoreOperationDecorator` no longer raises `ValueError` when input of `operation` is not valid, 
now it is logged as warning and record is ignored
 - `Profiler.delete_metric` and `Profiler.delete_handler` no longer raising `KeyError`when metric/handler not exists
now it is logged as warning 

### Deprecated

- `request_size_profile` parameter in `Profiler.config()` and `Profiler.dict_config()` is deprecated and will be removed in future versions, use
`response_size_profile` instead
- `phanos_profiler` variable is deprecated and will be removed in future versions, use `profiler` instead


## [0.2.2] - 2023-08-18

### Changed

- time profiler measurements have precision of two decimal places
- records are printed in one log message instead of log per record

## [0.2.1] - 2023-08-16

### Added

- added support for Mypy analysis


## [0.2.0] - 2023-08-05

### Added

- if `error_raised_label` set and error is raised during profiling, profiling will be printed with logger
- added `error_raised_label` flag into `Profiler.config` and `Profiler.dict_config` if turned
on, each record have additional label describing if profiled function/method raised error
- asyncio profiling support
- `phanos.publisher.NamedLoggerHandler` designed to be used of configuration `profile.dict_config`


### Changed
- `PhanosProfiler` class renamed to `Profiler`
- `current_node` of `ContextTree` moved into `Contextvar` due to asyncio support
- limit `requirements` to minimum and separate development ones into `requirements-dev.txt`
- `messaging` is now defined in this project and thus separated from `imp-prof`


## [0.1.0] - 2023-08-02


### Added

- support of dictionary configuration of profiler


## [0.0.0] - 2023-06-01

### Added

- Begin of changelog.