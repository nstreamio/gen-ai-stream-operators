prompt = """
Generate a Python function that implements a streaming operator for calculating the 
{operation} of a sequence of values. The function should take two arguments: 
an accumulator (acc) and a new value (x). It should return a tuple containing the 
updated accumulator and the result of the calculation. The accumulator should be 
initialized appropriately if it is empty. The function should be efficient, numerically 
stable, and able to handle large sequences without significant performance degradation 
or errors. For numerical stability, please use a well-known algorithm such as 
Welford’s online algorithm to avoid issues with precision and accumulation of rounding 
errors. Ensure that the function does not modify the input accumulator directly.

Specifically, the function should:
- Take two arguments: acc (accumulator) and x (new value)
- Return a tuple containing: (updated_acc, result)
- Initialize the accumulator appropriately if it is empty
- Perform the specified calculation using the accumulator and new value
- Return the updated accumulator and result

Please write a Python function that meets these requirements for the following calculation:
{operation}
"""

def ema(acc, x):
    """
    Calculate the exponential moving average using Welford's online algorithm.

    Args:
    - acc (tuple): Accumulator containing the count and mean of the sequence.
    - x (float): New value in the sequence.

    Returns:
    - tuple: Updated accumulator and the result of the calculation.
    """
    if not acc:  # Initialize the accumulator if it's empty
        acc = (1, x)
    else:
        count, mean = acc
        count += 1
        mean += (x - mean) / count
        acc = (count, mean)
    return acc, mean


def sma(acc, x, window_size):
    """
    Calculate the simple moving average.

    Args:
    - acc (list): List of previous data points.
    - x (float): New value in the sequence.
    - window_size (int): Size of the moving average window.

    Returns:
    - list: Updated accumulator and the result of the calculation.
    """
    if not acc:
        acc = [x]
    else:
        acc.append(x)
        if len(acc) > window_size:
            acc.pop(0)
    return acc, sum(acc) / len(acc)


def variance(acc, x):
    """
    Calculate the variance of a streaming data set.

    Args:
    - acc (tuple): Accumulator containing the count, mean, and sum of squared differences.
    - x (float): New value in the data stream.

    Returns:
    - tuple: Updated accumulator and the variance.
    """
    if not isinstance(x, (int, float)):
        raise ValueError("The new value 'x' must be a numeric value")

    if not acc:
        # Initialize the accumulator
        n, mean, sum_squared_diffs = 0, 0.0, 0.0
    else:
        n, mean, sum_squared_diffs = acc

    n += 1
    delta = x - mean
    mean += delta / n
    delta2 = x - mean
    sum_squared_diffs += delta * delta2

    if n < 2:
        variance = None
    else:
        variance = sum_squared_diffs / (n - 1)

    updated_acc = (n, mean, sum_squared_diffs)

    return updated_acc, variance


def stddev(acc, x):
    """
    Calculate the standard deviation of a streaming data set.

    Args:
    - acc (tuple): Accumulator containing the count, mean, and sum of squared differences.
    - x (float): New value in the data stream.

    Returns:
    - tuple: Updated accumulator and the standard deviation.
    """
    if not isinstance(x, (int, float)):
        raise ValueError("The new value 'x' must be a numeric value")

    if not acc:
        # Initialize the accumulator
        n, mean, sum_squared_diffs = 0, 0.0, 0.0
    else:
        n, mean, sum_squared_diffs = acc

    n += 1
    delta = x - mean
    mean += delta / n
    delta2 = x - mean
    sum_squared_diffs += delta * delta2

    if n < 2:
        stddev = None
    else:
        variance = sum_squared_diffs / (n - 1)
        stddev = variance ** 0.5

    updated_acc = (n, mean, sum_squared_diffs)

    return updated_acc, stddev


