# PHANOS
Python client to gather data for Prometheus logging in server with multiple instances and workers.

## Sending metrics
1. Connect instance of ProfilesPublisher to RabbitMQ

        from phanos import publisher 
        'some code'
        publisher.connect(**conection_params)

2. Create metric instances
        
        'some code'
        TimeProfiler(item="time_profilerXY")
        Histogram(item="example_hist")
    You can save instances into own variables or access them via publisher['item'] EG. publisher['example_hist']

3. decorate methods of endpoints from witch you want to send metrics @publisher.send_profiling() 
and make measurements inside

        'some code'
        @publisher.send_profiling(**params)
        def post(self):
        'some code'
        publisher['example_hist'].record_op("operation name", args, kwargs)
        'some_code'
        return {"success": 1}, 201

All measurements made are after request automatically sent to RabbitMQ queue, metrics are cleaned from records and log
is printed if instance have \_\_str\_\_()  implemented other than Object.\_\_str\_\_()

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
 - time profiler: class for measuring time consuming actions. Sent as Histogram metric
 - response size profiler class profiling response size. Sent as histogram metric
    

## Creating new metric

- New metric class needs to intherit from one of basic Prometheus metrics. 
- \_\_init\_\_()
  - \_\_init\_\_() method needs to call super().\_\_init\_\_()
  - self.default_operation and self.operations needs to be set
- Implement method for each operation wanted
- If special cleanup is needed after sending records implement method cleanup() calling super().cleanup() inside
- Rewrite \_\_str\_\_() method if some logging is needed after request