"""Funções pequenas usadas em vários apps."""

import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

from django.conf import settings


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def whatsapp_url(telefone, mensagem=""):
    """
    Link que abre o WhatsApp (celular ou WhatsApp Web) com a mensagem pronta.
    Não envia nada sozinho: você confere e aperta enviar. Grátis, sem API paga.
    """
    numero = so_digitos(telefone)
    if not numero:
        return ""
    if len(numero) in (10, 11):  # DDD + número, sem o 55 do Brasil
        numero = "55" + numero
    url = f"https://wa.me/{numero}"
    if mensagem:
        url += "?text=" + quote(mensagem)
    return url


def formatar_mensagem(modelo, **valores):
    """Troca {nome}, {hora}... sem quebrar se a mensagem tiver uma chave desconhecida."""

    class Seguro(dict):
        def __missing__(self, chave):
            return "{" + chave + "}"

    return modelo.format_map(Seguro(**valores))


def centavos(valor):
    return Decimal(valor or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def brl(valor):
    """1234.5 -> 'R$ 1.234,50'"""
    v = centavos(valor)
    sinal = "-" if v < 0 else ""
    inteiro, dec = f"{abs(v):.2f}".split(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{sinal}R$ {inteiro},{dec}"


def ip_do_cliente(request):
    if getattr(settings, "ATRAS_DE_PROXY", False):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if encaminhado:
            return encaminhado.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")
