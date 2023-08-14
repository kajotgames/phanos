# Changelog

All notable changes to [phanos](https://github.com/kajotgames/phanos) project will be documented in
this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- if `error_raised_label` set and error raised, profiling will be printed with logger
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