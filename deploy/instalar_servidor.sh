#!/usr/bin/env bash
# Prepara o Agendu num servidor Ubuntu 24.04 (pode ser o mesmo do Ativix). Rodar como root, UMA vez.
# Normalmente é chamado pelo deploy\enviar.ps1 -Instalar, a partir do Windows.
#
#   bash instalar_servidor.sh agendu.ativix.co voce@email.com /tmp/agendu.tar.gz
#
# Não mexe no Ativix: usuário, banco, pasta, porta (8002) e site do nginx são separados.
# Pode ser rodado de novo sem estragar nada (ex.: se o certificado falhou por causa do DNS).
set -euo pipefail

DOMINIO="${1:?uso: instalar_servidor.sh DOMINIO EMAIL [PACOTE]}"
EMAIL="${2:?uso: instalar_servidor.sh DOMINIO EMAIL [PACOTE]}"
PACOTE="${3:-/tmp/agendu.tar.gz}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
BASE=/srv/agendu
ENV=/etc/agendu/env

echo "==> Pacotes do sistema (já instalados se o Ativix estiver aqui)"
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=120 install -y -q python3-venv python3-dev postgresql nginx certbot \
    python3-certbot-nginx ufw curl >/dev/null

echo "==> Usuário e pastas"
id agendu >/dev/null 2>&1 || useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin agendu
mkdir -p "$BASE"/dados/{privado,staticfiles,cache} "$BASE"/backups /etc/agendu
chown -R agendu:agendu "$BASE"/dados
chmod 750 "$BASE"/dados/privado "$BASE"/backups

echo "==> Banco de dados (PostgreSQL, banco próprio: agendu)"
if [ ! -f "$ENV" ]; then
    SENHA_DB="$(openssl rand -hex 24)"
    if sudo -u postgres psql -tAc "select 1 from pg_roles where rolname='agendu'" | grep -q 1; then
        sudo -u postgres psql -q -c "alter role agendu with login password '$SENHA_DB'"
    else
        sudo -u postgres psql -q -c "create role agendu with login password '$SENHA_DB'"
    fi
    sudo -u postgres psql -tAc "select 1 from pg_database where datname='agendu'" | grep -q 1 \
        || sudo -u postgres createdb -O agendu agendu

    echo "==> Configuração (segredos em $ENV)"
    umask 027
    cat > "$ENV" <<EOF
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=$(openssl rand -hex 40)
DJANGO_ALLOWED_HOSTS=$DOMINIO
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMINIO
DJANGO_ATRAS_DE_PROXY=true
DJANGO_PRIVADO_ROOT=$BASE/dados/privado
DJANGO_STATIC_ROOT=$BASE/dados/staticfiles
DJANGO_CACHE_DIR=$BASE/dados/cache
DB_NAME=agendu
DB_USER=agendu
DB_PASSWORD=$SENHA_DB
DB_HOST=localhost
DB_PORT=5432
EOF
    umask 022
    chown root:agendu "$ENV"
    chmod 640 "$ENV"
else
    echo "    $ENV já existe; mantendo (senha do banco e chave secreta não mudam)."
fi

echo "==> Atalho agendu-manage (roda o manage.py como o usuário agendu)"
cat > /usr/local/bin/agendu-manage <<'EOF'
#!/usr/bin/env bash
set -a; . /etc/agendu/env; set +a
cd /srv/agendu/app
exec sudo --preserve-env -u agendu /srv/agendu/venv/bin/python manage.py "$@"
EOF
chmod 755 /usr/local/bin/agendu-manage

echo "==> Serviço do sistema"
install -m 644 "$AQUI/agendu.service" /etc/systemd/system/agendu.service
systemctl daemon-reload
systemctl enable agendu >/dev/null

echo "==> Código"
bash "$AQUI/atualizar.sh" "$PACOTE"

echo "==> nginx (site próprio; o do Ativix não muda)"
sed "s/DOMINIO/$DOMINIO/g" "$AQUI/nginx-agendu.conf" > /etc/nginx/sites-available/agendu
ln -sf /etc/nginx/sites-available/agendu /etc/nginx/sites-enabled/agendu
nginx -t
systemctl reload nginx

echo "==> Firewall (só SSH, HTTP e HTTPS)"
ufw allow OpenSSH >/dev/null
ufw allow "Nginx Full" >/dev/null
ufw --force enable >/dev/null

echo "==> Backup diário às 3h30 (guarda 14 dias em $BASE/backups)"
install -m 755 "$AQUI/backup.sh" /usr/local/bin/agendu-backup
echo '30 3 * * * root /usr/local/bin/agendu-backup >> /var/log/agendu-backup.log 2>&1' > /etc/cron.d/agendu

echo "==> Certificado HTTPS (Let's Encrypt)"
if [ "$EMAIL" = "sem-email" ]; then CONTA=(--register-unsafely-without-email); else CONTA=(-m "$EMAIL"); fi
if certbot --nginx -d "$DOMINIO" "${CONTA[@]}" --agree-tos --redirect -n; then
    echo ""
    echo "Pronto! Abra https://$DOMINIO"
    echo "Crie o seu usuário com:  agendu-manage createsuperuser"
else
    echo ""
    echo "ATENÇÃO: não consegui o certificado. Confira se o DNS de $DOMINIO aponta para"
    echo "este servidor e rode de novo:  certbot --nginx -d $DOMINIO ${CONTA[*]} --agree-tos --redirect -n"
    exit 1
fi
