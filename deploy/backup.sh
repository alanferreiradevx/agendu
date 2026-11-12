#!/usr/bin/env bash
# Backup do banco e das fotos do Agendu. Instalado como /usr/local/bin/agendu-backup
# e roda todo dia às 3h30 (o do Ativix roda às 3h). Guarda 14 dias.
set -euo pipefail

DESTINO=/srv/agendu/backups
DIAS=14
DATA=$(date +%Y-%m-%d_%H%M)
set -a; . /etc/agendu/env; set +a

umask 077
sudo -u postgres pg_dump --no-owner "$DB_NAME" | gzip > "$DESTINO/banco_$DATA.sql.gz"
tar -czf "$DESTINO/fotos_$DATA.tar.gz" -C /srv/agendu/dados privado
find "$DESTINO" -name '*.gz' -mtime +"$DIAS" -delete
echo "$(date '+%F %T') backup ok: banco_$DATA.sql.gz fotos_$DATA.tar.gz"
