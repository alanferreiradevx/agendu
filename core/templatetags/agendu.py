import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from core.utils import brl

register = template.Library()


@register.filter
def dinheiro(valor):
    """{{ valor|dinheiro }} -> R$ 1.234,50"""
    return brl(valor)


@register.filter
def numero(valor):
    """Quantidade sem zeros sobrando: 2.000 -> 2 ; 1.500 -> 1,5"""
    if valor is None:
        return "—"
    texto = f"{valor:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


@register.simple_tag(takes_context=True)
def ativo_se(context, *prefixos):
    caminho = context["request"].path
    return " ativo" if any(caminho.startswith(p) for p in prefixos) else ""


@register.simple_tag
def static_versao(caminho):
    """Endereço do CSS/JS com ?v=<data do arquivo>: o navegador baixa de novo quando o arquivo muda."""
    arquivo = finders.find(caminho) or str(settings.STATIC_ROOT / caminho)
    try:
        versao = int(os.path.getmtime(arquivo))
    except (OSError, TypeError):
        versao = 0
    return f"{static(caminho)}?v={versao}"


@register.simple_tag(takes_context=True)
def valor(context, quantia):
    """{% valor x %}: R$ 1.234,50 com o financeiro aberto; R$ ••• com ele trancado."""
    if context.get("financeiro_liberado"):
        return brl(quantia)
    return "R$ •••"
