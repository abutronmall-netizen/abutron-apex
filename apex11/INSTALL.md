# Local verification only

This is a staged APEX 1.1.0 replacement source. It is not a production installer.

```bash
python3 -m pytest -q
```

The current `abutron_replacement/` interfaces consume authenticated-structure candle exports, create APEX signals and account/risk-reviewed order candidates, and run a descriptive cost replay. They do not connect those candidates to a production MT5 order sender.

Original upstream APEX documentation is retained in `README.md`. Its deployment and Deriv trader examples are not tested or enabled by this staged package; `install.sh` and direct Deriv submit paths remain disabled because the server was not authorized for changes.
