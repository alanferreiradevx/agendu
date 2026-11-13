"""
Separação entre espaços: cada pessoa só enxerga os dados do SEU espaço.

O middleware coloca `request.estudio` em toda página (o espaço de quem está
logado) e barra quem estiver bloqueado ou com o acesso vencido. As views
filtram tudo por `request.estudio`: nunca busque um dado sem esse filtro.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import estudio_do_usuario


class EspacoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.estudio = None
        usuario = request.user
        if usuario.is_authenticated:
            estudio = estudio_do_usuario(usuario)
            motivo = None
            if estudio is None:
                motivo = "Este login não tem um espaço no Agendu."
            elif not usuario.is_superuser and not estudio.ativo:
                motivo = "Seu acesso ao Agendu está bloqueado. Fale com o suporte do Agendu."
            elif not usuario.is_superuser and estudio.vencido:
                motivo = (f"Seu acesso ao Agendu venceu em {estudio.valido_ate:%d/%m/%Y}. "
                          "Fale com o suporte do Agendu para renovar.")
            if motivo:
                logout(request)
                messages.error(request, motivo)
                return redirect("login")
            request.estudio = estudio
        return self.get_response(request)


def master_obrigatorio(view):
    """Área de acessos: só o master (superusuário)."""

    @wraps(view)
    def interna(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return interna


def contexto(request):
    """{{ estudio }} em todos os templates (o espaço de quem está logado)."""
    return {"estudio_atual": getattr(request, "estudio", None)}
