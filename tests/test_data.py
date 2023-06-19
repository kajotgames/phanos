time_profile_out = [
    {
        "item": "time_profiler",
        "metric": "histogram",
        "units": "mS",
        "job": "TESTS",
        "method": "GET",
        "labels": {"context": "DummyResource:get.first_access"},
        "value": ("observe", 2.0),
    },
    {
        "item": "time_profiler",
        "metric": "histogram",
        "units": "mS",
        "job": "TESTS",
        "method": "GET",
        "labels": {"context": "DummyResource:get.second_access.first_access"},
        "value": ("observe", 2.0),
    },
    {
        "item": "time_profiler",
        "metric": "histogram",
        "units": "mS",
        "job": "TESTS",
        "method": "GET",
        "labels": {"context": "DummyResource:get.second_access"},
        "value": ("observe", 5.0),
    },
    {
        "item": "time_profiler",
        "metric": "histogram",
        "units": "mS",
        "job": "TESTS",
        "method": "GET",
        "labels": {"context": "DummyResource:get"},
        "value": ("observe", 7.0),
    },
]

hist_no_lbl = [
    {
        "item": "hist_no_lbl",
        "metric": "histogram",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("observe", 2.0),
    }
]

hist_w_lbl = [
    {
        "item": "hist_w_lbl",
        "metric": "histogram",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {"test": "test"},
        "value": ("observe", 2.0),
    }
]

sum_no_lbl = [
    {
        "item": "sum_no_lbl",
        "metric": "summary",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("observe", 2.0),
    }
]

cnt_no_lbl = [
    {
        "item": "cnt_no_lbl",
        "metric": "counter",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("inc", 2.0),
    }
]

inf_no_lbl = [
    {
        "item": "inf_no_lbl",
        "metric": "info",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("info", {"value": "asd"}),
    }
]

gauge_no_lbl = [
    {
        "item": "gauge_no_lbl",
        "metric": "gauge",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("inc", 2.0),
    },
    {
        "item": "gauge_no_lbl",
        "metric": "gauge",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("dec", 2.0),
    },
    {
        "item": "gauge_no_lbl",
        "metric": "gauge",
        "units": "V",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("set", 2.0),
    },
]

enum_no_lbl = [
    {
        "item": "enum_no_lbl",
        "metric": "enum",
        "units": "enum",
        "job": "TESTS",
        "method": "GET",
        "labels": {},
        "value": ("state", "true"),
    }
]
