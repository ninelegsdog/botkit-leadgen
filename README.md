
## Бэкапы
Крон на VPS (ежедневно 04:00, retention 14 дней):
```
0 4 * * * AGE_RECIPIENT=age1... OFFSITE_TARGET=user@backup-host:/srv/backups /usr/local/bin/botkit-backup.sh BOTNAME
```
Восстановление:
```
botkit-restore.sh BOTNAME <db-name>.db ~/.secrets/keys/backup.txt [target-dir]
```
Скрипты: `~/bin/backup/{botkit-backup.sh,botkit-restore.sh}`.
