"""
Cofre do financeiro: tudo que mostra valores (caixa, preços, custos, pacotes)
só aparece depois da "senha do financeiro", que é diferente da senha de login.

A liberação fica na sessão e vence depois de FINANCEIRO_MINUTOS sem usar o
sistema (cada página aberta renova o prazo). O botão "Trancar" encerra na hora.
"""

import time
from functools import wraps

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

CHAVE = "financeiro_ate"


def _minutos():
    return getattr(settings, "FINANCEIRO_MINUTOS", 15)


def liberado(request):
    return request.session.get(CHAVE, 0) > time.time()


def liberar(request):
    request.session[CHAVE] = time.time() + _minutos() * 60


def trancar(request):
    request.session.pop(CHAVE, None)


def url_desbloquear(request):
    return reverse("financeiro_entrar") + "?" + urlencode({"next": request.get_full_path()})


def financeiro_obrigatorio(view):
    """Decorator das páginas de valores: sem a senha do financeiro, pede a senha antes."""

    @wraps(view)
    def interna(request, *args, **kwargs):
        if not liberado(request):
            return redirect(url_desbloquear(request))
        return view(request, *args, **kwargs)

    return interna


class FinanceiroMiddleware:
    """Renova o prazo a cada página e tranca a Administração (lá aparecem todos os valores)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            aberto = liberado(request)
            if aberto:
                liberar(request)
            elif request.path.startswith("/admin/"):
                return redirect(url_desbloquear(request))
        return self.get_response(request)


def contexto(request):
    """{{ financeiro_liberado }} em todos os templates."""
    return {"financeiro_liberado": liberado(request) if hasattr(request, "session") else False}
