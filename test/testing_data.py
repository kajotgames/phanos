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
test_handler_out_no_lbl = (
    "profiler: test_name, method: DummyResource:get.first_access, value: 2.0 mS\n"
)

hist_no_lbl = [
    {
        "item": "test",
        "metric": "histogram",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("observe", 2.0),
    }
]

hist_w_lbl = [
    {
        "item": "test",
        "metric": "histogram",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {"test": "test"},
        "value": ("observe", 2.0),
    }
]

sum_no_lbl = [
    {
        "item": "test",
        "metric": "summary",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("observe", 2.0),
    }
]

cnt_no_lbl = [
    {
        "item": "test",
        "metric": "counter",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("inc", 2.0),
    }
]

inf_no_lbl = [
    {
        "item": "test",
        "metric": "info",
        "units": "info",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("info", {"value": "asd"}),
    }
]

gauge_no_lbl = [
    {
        "item": "test",
        "metric": "gauge",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("inc", 2.0),
    },
    {
        "item": "test",
        "metric": "gauge",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("dec", 2.0),
    },
    {
        "item": "test",
        "metric": "gauge",
        "units": "V",
        "job": "TEST",
        "method": "test:method",
        "labels": {},
        "value": ("set", 2.0),
    },
]

enum_no_lbl = [
    {
        "item": "test",
        "metric": "enum",
        "units": "enum",
        "job": "TEST",
        "method": "test:method",
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
