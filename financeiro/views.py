import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from agenda.models import Agendamento
from core.financeiro import financeiro_obrigatorio

from .forms import FormasFormSet, LancamentoForm
from .models import Lancamento, resumo

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def _mes(request):
    """?mes=2026-11 -> (primeiro dia, último dia). Padrão: mês atual."""
    hoje = timezone.localdate()
    try:
        ano, mes = (int(x) for x in request.GET.get("mes", "").split("-"))
        inicio = date(ano, mes, 1)
    except ValueError:
        inicio = hoje.replace(day=1)
    proximo = date(inicio.year + inicio.month // 12, inicio.month % 12 + 1, 1)
    return inicio, proximo


def _navegacao(inicio, proximo):
    anterior = date(inicio.year - (inicio.month == 1), (inicio.month - 2) % 12 + 1, 1)
    return {"nome_mes": f"{MESES[inicio.month - 1]} de {inicio.year}", "mes_codigo": f"{inicio:%Y-%m}",
            "mes_anterior": f"{anterior:%Y-%m}", "mes_proximo": f"{proximo:%Y-%m}"}


@financeiro_obrigatorio
def caixa(request):
    inicio, proximo = _mes(request)
    qs = Lancamento.objects.filter(data__gte=inicio, data__lt=proximo).select_related("forma", "cliente")
    tipo = request.GET.get("tipo")
    lista = qs.filter(tipo=tipo) if tipo in (Lancamento.ENTRADA, Lancamento.SAIDA) else qs
    if request.GET.get("csv"):
        return _csv(lista, inicio)
    por_categoria = defaultdict(Decimal)
    for l in qs.filter(tipo=Lancamento.SAIDA):
        por_categoria[l.get_categoria_display()] += l.valor
    return render(request, "financeiro/caixa.html", {
        "lancamentos": lista, "r": resumo(qs), "tipo": tipo,
        "despesas_por_categoria": sorted(por_categoria.items(), key=lambda x: -x[1]),
        **_navegacao(inicio, proximo),
    })


def _csv(qs, inicio):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="caixa-{inicio:%Y-%m}.csv"'
    resposta.write("﻿")  # BOM: o Excel abre com acentos certos
    w = csv.writer(resposta, delimiter=";")
    w.writerow(["Data", "Tipo", "Categoria", "Descrição", "Cliente", "Forma", "Parcelas", "Valor", "Taxa", "Líquido"])
    num = lambda v: f"{v:.2f}".replace(".", ",")  # noqa: E731
    for l in qs:
        w.writerow([f"{l.data:%d/%m/%Y}", l.get_tipo_display(), l.get_categoria_display(), l.descricao,
                    l.cliente or "", l.forma or "", l.parcelas, num(l.valor), num(l.taxa), num(l.liquido)])
    return resposta


@financeiro_obrigatorio
def lancamento(request, tipo, pk=None):
    lanc = get_object_or_404(Lancamento, pk=pk) if pk else None
    if lanc:
        tipo = lanc.tipo
    if tipo not in (Lancamento.ENTRADA, Lancamento.SAIDA):
        return redirect("financeiro:caixa")
    form = LancamentoForm(request.POST or None, instance=lanc, tipo=tipo,
                          initial={"data": timezone.localdate()} if not lanc else None)
    if request.method == "POST" and form.is_valid():
        l = form.save()
        messages.success(request, f"{l.get_tipo_display()} de {l.valor} salva.")
        return redirect(f"/caixa/?mes={l.data:%Y-%m}")
    return render(request, "financeiro/lancamento_form.html", {"form": form, "tipo": tipo, "lanc": lanc})


@require_POST
@financeiro_obrigatorio
def apagar(request, pk):
    lanc = get_object_or_404(Lancamento, pk=pk)
    if lanc.agendamento_id and lanc.categoria == "atendimento":
        messages.error(request, "Essa entrada é de um atendimento: use \"desfazer conclusão\" no atendimento.")
        return redirect("financeiro:caixa")
    mes = f"{lanc.data:%Y-%m}"
    lanc.delete()
    messages.success(request, "Lançamento apagado.")
    return redirect(f"/caixa/?mes={mes}")


@financeiro_obrigatorio
def faturamento(request):
    """Quanto cada procedimento rendeu no mês, quanto gastou de material e o que sobrou."""
    inicio, proximo = _mes(request)
    feitos = (Agendamento.objects.filter(status=Agendamento.CONCLUIDO, inicio__date__gte=inicio,
                                         inicio__date__lt=proximo)
              .select_related("procedimento", "pacote").prefetch_related("lancamentos"))
    linhas = {}
    for ag in feitos:
        l = linhas.setdefault(ag.procedimento_id, {"procedimento": ag.procedimento, "qtd": 0, "receita": Decimal(0),
                                                    "taxas": Decimal(0), "material": Decimal(0), "de_pacote": 0})
        l["qtd"] += 1
        l["material"] += ag.custo_material or 0
        if ag.pacote_id:
            l["receita"] += ag.pacote.valor_sessao  # sessão de pacote vale a fração do pacote
            l["de_pacote"] += 1
        else:
            for lanc in ag.lancamentos.all():
                l["receita"] += lanc.valor
                l["taxas"] += lanc.taxa
    for l in linhas.values():
        l["lucro"] = l["receita"] - l["taxas"] - l["material"]
        l["ticket"] = l["receita"] / l["qtd"] if l["qtd"] else 0
    linhas = sorted(linhas.values(), key=lambda l: -l["receita"])

    qs = Lancamento.objects.filter(data__gte=inicio, data__lt=proximo)
    formas = defaultdict(lambda: {"valor": Decimal(0), "taxa": Decimal(0), "qtd": 0})
    for l in qs.filter(tipo=Lancamento.ENTRADA).select_related("forma"):
        f = formas[str(l.forma or "Sem forma")]
        f["valor"] += l.valor
        f["taxa"] += l.taxa
        f["qtd"] += 1

    # últimos 6 meses para comparar
    historico = []
    ref = inicio
    for _ in range(6):
        prox = date(ref.year + ref.month // 12, ref.month % 12 + 1, 1)
        r = resumo(Lancamento.objects.filter(data__gte=ref, data__lt=prox))
        r["nome"] = f"{MESES[ref.month - 1][:3]}/{ref:%y}"
        r["atendimentos"] = Agendamento.objects.filter(status=Agendamento.CONCLUIDO, inicio__date__gte=ref,
                                                       inicio__date__lt=prox).count()
        historico.append(r)
        ref = date(ref.year - (ref.month == 1), (ref.month - 2) % 12 + 1, 1)
    maior = max((h["entradas"] for h in historico), default=0) or 1
    for h in historico:
        h["pct"] = int(100 * h["entradas"] / maior)

    return render(request, "financeiro/faturamento.html", {
        "linhas": linhas, "r": resumo(qs), "formas": sorted(formas.items(), key=lambda x: -x[1]["valor"]),
        "historico": historico[::-1], "atendimentos": len(feitos),
        "faltas": Agendamento.objects.filter(status=Agendamento.FALTOU, inicio__date__gte=inicio,
                                             inicio__date__lt=proximo).count(),
        **_navegacao(inicio, proximo),
    })


@financeiro_obrigatorio
def formas(request):
    """Formas de pagamento e a taxa de cada uma (maquininha, banco)."""
    conjunto = FormasFormSet(request.POST or None, prefix="formas")
    if request.method == "POST" and conjunto.is_valid():
        conjunto.save()
        messages.success(request, "Formas de pagamento salvas.")
        return redirect("financeiro:formas")
    return render(request, "financeiro/formas.html", {"formas": conjunto})
