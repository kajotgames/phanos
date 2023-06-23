resp_size_out = {
    "item": "DummyResource",
    "metric": "histogram",
    "units": "B",
    "job": "TEST",
    "method": "DummyResource:get",
    "labels": {},
    "value": ("observe", 56.0),
}

time_profile_out = [
    {
        "item": "DummyResource",
        "metric": "histogram",
        "units": "mS",
        "job": "TEST",
        "method": "DummyResource:get.first_access",
        "labels": {},
        "value": ("observe", 2.0),
    },
    {
        "item": "DummyResource",
        "metric": "histogram",
        "units": "mS",
        "job": "TEST",
        "method": "DummyResource:get.second_access.first_access",
        "labels": {},
        "value": ("observe", 2.0),
    },
    {
        "item": "DummyResource",
        "metric": "histogram",
        "units": "mS",
        "job": "TEST",
        "method": "DummyResource:get.second_access",
        "labels": {},
        "value": ("observe", 5.0),
    },
    {
        "item": "DummyResource",
        "metric": "histogram",
        "units": "mS",
        "job": "TEST",
        "method": "DummyResource:get",
        "labels": {},
        "value": ("observe", 7.0),
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
test_handler_out = "profiler: test_name, method: DummyResource:get.first_access, value: 2.0 mS, labels: test = value\n"
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
