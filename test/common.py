import typing


def parse_output(out: typing.List[str]) -> typing.Tuple[list, list]:
    values = []
    methods = []
    for line in out:
        split = line.split(", ")
        methods.append(split[1].split(": ")[1])
        values.append(float(split[2].split(": ")[1][:-3]) // 100)
    return methods, values
