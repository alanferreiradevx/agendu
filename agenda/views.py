from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.financeiro import financeiro_obrigatorio, liberado, url_desbloquear
from core.models import Estudio
from core.utils import formatar_mensagem

from . import servicos
from .forms import AgendamentoForm, ConcluirForm, MateriaisFormSet, PacoteForm, ProcedimentoForm, ReceberForm
from .models import Agendamento, Pacote, Procedimento

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _data(texto, padrao):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return padrao


def semana(request):
    hoje = timezone.localdate()
    dia = _data(request.GET.get("data"), hoje)
    segunda = dia - timedelta(days=dia.weekday())
    dias = [segunda + timedelta(days=i) for i in range(7)]
    inicio = timezone.make_aware(datetime.combine(segunda, time.min))
    ags = (Agendamento.objects.filter(inicio__gte=inicio, inicio__lt=inicio + timedelta(days=7))
           .select_related("cliente", "procedimento").order_by("inicio"))
    if request.GET.get("cancelados") != "1":
        ags = ags.exclude(status=Agendamento.CANCELADO)
    por_dia = {d: [] for d in dias}
    for a in ags:
        por_dia[timezone.localdate(a.inicio)].append(a)
    colunas = [{"data": d, "nome": DIAS[i], "itens": por_dia[d], "hoje": d == hoje} for i, d in enumerate(dias)]
    return render(request, "agenda/semana.html", {
        "colunas": colunas, "segunda": segunda, "domingo": dias[-1],
        "anterior": segunda - timedelta(days=7), "proxima": segunda + timedelta(days=7), "hoje": hoje,
    })


def editar(request, pk=None):
    ag = get_object_or_404(Agendamento, pk=pk) if pk else Agendamento()
    if ag.status == Agendamento.CONCLUIDO:
        messages.error(request, "Atendimento concluído não se edita. Desfaça a conclusão antes, se precisar.")
        return redirect("agenda:detalhe", ag.pk)
    inicial = {}
    if not pk:
        estudio = Estudio.atual()
        inicial["data"] = _data(request.GET.get("data"), timezone.localdate())
        inicial["hora"] = request.GET.get("hora") or estudio.hora_abre.strftime("%H:%M")
        inicial["duracao"] = 60
        if request.GET.get("cliente"):
            inicial["cliente"] = request.GET["cliente"]
        if request.GET.get("procedimento"):
            proc = Procedimento.objects.filter(pk=request.GET["procedimento"]).first()
            if proc:
                inicial.update(procedimento=proc.pk, duracao=proc.duracao_min, valor=proc.preco)
        if request.GET.get("pacote"):
            pac = Pacote.objects.filter(pk=request.GET["pacote"]).first()
            if pac:
                inicial.update(pacote=pac.pk, cliente=pac.cliente_id, procedimento=pac.procedimento_id,
                               duracao=pac.procedimento.duracao_min, valor=0)
    form = AgendamentoForm(request.POST or None, instance=ag if pk else None, initial=inicial,
                           financeiro=liberado(request))
    if request.method == "POST" and form.is_valid():
        ag = form.save()
        messages.success(request, f"Agendado: {ag.cliente} em {timezone.localtime(ag.inicio):%d/%m às %H:%M}.")
        return redirect("agenda:detalhe", ag.pk)
    return render(request, "agenda/form.html", {"form": form, "ag": ag if pk else None})


def detalhe(request, pk):
    ag = get_object_or_404(Agendamento.objects.select_related("cliente", "procedimento", "pacote"), pk=pk)
    estudio = Estudio.atual()
    inicio = timezone.localtime(ag.inicio)
    hoje = timezone.localdate()
    if inicio.date() == hoje:
        quando = "hoje"
    elif inicio.date() == hoje + timedelta(days=1):
        quando = "amanhã"
    else:
        quando = f"no dia {inicio:%d/%m} ({DIAS[inicio.weekday()].lower()})"
    lembrete = formatar_mensagem(estudio.msg_lembrete, nome=ag.cliente.primeiro_nome, procedimento=ag.procedimento.nome,
                                 quando=quando, hora=f"{inicio:%H:%M}", data=f"{inicio:%d/%m}", estudio=estudio.nome)
    cuidados = ""
    if ag.procedimento.cuidados_pos:
        cuidados = (f"Olá, {ag.cliente.primeiro_nome}! Seguem os cuidados após {ag.procedimento.nome}:\n\n"
                    f"{ag.procedimento.cuidados_pos}\n\n{estudio.nome}")
    ficha = getattr(ag.cliente, "ficha", None)
    return render(request, "agenda/detalhe.html", {
        "ag": ag, "whatsapp_lembrete": ag.cliente.whatsapp(lembrete),
        "whatsapp_cuidados": ag.cliente.whatsapp(cuidados) if cuidados else "",
        "atencao": ficha.pontos_de_atencao() if ficha else [],
        "materiais": ag.procedimento.materiais.select_related("material"),
        "movimentos": ag.movimentos.select_related("material"),
        "lancamentos": ag.lancamentos.select_related("forma"),
    })


