# PHANOS
Python client to gather data for Prometheus logging in server with multiple instances and workers.

## Profiling

### Default metrics

Phanos contains two default metrics. Time profiler measuring execution time of
decorated methods and response size profiler measuring response size of decorated method
of endpoint. Both can be deleted by `phanos_profiler.delete_metric(phanos.publisher.TIME_PROFILER)`
and `phanos_profiler.delete_metric(phanos.publisher.RESPONSE_SIZE)` if not deleted, measurements are
made automatically.

### Usage

1. decorate methods from which you want to send metrics `@phanos_profiler.profile`
   ```python
   from phanos import phanos_profiler
   # some code
   @phanos_profiler.profile
   def some_method():
      # some code
   ```

2. Instantiate handlers you need for measured records at app construction.
   ```python      
   from phanos import phanos_profiler
   from phanos.publisher import LoggerHandler, ImpProfHandler
   # some code
   class SomeApp(Flask):
      """some code""" 
   phanos_profiler.config(logger, should_time_profile, should_resp_size_profile, should_handle_records)
   log_handler = LoggerHandler('logger_name', logger_instance, logging_level)
   phanos_profiler.addHandler(log_handler)    
      # some code
   ```
In `config` method you can select if you want to turn off  time profiling, response size profiling
 or records handling. Default is turned on.
After root method is executed all measured records are handled by all handlers added to
`phanos_profiler`

## Handlers

Each handler have handler_name parameter. This string can be used to delete handlers later
with `phanos_profiler.deleteHandler(handler_name)`.

Records can be handled by these handlers:
 - `StreamHandler(handler_name, output)` - write records to given output (default is sys.stdout)
 - `LoggerHandler(handler_name, logger, level)` - logs string representation of records with given logger and with given level
(default level is `logging.DEBUG`) 
 - `ImpProfHandler(handler_name, **rabbit_connection_params, logger)` - sending records to RabbitMQ queue of IMP_prof

## Phanos metrics:

### Basic Prometheus metrics:

 - Histogram
 - Summary
 - Counter
 - Info
 - Gauge
 - Enum

These classes represent Prometheus metrics without any modification.


### Custom metrics

 - time profiler: class for measuring time-consuming actions. Sent as Histogram metric
 - response size profiler class profiling response size. Sent as histogram metric
    

### Creating new custom metric

- New metric class needs to inherit from one of basic Prometheus metrics. 
- `__init__()`
  - `__init__()` method needs to call `super().__init__()`
  - `self.default_operation` and `self.operations` needs to be set
- Implement method for each operation wanted
- If special cleanup is needed after sending records implement method `cleanup()` calling `super().cleanup()` inside

### Add metrics automatic measurements

'phanos_profiler' contains these four arguments:
 
- before_func : callable - executes before each profiled method
- after_func : callable - executes after each profiled method
- before_root_func : callable - executes before each profiled root method (first method in profiling tree)
- after_root_func : callable - executes after each profiled root method (first method in profiling tree)

Implement these methods with all your measurement. Example:
   ```python
   def before_function(function):
      # this operation will be recorded
      my_metric.store_operation(
          operation="my_operation",
          method=phanos_profiler.current_node.context,
          value=measured_value,
          label_values={"label_name": "label_value"},
      )
      # this won't be recorded
      my_metric.my_method()
      next_metric....
   # some code 
   phanos_profiler.before_func = before_function
   ```

`phanos_profiler` will record operation `"my_operation"` with value `measured_value` and given labels before
each method decorated with `phanos_profiler.profile`.

What must/can be done
- 'before_' functions must have 'function' parameter where function which is executed is passed.
'after_' function needs to have 'fn_result' parameter where function result is passed
- all four functions can access `*args` and `**kwargs` of decorated methods.
- Each 'store_operation' must have parameter `method=phanos_profiler.current_node.context` so 
method context is correctly saved. 
- current_node.context stores context of method calling in format: 
`"root_class.__name__:root_method.__name__.currently_executed.__name__"` if root is function then instead of 
class name its module name.

