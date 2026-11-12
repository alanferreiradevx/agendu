from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from agenda.consultas import aniversariantes, retornos
from agenda.models import Agendamento
from estoque.models import Material
from financeiro.forms import FormasFormSet
from financeiro.models import Lancamento, resumo

from .forms import EstudioForm
from .models import Estudio


def painel(request):
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    agora = timezone.now()

    de_hoje = (Agendamento.objects.filter(inicio__date=hoje).exclude(status=Agendamento.CANCELADO)
               .select_related("cliente", "procedimento").order_by("inicio"))
    amanha = (Agendamento.objects.filter(inicio__date=hoje + timedelta(days=1), status__in=Agendamento.EM_ABERTO)
              .select_related("cliente", "procedimento").order_by("inicio"))
    pendentes = (Agendamento.objects.filter(status__in=Agendamento.EM_ABERTO, fim__lt=agora, inicio__date__lt=hoje)
                 .select_related("cliente", "procedimento").order_by("-inicio")[:10])

    mes = resumo(Lancamento.objects.filter(data__gte=inicio_mes, data__lte=hoje))
    concluidos_mes = Agendamento.objects.filter(status=Agendamento.CONCLUIDO, inicio__date__gte=inicio_mes,
                                                inicio__date__lte=hoje).count()
    faltas_mes = Agendamento.objects.filter(status=Agendamento.FALTOU, inicio__date__gte=inicio_mes).count()

    materiais = Material.objects.filter(ativo=True)
    alerta_estoque = [m for m in materiais if m.abaixo_do_minimo or m.vencido or m.vencendo]

    estudio = Estudio.atual()
    return render(request, "core/painel.html", {
        "hoje": hoje, "de_hoje": de_hoje, "amanha": amanha, "pendentes": pendentes,
        "mes": mes, "concluidos_mes": concluidos_mes, "faltas_mes": faltas_mes,
        "ticket_medio": (mes["entradas"] / concluidos_mes) if concluidos_mes else 0,
        "alerta_estoque": alerta_estoque,
        "retornos": retornos(), "aniversariantes": [c for c in aniversariantes() if c.nascimento.day >= hoje.day][:8],
        "estudio": estudio,
    })


def configuracoes(request):
    estudio = Estudio.atual()
    form = EstudioForm(request.POST or None, request.FILES or None, instance=estudio, prefix="estudio")
    formas = FormasFormSet(request.POST or None, prefix="formas")
    if request.method == "POST" and form.is_valid() and formas.is_valid():
        form.save()
        formas.save()
        messages.success(request, "Configurações salvas.")
        return redirect("configuracoes")
    return render(request, "core/configuracoes.html", {"form": form, "formas": formas})


def logo(request):
    estudio = Estudio.atual()
    if not estudio.logo:
        raise Http404
    return FileResponse(estudio.logo.open("rb"))


def busca(request):
    """Busca rápida da barra do topo: vai direto para a cliente se só uma bater."""
    from clientes.models import Cliente

    termo = request.GET.get("q", "").strip()
    if not termo:
        return redirect("clientes:lista")
    achados = Cliente.objects.filter(Q(nome__icontains=termo) | Q(telefone__icontains=termo))
    if achados.count() == 1:
        return redirect("clientes:detalhe", achados.first().pk)
    return redirect(f"/clientes/?q={termo}")
