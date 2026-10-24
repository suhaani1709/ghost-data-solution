-- Ghost Data Still Exists: point-in-time database snapshot
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-06-20T23:00:00Z
-- Database topology: failover_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_profiles_failover_replica (
                resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
                account_status TEXT NOT NULL, updated_at TEXT NOT NULL
            );
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9101','user_9101','Cora Vance','cora.vance@example.com','+1 555 0111','ACTIVE','2026-06-20T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9002','user_9002','Ben Okafor-Lind','ben.okafor@example.com','+1 555 0102','ACTIVE','2026-06-20T22:45:00Z');
CREATE TABLE customer_profiles_primary (
                resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
                account_status TEXT NOT NULL, updated_at TEXT NOT NULL
            );
INSERT INTO "customer_profiles_primary" VALUES('account_9002','user_9002','Ben Okafor-Lind','ben.okafor@example.com','+1 555 0102','ACTIVE','2026-06-20T22:45:00Z');
COMMIT;
