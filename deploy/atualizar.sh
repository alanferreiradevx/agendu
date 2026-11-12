#!/usr/bin/env bash
# Coloca uma versão nova do Agendu no ar. Rodar como root no servidor.
# Normalmente é chamado pelo deploy\enviar.ps1, a partir do Windows.
#
#   bash atualizar.sh /tmp/agendu.tar.gz
#
# Guarda a versão anterior em /srv/agendu/app.anterior. Para voltar:
#   rm -rf /srv/agendu/app && mv /srv/agendu/app.anterior /srv/agendu/app && systemctl restart agendu
set -euo pipefail

PACOTE="${1:-/tmp/agendu.tar.gz}"
BASE=/srv/agendu
APP=$BASE/app
NOVO=$BASE/app.novo

echo "==> Extraindo $PACOTE"
rm -rf "$NOVO"
mkdir -p "$NOVO"
tar -xzf "$PACOTE" -C "$NOVO"
find "$NOVO/deploy" -name '*.sh' -exec sed -i 's/\r$//' {} +

echo "==> Dependências do Python"
[ -d "$BASE/venv" ] || python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install -q --upgrade pip
"$BASE/venv/bin/pip" install -q -r "$NOVO/requirements-producao.txt"

echo "==> Conferindo a versão nova antes de trocar"
set -a; . /etc/agendu/env; set +a
(cd "$NOVO" && "$BASE/venv/bin/python" manage.py check --deploy --fail-level ERROR)

echo "==> Trocando a versão"
rm -rf "$BASE/app.anterior"
[ -d "$APP" ] && mv "$APP" "$BASE/app.anterior"
mv "$NOVO" "$APP"
chown -R root:agendu "$APP"
chmod -R g+rX,o-rwx "$APP"

echo "==> Banco e arquivos estáticos"
cd "$APP"
"$BASE/venv/bin/python" manage.py migrate --noinput
# --clear: o pacote mantém a data dos arquivos do PC; sem ele o CSS novo podia ser ignorado
"$BASE/venv/bin/python" manage.py collectstatic --noinput --clear -v 0
chown -R agendu:agendu "$BASE/dados/staticfiles" "$BASE/dados/cache"

echo "==> Reiniciando"
systemctl restart agendu
for i in $(seq 1 20); do
    codigo=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DJANGO_ALLOWED_HOSTS%%,*}" \
        -H "X-Forwarded-Proto: https" http://127.0.0.1:8002/entrar/ || true)
    if [ "$codigo" = "200" ]; then
        echo "OK: Agendu no ar."
        exit 0
    fi
    sleep 1
done
echo "ERRO: o Agendu não respondeu. Veja o log com:  journalctl -u agendu -n 50"
exit 1
