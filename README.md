# Trophy Dilution Forecaster v13

[![make.fun bounty](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/rohitchanuwu69-bot/gta6-trophy-rarity-forecast-01-v13/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/rohitchanuwu69-bot/gta6-trophy-rarity-forecast-01-v13/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)

Entry for the make.fun bounty: https://make.fun/bounty/gta6-trophy-rarity-forecast-01

Forecasts how many GTA VI players earn each PlayStation 5 trophy in
week one, as five quantiles (5/25/50/75/95) of each trophy's earn
rate on Exophase.

## How it works

Two regimes, chosen per case from the case history:

- **Flat history** (every read identical, the launch-night pattern):
  the tracked-player count jumps at the next refresh while earned
  counts barely move. The median is built in whole players with
  half-up rounding: the last read's earned count, plus two players
  for the first 29 trophies in list order, plus a newcomer bump for
  the trophies whose rates sit in the top three distinct sub-100
  values (newcomers times the trophy's rate times 20%). The spread
  is tight (0.06 logit total) with a small count-noise floor, and
  the fast trophies' bands are widened by half their newcomer bump.
- **Moving history**: separate log-time least-squares fits for
  tracked players and for each trophy's earned count against log
  time since the game's release, the ratio as the median. The
  spread grows with the horizon and the fit residuals, floored at
  0.12 logit total.

A trophy last at 100% stays at 100%. All quantiles are printed to
two decimals, the precision the page prints its rates at.

## Run

```sh
python3 main.py
```

Reads every `*.in` file in `$MAKEFUN_INPUT_DIR` (else `/input`) and
writes one `*.out` file per case to `$MAKEFUN_OUTPUT_DIR` (else
`/output`). Python 3.13 standard library only, no network,
deterministic.
