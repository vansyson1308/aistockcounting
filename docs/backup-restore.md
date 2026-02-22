# Backup & Restore

Backups are stored at `/opt/vj-inventory/backups/`.

## Manual backup
```bash
cd /opt/vj-inventory/current
./ops/backup/backup_all.sh
```

## Manual restore
```bash
./ops/backup/restore_postgres.sh /opt/vj-inventory/backups/<timestamp>/postgres.dump
./ops/backup/restore_minio.sh /opt/vj-inventory/backups/<timestamp>/minio.tar.gz
```

## Cron example
Run every day at 02:30 and prune at 03:00:
```cron
30 2 * * * cd /opt/vj-inventory/current && ./ops/backup/backup_all.sh >> /var/log/vj-backup.log 2>&1
0 3 * * * cd /opt/vj-inventory/current && ./ops/backup/prune_backups.sh >> /var/log/vj-backup.log 2>&1
```

## Restore drill
1. Create fresh backup.
2. Restore into staging maintenance window.
3. Run `./ops/smoke_test.sh`.
4. Verify counts table row count and sample image retrieval.

## MVP RPO/RTO
- Target RPO: 24h (daily backups).
- Target RTO: 1-2h (operator-guided restore).
