# Experimental Sequence Models

LSTM, GRU, TCN and TFT are experimental research models in pyMercator.

They do not replace the current operational engines:

- extratrees
- randomforest
- gradientboosting
- multi_horizon_ridge

Rules for future work:

- Sequence models must run only with `experimental_models=true` or an equivalent explicit laboratory flag.
- They must be evaluated with walk-forward validation.
- They must be compared against the current baseline and ensemble.
- They must not become operational defaults without a separate approval and test cycle.
- The first safe use is as feature encoders, not as final decision engines.

Operational run, basket, model_quality guard and behavior guard must remain
unchanged while these models are investigated.