@require_POST
def mudar_status(request, pk, status):
    ag = get_object_or_404(Agendamento, pk=pk)
    permitidos = {Agendamento.CONFIRMADO, Agendamento.FALTOU, Agendamento.CANCELADO, Agendamento.AGENDADO}
    if status not in permitidos or ag.status == Agendamento.CONCLUIDO:
        messages.error(request, "Mudança não permitida.")
    else:
        if status in Agendamento.EM_ABERTO and ag.conflitos().exists():
            messages.error(request, "Esse horário já foi ocupado por outro atendimento.")
            return redirect("agenda:detalhe", pk)
        ag.status = status
        ag.save(update_fields=["status"])
        messages.success(request, f"Marcado como {ag.get_status_display().lower()}.")
    return redirect("agenda:detalhe", pk)


def concluir(request, pk):
    ag = get_object_or_404(Agendamento.objects.select_related("cliente", "procedimento"), pk=pk)
    if not ag.em_aberto and ag.status != Agendamento.FALTOU:
        messages.error(request, "Este atendimento não pode ser concluído.")
        return redirect("agenda:detalhe", pk)
    form = ConcluirForm(request.POST or None, request.FILES or None, agendamento=ag, financeiro=liberado(request))
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            servicos.concluir(ag, forma=d["forma"], valor=d.get("valor"), parcelas=d.get("parcelas") or 1,
                              usar_pacote=d["usar_pacote"], evolucao=d["evolucao"], medidas=d["medidas"],
                              fotos=d["fotos"], momento_fotos=d["momento_fotos"])
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, "Atendimento concluído: estoque e caixa atualizados.")
            return redirect("agenda:detalhe", pk)
    materiais = ag.procedimento.materiais.select_related("material")
    return render(request, "agenda/concluir.html", {"ag": ag, "form": form, "materiais": materiais})


@require_POST
@financeiro_obrigatorio
def desfazer(request, pk):
    ag = get_object_or_404(Agendamento, pk=pk)
    try:
        servicos.desfazer_conclusao(ag)
        messages.success(request, "Conclusão desfeita: materiais voltaram ao estoque e a entrada saiu do caixa.")
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("agenda:detalhe", pk)


@require_POST
def apagar(request, pk):
    ag = get_object_or_404(Agendamento, pk=pk)
    if ag.status == Agendamento.CONCLUIDO:
        messages.error(request, "Atendimento concluído não se apaga (está no caixa e no estoque). Desfaça antes.")
        return redirect("agenda:detalhe", pk)
    dia = timezone.localdate(ag.inicio)
    ag.delete()
    messages.success(request, "Agendamento apagado.")
    return redirect(f"/agenda/?data={dia:%Y-%m-%d}")


# ----- Procedimentos ---------------------------------------------------------

def procedimentos(request):
    procs = Procedimento.objects.prefetch_related("materiais__material")
    return render(request, "agenda/procedimentos.html", {"procedimentos": procs})


def procedimento_editar(request, pk=None):
    proc = get_object_or_404(Procedimento, pk=pk) if pk else Procedimento()
    form = ProcedimentoForm(request.POST or None, instance=proc, financeiro=liberado(request))
    materiais = MateriaisFormSet(request.POST or None, instance=proc, prefix="mat")
    if request.method == "POST" and form.is_valid() and materiais.is_valid():
        with transaction.atomic():
            proc = form.save()
            materiais.instance = proc
            materiais.save()
        messages.success(request, f"Procedimento {proc} salvo.")
        return redirect("agenda:procedimentos")
    return render(request, "agenda/procedimento_form.html", {"form": form, "materiais": materiais, "proc": proc if pk else None})


# ----- Pacotes ---------------------------------------------------------------

def pacotes(request):
    todos = Pacote.objects.select_related("cliente", "procedimento").prefetch_related("lancamentos", "agendamentos")
    ativos = [p for p in todos if p.restantes > 0 and not p.vencido]
    encerrados = [p for p in todos if p not in ativos]
    return render(request, "agenda/pacotes.html", {"ativos": ativos, "encerrados": encerrados[:50]})


@financeiro_obrigatorio
def pacote_novo(request):
    inicial = {}
    if request.GET.get("cliente"):
        inicial["cliente"] = request.GET["cliente"]
    form = PacoteForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        pacote = servicos.vender_pacote(form.save(commit=False), forma=d["forma"],
                                        valor_pago=d["valor_pago"] if d["valor_pago"] is not None else d["valor"],
                                        parcelas=d["parcelas"])
        messages.success(request, f"Pacote vendido: {pacote}.")
        return redirect("agenda:pacote", pacote.pk)
    return render(request, "agenda/pacote_form.html", {"form": form})


def pacote(request, pk):
    p = get_object_or_404(Pacote.objects.select_related("cliente", "procedimento"), pk=pk)
    if request.method == "POST" and not liberado(request):
        return redirect(url_desbloquear(request))
    form = ReceberForm(request.POST or None, initial={"valor": p.a_receber})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        servicos.receber_pacote(p, valor=d["valor"], forma=d["forma"], parcelas=d["parcelas"])
        messages.success(request, "Pagamento registrado no caixa.")
        return redirect("agenda:pacote", pk)
    return render(request, "agenda/pacote.html", {
        "p": p, "form": form, "sessoes": p.agendamentos.select_related("procedimento").order_by("inicio"),
        "lancamentos": p.lancamentos.select_related("forma"),
    })

