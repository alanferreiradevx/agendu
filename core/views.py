from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from agenda.consultas import aniversariantes, retornos
from agenda.models import Agendamento, Pacote
from estoque.models import Material

from . import financeiro
from .forms import CriarSenhaFinanceiroForm, EstudioForm, SenhaFinanceiroForm, TrocarSenhaFinanceiroForm


def painel(request):
    """Agendamentos primeiro. Nada de valores aqui: dinheiro fica no Financeiro (com senha)."""
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    agora = timezone.now()

    e = request.estudio
    ags = Agendamento.objects.filter(estudio=e)
    de_hoje = (ags.filter(inicio__date=hoje).exclude(status=Agendamento.CANCELADO)
               .select_related("cliente", "procedimento").order_by("inicio"))
    proximos = (ags.filter(inicio__date__gt=hoje, inicio__date__lte=hoje + timedelta(days=6),
                                           status__in=Agendamento.EM_ABERTO)
                .select_related("cliente", "procedimento").order_by("inicio"))
    pendentes = (ags.filter(status__in=Agendamento.EM_ABERTO, fim__lt=agora, inicio__date__lt=hoje)
                 .select_related("cliente", "procedimento").order_by("-inicio")[:10])

    do_mes = ags.filter(inicio__date__gte=inicio_mes, inicio__date__lte=hoje)
    materiais = Material.objects.filter(estudio=e, ativo=True)
    return render(request, "core/painel.html", {
        "hoje": hoje, "amanha": hoje + timedelta(days=1), "de_hoje": de_hoje, "proximos": proximos,
        "pendentes": pendentes,
        "concluidos_mes": do_mes.filter(status=Agendamento.CONCLUIDO).count(),
        "faltas_mes": do_mes.filter(status=Agendamento.FALTOU).count(),
        "pacotes_ativos": sum(1 for p in Pacote.objects.filter(estudio=e) if p.restantes and not p.vencido),
        "alerta_estoque": [m for m in materiais if m.abaixo_do_minimo or m.vencido or m.vencendo],
        "retornos": retornos(e),
        "aniversariantes": [c for c in aniversariantes(e) if c.nascimento.day >= hoje.day][:8],
        "estudio": e,
    })


def configuracoes(request):
    estudio = request.estudio
    form = EstudioForm(request.POST or None, request.FILES or None, instance=estudio, prefix="estudio")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configurações salvas.")
        return redirect("configuracoes")
    return render(request, "core/configuracoes.html", {"form": form, "estudio": estudio})


# ----- Senha do financeiro ---------------------------------------------------

def _destino(request):
    proximo = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return proximo
    return "/caixa/"


def financeiro_entrar(request):
    """Pede a senha do financeiro (ou cria, no primeiro acesso)."""
    estudio = request.estudio
    destino = _destino(request)
    if financeiro.liberado(request):
        return redirect(destino)
    criar = not estudio.tem_senha_financeiro
    chave = f"financeiro-tentativas:{request.user.pk}"
    bloqueado = cache.get(chave, 0) >= settings.LOGIN_MAX_TENTATIVAS
    form = (CriarSenhaFinanceiroForm if criar else SenhaFinanceiroForm)(request.POST or None)
    if request.method == "POST" and not bloqueado and form.is_valid():
        if criar:
            estudio.definir_senha_financeiro(form.cleaned_data["senha"])
            messages.success(request, "Senha do financeiro criada. Guarde bem: ela é diferente da senha de login.")
        elif not estudio.confere_senha_financeiro(form.cleaned_data["senha"]):
            cache.set(chave, cache.get(chave, 0) + 1, settings.LOGIN_BLOQUEIO_SEGUNDOS)
            form.add_error("senha", "Senha incorreta.")
            bloqueado = cache.get(chave, 0) >= settings.LOGIN_MAX_TENTATIVAS
        if not form.errors:
            cache.delete(chave)
            financeiro.liberar(request)
            return redirect(destino)
    return render(request, "core/financeiro_entrar.html", {
        "form": form, "criar": criar, "bloqueado": bloqueado, "destino": destino,
        "minutos": settings.FINANCEIRO_MINUTOS,
    })


@require_POST
def financeiro_trancar(request):
    financeiro.trancar(request)
    messages.success(request, "Financeiro trancado: os valores sumiram da tela.")
    voltar = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}) or voltar.startswith(("/caixa", "/admin")):
        voltar = "/"
    return redirect(voltar)


@financeiro.financeiro_obrigatorio
def financeiro_senha(request):
    estudio = request.estudio
    form = TrocarSenhaFinanceiroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not estudio.confere_senha_financeiro(form.cleaned_data["atual"]):
            form.add_error("atual", "Senha atual incorreta.")
        else:
            estudio.definir_senha_financeiro(form.cleaned_data["senha"])
            messages.success(request, "Senha do financeiro trocada.")
            return redirect("configuracoes")
    return render(request, "core/financeiro_senha.html", {"form": form})


def logo(request):
    estudio = request.estudio
    if not estudio.logo:
        raise Http404
    return FileResponse(estudio.logo.open("rb"))


def busca(request):
    """Busca rápida da barra do topo: vai direto para a cliente se só uma bater."""
    from clientes.models import Cliente

    termo = request.GET.get("q", "").strip()
    if not termo:
        return redirect("clientes:lista")
    achados = Cliente.objects.filter(Q(nome__icontains=termo) | Q(telefone__icontains=termo), estudio=request.estudio)
    if achados.count() == 1:
        return redirect("clientes:detalhe", achados.first().pk)
    return redirect(f"/clientes/?q={termo}")
