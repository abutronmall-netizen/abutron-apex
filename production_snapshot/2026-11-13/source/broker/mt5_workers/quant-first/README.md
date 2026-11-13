# ABUTRON APEX quant-first research layer v1

Status: installed as read-only shadow research, **not activated in native order execution**.

## Evidence and rationale
- Verified Nov 6 pre-change offsite Restic backup: /var/log/abutron-full-backup-20261106T133552Z.log ends FULL_PRECHANGE_BACKUP_END_SUCCESS and remote metadata/DB readback checks PASS.
- Native Deriv input /var/lib/apex/operator-live/native-market.json; limited to Volatility 25/50/75 for new research; history and existing positions untouched.
- Native FP partial research inputs /var/lib/abutron-fpmarkets-feed/partial/*.json; each connection isolated by fingerprint, no cross-account normalization. Current feed is partial and multiple FP DEMO links make automatic qualification unsafe.
- SMC/ICT are not called by this module. The currently active Deriv native signal router explicitly states SMC/ICT/veto not consulted; the FP research scanner already marks SMC/ICT REMOVED.
- Quant feature engineering: 20/60-return realized volatility, volatility regime ratio, trend z-score, price-path efficiency, M5 ATR, EMA20 normalized extension, M5 candle pressure, M15/H1 drift confirmation, FP bid/ask spread cost/ATR.
- Flow labels: Deriv candle price-flow proxy only, **not** true order flow; FP broker bid/ask quote cost only, **not** traded volume or institution-wide depth.
- No training, measured alpha, statistical confidence, validated edge, walk-forward certification, order submission, SL/TP change, account toggle, risk modification or claim of profitability.
- Research signals are written to /var/lib/abutron-quant-first/latest.json. They are NOT connected to the MT5 router.
- Unit service uses private network and read-only filesystem except isolated output directory.

## Verification
Run: python3 -B /opt/apex-client-mt5/quant-first/test_abutron_quant_first_v1.py
Run: systemctl status abutron-quant-first-shadow.service abutron-quant-first-shadow.timer
See: /var/lib/abutron-quant-first/latest.json

## Rollback (new shadow component only)
sudo systemctl disable --now abutron-quant-first-shadow.timer
sudo systemctl stop abutron-quant-first-shadow.service
sudo rm /etc/systemd/system/abutron-quant-first-shadow.service /etc/systemd/system/abutron-quant-first-shadow.timer
sudo systemctl daemon-reload
Remove the new /opt/apex-client-mt5/quant-first directory and /var/lib/abutron-quant-first research outputs only after preserving evidence.
These steps do not change pre-existing execution or trading-risk configuration.

## Gate before promoting any quant signal into order execution
Verified broker data lineage and complete FP per-account feed; point-in-time walk-forward with costs and untouched holdout; independent DEMO forward performance; stable EA/ledger reconciliation; performance risk review; explicit reversible cutover. No LIVE promotion or new strategy authorization from this work.
