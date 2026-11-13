-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /home/apexmt5/bridge-runtime/apex_deriv_accounts.sqlite3
-- Database copy: db-7edb8cb41e4c1e41001b.sqlite3
-- Customer records not included.

CREATE TABLE profiles(
        login TEXT NOT NULL, server TEXT NOT NULL,
        label TEXT NOT NULL, requested_at TEXT,
        PRIMARY KEY(login,server)
    );
