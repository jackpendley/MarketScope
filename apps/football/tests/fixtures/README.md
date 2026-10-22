# Test fixtures

- `results_2016_2024.csv`: NFL game results 2016–2024 (regular season and playoffs; franchise codes) from
  [nflverse](https://github.com/nflverse) schedules, licensed CC-BY 4.0. Real public results, used by
  `tests/test_simulate.py` to check that the tiebreakers reproduce the actual playoff fields. No odds.

## synthetic_forward_test.csv (SYNTHETIC)

**Synthetic data, not real games, results or odds.** 60 made-up scored estimates in the shape of the live
forward test, generated with a fixed seed. Used by `tests/test_model_card.py` and as the credential-free
demo of the generated model card:

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.model_card \
        --scored tests/fixtures/synthetic_forward_test.csv --json /tmp/card.json --markdown /tmp/card.md
