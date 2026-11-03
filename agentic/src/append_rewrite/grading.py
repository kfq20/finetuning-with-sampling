"""Strict reward-channel decoding shared by runtime and diagnostics."""

import json
import math


def parse_rewards(files):
    values = {}
    for name, text in files.items():
        if name == "reward.txt":
            value = float(text.strip())
        elif name == "reward.json":
            data = json.loads(text)
            value = data["reward"] if isinstance(data, dict) else data
        else:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or value not in (0, 1)
        ):
            raise ValueError("InvalidReward")
        values[name] = float(value)
    if len(set(values.values())) > 1:
        raise ValueError("ConflictingRewardChannels")
    return next(iter(values.values()), None)
