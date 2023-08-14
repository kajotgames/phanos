# PHANOS

Python client to gather data for Prometheus logging in server with multiple instances and workers.
Phanos works with synchronous programs and with asynchronous programs implemented by asyncio.
Behavior in multithread programs is unspecified.

## Profiling

### Default metrics

Phanos contains two default metrics. Time profiler measuring execution time of
decorated methods is ON by default. Response size profiler measuring size of methods return value
of root method is OFF by default. Both can be deleted by `phanos.profiler.delete_metric(phanos.publisher.TIME_PROFILER)`
and `phanos.profiler.delete_metric(phanos.publisher.RESPONSE_SIZE)`.

### Configuration

There are options of how to configure profiler. Profiler must be configured by one of these options.

Both options uses these attributes:

- `job` job _label_ for prometheus; usually name of app
- `logger` _(optional)_ name of logger; if not specified, Phanos creates its own logger
- `time_profile` _(optional)_ by default _profiler_ tracks execution time of profiled function/object
- `response_size_profile` _(optional)_ by default _profiler_ will not track size of return value
- `handle_records` _(optional)_ by default _profiler_ measures values and handles them; 
if False then no profiling is made or handled
- `error_raised_label` _(optional)_ by default profiler will not add label `error_raised` to each
record; if set, every record will have information if given profiled function/method raised error; if error raised,
profiling will be logged even if no `LoggerHandler` exists

- `handlers` _(optional)_ serialized named handlers to publish profiled records; 
if no handlers specified then no measurements are made; for handlers description refer to [Handlers](#handlers).
  - `class` class handler to initialized
  - `handler_name` handler name required argument of publishers
  - `**other arguments` - specific arguments required to construct instance of class f.e.: `output`.

#### Dict Configuration
It is possible to configure profile with configration dictionary with method `Profiler.dict_config(settings)` 
_(similar to `logging` `dictConfig`)_.

Example of configuration dict:

```python
settings = {
    "job": "my_app", 
    "logger": "my_app_debug_logger", 
    "time_profile": True, 
    "request_size_profile": False,
    "handle_records": True, 
    "error_raised_label": False,
    "handlers": {
        "stdout_handler_ref": {
                "class": "phanos.handlers.StreamHandler", 
                "handler_name": "stdout_handler", 
                "output": "ext://sys.stdout"
            }
        }
}
```

#### Configuration in code
    
When configuring in code use `Profiler.config` method  to configure profiling.
For handler addition create handler instance first and add it to profiler with `Profiler.add_handler` method.

Example of configuration:

```python      
    import phanos
    # some code
    class SomeApp(Flask):
        """some code""" 
        phanos.profiler.config(logger, time_profile, resp_size_profile, handle_records, error_raised_label)
        log_handler = phanos.handlers.LoggerHandler('handler_name', logger_instance, logging_level)
        phanos.profiler.add_handler(log_handler)    
        # some code
```

### Usage

- configure profiler as shown in [Configuration](#configuration)

- decorate methods which you want to profile `@phanos.profile` shortcut for `@phanos.profiler.profile`.
Allways put decorator closest to method definition as possible, because the decorator collides with some other
decorators. The decorator must allways be under `@classmethod`, `@staticmethod`, `flask_restx` 
decorators and possibly others. 

```python
import phanos
   
class SomeClass:
    """ Example of @profile decorator placement"""
    @staticmethod
    @phanos.profile
    def some_method():
        pass
    
    # is equivalent to
    @staticmethod
    @phanos.profiler.profile
    def some_method():
        pass
```

## Handlers

Each handler have `handler_name` argument. This string can be used to delete handlers later
with `phanos.profiler.delete_handler(handler_name)`.

Records can be handled by these handlers:
 - `StreamHandler(handler_name, output)` - write records to given output (default is `sys.stdout`)
 - `LoggerHandler(handler_name, logger, level)` - logs string representation of records with given logger and with given
level; default level is `logging.DEBUG`; if no logger is passed, Phanos creates its own logger
 - `NamedLoggerHandler(handler_name, logger_name, level)` - same as LoggerHandler, but `logger` instance is found by 
`logging.getLogger(logger_name)` method.
 - `ImpProfHandler(handler_name, **rabbit_connection_params, logger)` - sending records to RabbitMQ queue.

## Phanos metrics:

### Basic Prometheus metrics:

 - Histogram
 - Summary
 - Counter
 - Info
 - Gauge
 - Enum

These classes represent basic Prometheus metrics types. For more information about Prometheus metric types, mainly
allowed operations, refer to [Prometheus documentation](https://prometheus.io/docs/concepts/metric_types/).


### Custom metrics

 - `time profiler`: metric for measuring time-consuming actions in mS; basically Histogram metric of Prometheus.
 - `response size profiler`: metric for measuring return value of method in bytes, designed to measure response 
size of endpoints; basically Histogram metric of Prometheus.

    

### Creating new custom metric

- new metric class needs to inherit from one of basic Prometheus metrics.
- `__init__()` method needs to call `super().__init__()`
- implement method for each operation wanted; this method must call one of inherited metrics operations if you want
operation to be saved f.e. `Gauge.dec`;
- `MetricWrapper.cleanup()` is called after all measured metrics are handled; if custom cleanup is needed, 
implement method `cleanup()` calling `super().cleanup()` inside

### Add metrics automatic measurements

`phanos.profiler` contains these four arguments:
 
- before_func : callable - executes before each profiled method/function
- after_func : callable - executes after each profiled method/function
- before_root_func : callable - executes before each profiled root method/function (first method in profiling tree)
- after_root_func : callable - executes after each profiled root method/function (first method in profiling tree)

Implement these methods with all needed measurement.

### Complete example

```python
import typing
import phanos.tree
import phanos


# custom metric example
class CustomMetric(phanos.metrics.Counter):
  def __init__(self, name, job, units, labels):
    super().__init__(name, job, units, labels)
    # custom initialization
    self.count = 0

  def custom_op(self, value: int = 0, label_values: typing.Optional[typing.Dict[str,str]] = None):
    self.count += value
    self.inc(self.count, label_values)

  def helper_method(self):
    pass

  def cleanup(self) -> None:
    super().cleanup()
    self.count = 0


my_metric = CustomMetric(name="name", job="MyJob", units="units", labels=["label_name"])


def before_function(func, args, kwargs):
  # this operation will be recorded
  my_metric.custom_op(2,{"label_name": "label_value"})
  # this won't be recorded
  my_metric.helper_method()


phanos.profiler.before_func = before_function
```

What must/can be done:
- custom metric
  -  `MetricWrapper.__init__` needs `name`, `job`, `units` arguments passed; 
`labels` and `logger` are optional
- custom measurements
  - `before_*` functions must have `func` argument, where function which is executed is passed.
`after_*` function needs to have `fn_result` argument where function result is passed
  - all four functions can access `args` and `kwargs` of decorated methods. These arguments are passed
in packed form.

