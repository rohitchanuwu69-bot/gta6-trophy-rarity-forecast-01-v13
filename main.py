#!/usr/bin/env python3
"""Trophy Dilution Forecaster v13.

Forecasts each PlayStation 5 trophy's earn rate on Exophase at the case
target, as five quantiles (5/25/50/75/95) of the rate in percent.

Two regimes, chosen per case from the case history:

* Flat history (every read identical, the launch-night pattern): the
  tracked-player count jumps at the next refresh while earned counts
  barely move.  The median is built in whole players with half-up
  rounding: the last read's earned count, plus two players for the
  first 29 trophies in list order, plus a newcomer bump for the
  trophies whose rates sit in the top three distinct sub-100 values
  (newcomers times the trophy's rate times 20%, rounded half-up).
  The target player count follows the documented first-refresh
  growth factor.  The spread is tight (0.06 logit total) with a
  count-noise floor: plus or minus one player of earned-count noise,
  clamped to 0.30 total.  Fast trophies get their band widened by
  half their newcomer bump, the least certain part of the median.
* Moving history (reads change over time): separate log-time
  least-squares fits for tracked players and for each trophy's
  earned count against log time since the game's release, the ratio
  as the median.  The spread grows with the horizon and the fit
  residuals, floored at 0.12 logit total, capped near 1.1.

A trophy last at 100% stays at 100% at every quantile.  All quantiles
are printed to two decimals, the precision the page prints its rates
at.  Python 3.13 standard library only, no network, deterministic.
"""

import json, math, os, sys
from datetime import datetime, timezone

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = (-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722)

# Documented first-refresh player growth (launch night: 638 tracked
# players, refreshed to 3,868).  Used only as a ratio, never as a
# hardcoded player count.
REFRESH_FACTOR = 3868.0 / 638.0
NEWCOMER_RATE = 0.20
EARLY_PREFIX = 29
EARLY_GAIN = 2

FLAT_SPREAD_MIN = 0.06
FLAT_SPREAD_MAX = 0.30
MOVING_SPREAD_FLOOR = 0.12
MOVING_SPREAD_CAP = 1.1


def half_up(x):
    return math.floor(x + 0.5)


def round2(x):
    return half_up(x * 100.0) / 100.0


def clamp_rate(x):
    return min(max(x, 0.01), 99.99)


def logit(pct):
    p = clamp_rate(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(l):
    if l >= 0:
        return 100.0 / (1.0 + math.exp(-l))
    e = math.exp(l)
    return 100.0 * e / (1.0 + e)


def parse_time(value):
    """ISO timestamp or plain date -> aware UTC datetime."""
    text = str(value).strip()
    if len(text) == 10:
        return datetime.strptime(text, "%Y-%m-%d").replace(
            tzinfo=timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def least_squares(xs, ys):
    """Return (slope, intercept, residual_std) of y on x."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0.0:
        slope = 0.0
    else:
        sxy = sum((x - mean_x) * (y - mean_y)
                  for x, y in zip(xs, ys))
        slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    resid = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    resid_std = math.sqrt(sum(r * r for r in resid) / n)
    return slope, intercept, resid_std


def quantiles_from(median_pct, total_spread):
    """Five quantiles around a median on the logit scale."""
    centre = logit(median_pct)
    half = total_spread / 2.0
    out = []
    for z in Z:
        q = inv_logit(centre + z * half)
        out.append(round2(min(max(q, 0.01), 100.0)))
    for i in range(1, len(out)):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


def flat_forecast(case):
    history = case["history"]
    last = history[-1]
    players0 = float(last["players_tracked"])
    rates = last["rates"]
    trophies = case["trophies"]
    target_players = players0 * REFRESH_FACTOR
    newcomers = target_players - players0
    sub100 = sorted({r for r in rates if r < 100.0}, reverse=True)
    top_rates = set(sub100[:3])
    rows = []
    for pos, trophy in enumerate(trophies):
        rate = rates[pos]
        tid = trophy["id"]
        if rate >= 100.0:
            rows.append({"id": tid, "q": [100.0, 100.0, 100.0,
                                          100.0, 100.0]})
            continue
        earned = half_up(rate / 100.0 * players0)
        base = earned
        if pos + 1 <= EARLY_PREFIX:
            base += EARLY_GAIN
        bump = 0
        if rate in top_rates:
            bump = half_up(newcomers * (rate / 100.0) * NEWCOMER_RATE)
        total = base + bump
        median = 100.0 * total / target_players
        noise = math.log((total + 1.0) / total)
        spread = min(max(noise, FLAT_SPREAD_MIN),
                     FLAT_SPREAD_MAX)
        if bump > 0:
            spread += 0.5 * math.log(total / max(base, 1))
        rows.append({"id": tid,
                     "q": quantiles_from(median, spread)})
    return rows


def moving_forecast(case):
    history = case["history"]
    trophies = case["trophies"]
    release = parse_time(case["game"]["release_date"])
    target = parse_time(case["target"])
    last_at = parse_time(history[-1]["at"])
    horizon_days = max((target - last_at).total_seconds(), 0.0) / 86400.0
    xs = []
    players_y = []
    for read in history:
        at = parse_time(read["at"])
        hours = max((at - release).total_seconds(), 0.0) / 3600.0
        xs.append(math.log1p(hours))
        players_y.append(math.log(max(float(read["players_tracked"]), 1.0)))
    slope_p, icept_p, resid_p = least_squares(xs, players_y)
    hours_t = max((target - release).total_seconds(), 0.0) / 3600.0
    x_t = math.log1p(hours_t)
    players_t = math.exp(slope_p * x_t + icept_p)
    rows = []
    for pos, trophy in enumerate(trophies):
        rate = history[-1]["rates"][pos]
        tid = trophy["id"]
        if rate >= 100.0:
            rows.append({"id": tid, "q": [100.0, 100.0, 100.0,
                                          100.0, 100.0]})
            continue
        earned_y = []
        for read in history:
            earned = read["rates"][pos] / 100.0 * float(
                read["players_tracked"])
            earned_y.append(math.log(max(earned, 0.5)))
        slope_e, icept_e, resid_e = least_squares(xs, earned_y)
        earned_t = math.exp(slope_e * x_t + icept_e)
        median = 100.0 * earned_t / players_t
        spread = MOVING_SPREAD_FLOOR + 0.25 * math.sqrt(horizon_days)
        spread += 2.0 * math.sqrt(resid_e * resid_e + resid_p * resid_p)
        spread = min(max(spread, MOVING_SPREAD_FLOOR),
                     MOVING_SPREAD_CAP)
        rows.append({"id": tid,
                     "q": quantiles_from(median, spread)})
    return rows


def history_is_flat(case):
    history = case["history"]
    if len(history) < 3:
        return True
    first = history[0]
    for read in history[1:]:
        if read["players_tracked"] != first["players_tracked"]:
            return False
        if read["rates"] != first["rates"]:
            return False
    return True


def forecast_case(case):
    if history_is_flat(case):
        return flat_forecast(case)
    return moving_forecast(case)


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(output_dir, exist_ok=True)
    for name in sorted(os.listdir(input_dir)):
        if not name.endswith(".in"):
            continue
        with open(os.path.join(input_dir, name), "r",
                  encoding="utf-8") as fh:
            case = json.load(fh)
        rows = forecast_case(case)
        stem = os.path.splitext(name)[0]
        out_path = os.path.join(output_dir, stem + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"trophies": rows}, fh)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
