from math import asin, erfc, hypot, sqrt
from statistics import NormalDist

ALPHA = 0.05


def wilson(successes, total):
    z = NormalDist().inv_cdf(1 - ALPHA / 2)
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    margin = z * sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return max(0, center - margin), min(1, center + margin)


def two_proportion(control_success, control_n, variant_success, variant_n):
    if not (0 <= control_success <= control_n and 0 <= variant_success <= variant_n and min(control_n, variant_n) > 0):
        raise ValueError('分母为空或成功人数超出分母')
    a, b = control_success / control_n, variant_success / variant_n
    pooled = (control_success + variant_success) / (control_n + variant_n)
    if min(control_n, variant_n) * min(pooled, 1 - pooled) < 5:
        raise ValueError('在零假设下至少一个期望格数小于 5，冻结两比例正态近似')
    diff = b - a
    z = diff / sqrt(pooled * (1 - pooled) * (1 / control_n + 1 / variant_n))
    p = erfc(abs(z) / sqrt(2))
    a_low, a_high = wilson(control_success, control_n)
    b_low, b_high = wilson(variant_success, variant_n)
    return {
        'a_success': control_success, 'a_n': control_n, 'a_rate': a,
        'b_success': variant_success, 'b_n': variant_n, 'b_rate': b,
        'difference': diff, 'z': z, 'p': p, 'alpha': ALPHA, 'significant': p < ALPHA,
        'ci_low': diff - hypot(b - b_low, a_high - a),
        'ci_high': diff + hypot(b_high - b, a - a_low),
        'cohen_h': 2 * (asin(sqrt(b)) - asin(sqrt(a))),
    }
