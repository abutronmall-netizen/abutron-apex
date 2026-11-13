-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /home/dcagent/abutron-recovery/staging/reconstruction/v4-20260926-isolated/data/abutron_decisions.db
-- Database copy: db-70d09fb673571c2fe796.sqlite3
-- Customer records not included.

CREATE TABLE decisions(id INTEGER PRIMARY KEY AUTOINCREMENT,created_ts INTEGER NOT NULL,symbol TEXT NOT NULL,mode TEXT NOT NULL,direction TEXT NOT NULL,confidence REAL NOT NULL,approved INTEGER NOT NULL,reason TEXT NOT NULL,payload TEXT NOT NULL);

CREATE TABLE sqlite_sequence(name,seq);
