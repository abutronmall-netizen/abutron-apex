-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-v7-mt5-enrollment-gate/rate-limits.sqlite3
-- Database copy: db-c2b46a6a1b2400785800.sqlite3
-- Customer records not included.

CREATE INDEX idx_attempts_scope ON attempts(subject,at);

CREATE INDEX idx_challenge_exp ON challenge(expires);

CREATE TABLE attempts (subject TEXT NOT NULL, at INTEGER NOT NULL);

CREATE TABLE challenge (digest TEXT PRIMARY KEY,owner TEXT NOT NULL, expires INTEGER NOT NULL);
