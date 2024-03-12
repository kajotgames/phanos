import typing
import math


def parse_output(out: typing.List[str]) -> typing.Tuple[list, list, list]:
    values = list()
    methods = list()
    labels = list()
    for line in out:
        split = line.split(", ")
        methods.append(split[1].split(": ")[1])
        measured_val = float(split[2].split(": ")[1][:-3])
        if "time_profile" in split[0]:  # round to 100ms so we can check for equality
            values.append(math.floor(measured_val / 100) * 100)
        else:
            values.append(measured_val)
        try:
            labels.append(split[3].split(": ")[1][:-1])
        except IndexError:
            pass
    return methods, values, labels
