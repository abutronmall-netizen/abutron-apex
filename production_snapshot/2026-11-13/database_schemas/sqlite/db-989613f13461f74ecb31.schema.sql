-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-ai-smc-evidence/prospective/first_seen.sqlite3
-- Database copy: db-989613f13461f74ecb31.sqlite3
-- Customer records not included.

CREATE TABLE decision_first_seen(
   account_hash TEXT NOT NULL,symbol TEXT NOT NULL,m5_bar_utc INTEGER NOT NULL,
   side TEXT NOT NULL,verdict TEXT NOT NULL,reason TEXT NOT NULL,
   smc TEXT NOT NULL,ai_report_current INTEGER NOT NULL,
   first_seen_utc TEXT NOT NULL,
   PRIMARY KEY(account_hash,symbol,m5_bar_utc,side,verdict));
