import math


def is_threshold_failed(actual, comparison, expected):
    if comparison == 'gte':
        return actual >= expected
    elif comparison == 'lte':
        return actual <= expected
    elif comparison == 'gt':
        return actual > expected
    elif comparison == 'lt':
        return actual < expected
    elif comparison == 'eq':
        return actual == expected
    return False


def get_aggregated_value(aggregation, metrics):
    if aggregation == 'max':
        return max(metrics)
    elif aggregation == 'min':
        return min(metrics)
    elif aggregation == 'avg':
        return int(sum(metrics) / len(metrics))
    elif aggregation == 'pct95':
        return percentile(metrics, 95)
    elif aggregation == 'pct50':
        return percentile(metrics, 50)
    else:
        raise Exception(f"No such aggregation {aggregation}")


def percentile(data, percentile):
    size = len(data)
    return sorted(data)[int(math.ceil((size * percentile) / 100)) - 1]

