import typing


def parse_output(out: typing.List[str]) -> typing.Tuple[list, list, list]:
    values = list()
    methods = list()
    labels = list()
    for line in out:
        split = line.split(", ")
        methods.append(split[1].split(": ")[1])
        values.append(float(split[2].split(": ")[1][:-3]) // 100)
        try:
            labels.append(split[3].split(": ")[1][:-1])
        except IndexError:
            pass
    return methods, values, labels
