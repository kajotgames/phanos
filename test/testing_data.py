profiling_out = [
    {
        "method": "DummyResource:get.first_access",
        "value": 2.0,
    },
    {
        "method": "DummyResource:get.second_access.first_access",
        "value": 2.0,
    },
    {
        "method": "DummyResource:get.second_access",
        "value": 5.0,
    },
    {
        "method": "DummyResource:get",
        "value": 7.0,
    },
    {
        "method": "DummyResource:get",
        "value": 56.0,
    },
]

test_handler_in = (
    {
        "item": "DummyResource",
        "metric": "histogram",
        "units": "mS",
        "job": "TEST",
        "method": "DummyResource:get.first_access",
        "labels": {"test": "value"},
        "value": ("observe", 2.0),
    },
)
test_handler_in_no_lbl = (
    {
        "item": "DummyResource",
        "metric": "histogram",
        "units": "mS",
        "job": "TEST",
        "method": "DummyResource:get.first_access",
        "labels": {},
        "value": ("observe", 2.0),
    },
)
test_handler_out = "profiler: test_name, method: DummyResource:get.first_access, value: 2.0 mS, labels: test=value\n"
test_handler_out_no_lbl = "profiler: test_name, method: DummyResource:get.first_access, value: 2.0 mS\n"

hist_no_lbl = [
    {
        "item": "Missing",
        "metric": "histogram",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("observe", 2.0),
    }
]

hist_w_lbl = [
    {
        "item": "Missing",
        "metric": "histogram",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {"test": "test"},
        "value": ("observe", 2.0),
    }
]

sum_no_lbl = [
    {
        "item": "Missing",
        "metric": "summary",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("observe", 2.0),
    }
]

cnt_no_lbl = [
    {
        "item": "Missing",
        "metric": "counter",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("inc", 2.0),
    }
]

inf_no_lbl = [
    {
        "item": "Missing",
        "metric": "info",
        "units": "info",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("info", {"value": "asd"}),
    }
]

gauge_no_lbl = [
    {
        "item": "Missing",
        "metric": "gauge",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("inc", 2.0),
    },
    {
        "item": "Missing",
        "metric": "gauge",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("dec", 2.0),
    },
    {
        "item": "Missing",
        "metric": "gauge",
        "units": "V",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("set", 2.0),
    },
]

enum_no_lbl = [
    {
        "item": "Missing",
        "metric": "enum",
        "units": "enum",
        "job": "TEST",
        "method": "Missing:method",
        "labels": {},
        "value": ("state", "true"),
    }
]


custom_profile_out = [
    {
        "method": "DummyDbAccess:second_access",
        "value": 1.0,
        "place": "before_root",
    },
    {
        "method": "DummyDbAccess:second_access",
        "value": 2.0,
        "place": "before_func",
    },
    {
        "method": "DummyDbAccess:second_access.first_access",
        "value": 2.0,
        "place": "before_func",
    },
    {
        "method": "DummyDbAccess:second_access.first_access",
        "value": 3.0,
        "place": "after_func",
    },
    {
        "method": "DummyDbAccess:second_access",
        "value": 3.0,
        "place": "after_func",
    },
    {
        "method": "DummyDbAccess:second_access",
        "value": 4.0,
        "place": "after_root",
    },
]

test_await_out_methods = [
    "AsyncTest:await_test",
    "AsyncTest:await_test",
    "AsyncTest:await_test.async_access_long",
    "AsyncTest:await_test.async_access_long",
    "AsyncTest:await_test.async_access_short",
    "AsyncTest:await_test.async_access_short",
]
test_await_out_values = [2.0, 2.0, 3.0, 3.0, 5.0, 5.0]

test_task_out_methods = [
    "AsyncTest:async_access_short",
    "AsyncTest:task_test",
    "AsyncTest:task_test.async_access_long",
    "AsyncTest:task_test.task_nested",
    "AsyncTest:task_test.task_nested.async_access_short",
]
test_task_out_values = [2.0, 3.0, 3.0, 3.0, 3.0]

test_mix_out_methods = [
    "AsyncTest:test_mix",
    "AsyncTest:test_mix.task_test",
    "AsyncTest:test_mix.task_test",
    "AsyncTest:test_mix.task_test.async_access_long",
    "AsyncTest:test_mix.task_test.async_access_long",
    "AsyncTest:test_mix.task_test.task_nested",
    "AsyncTest:test_mix.task_test.task_nested",
    "AsyncTest:test_mix.task_test.task_nested.async_access_short",
    "AsyncTest:test_mix.task_test.task_nested.async_access_short",
]

test_mix_out_values = [2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 6.0]


sync_in_async_methods = [
    "AsyncTest:sync_in_async",
    "AsyncTest:sync_in_async",
    "AsyncTest:sync_in_async.sync_access_long",
    "AsyncTest:sync_in_async.sync_access_long",
]
sync_in_async_values = [2.0, 2.0, 2.0, 2.0]

error_flag_out = [
    ("DummyResource:post.delete.put", "error_raised=True"),
    ("DummyResource:post.delete", "error_raised=False"),
    ("DummyResource:post", "error_raised=False"),
]
