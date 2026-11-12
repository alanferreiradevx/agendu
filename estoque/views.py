from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.financeiro import liberado
from core.utils import centavos
from financeiro.models import Lancamento

from .forms import AjusteForm, EntradaForm, MaterialForm
from .models import Material, Movimento, movimentar


def lista(request):
    materiais = list(Material.objects.filter(ativo=True))
    alerta = request.GET.get("filtro") == "alerta"
    if alerta:
        materiais = [m for m in materiais if m.abaixo_do_minimo or m.vencido or m.vencendo]
    total = sum((m.valor_em_estoque for m in materiais), Decimal(0))
    inativos = Material.objects.filter(ativo=False).count()
    return render(request, "estoque/lista.html", {"materiais": materiais, "total": total, "alerta": alerta,
                                                  "inativos": inativos})


def editar(request, pk=None):
    material = get_object_or_404(Material, pk=pk) if pk else None
    aberto = liberado(request)
    form = MaterialForm(request.POST or None, instance=material, financeiro=aberto)
    entrada = EntradaForm(request.POST or None, prefix="entrada", financeiro=aberto) if not pk else None
    if request.method == "POST" and form.is_valid() and (entrada is None or not entrada.has_changed() or entrada.is_valid()):
        with transaction.atomic():
            material = form.save()
            if entrada is not None and entrada.has_changed() and entrada.cleaned_data.get("quantidade"):
                _registrar_entrada(material, entrada.cleaned_data)
        messages.success(request, f"{material} salvo.")
        return redirect("estoque:detalhe", material.pk)
    return render(request, "estoque/form.html", {"form": form, "entrada": entrada, "material": material})


def _registrar_entrada(material, d):
    qtd, total = d["quantidade"], d.get("valor_total") or Decimal(0)
    custo = (total / qtd) if total else None
    movimentar(material, qtd, "entrada", custo_unitario=custo, descricao=d.get("descricao") or "Compra")
    if d.get("validade"):
        material.validade = d["validade"]
        material.save(update_fields=["validade"])
    if total and d.get("lancar_despesa"):
        Lancamento.objects.create(
            tipo=Lancamento.SAIDA, categoria="material", valor=centavos(total), forma=d.get("forma"),
            descricao=f"Compra: {material} ({qtd:g} {material.unidade})", data=timezone.localdate(),
            observacoes=d.get("descricao") or "",
        )


def detalhe(request, pk):
    material = get_object_or_404(Material, pk=pk)
    aberto = liberado(request)
    entrada = EntradaForm(prefix="entrada", financeiro=aberto)
    ajuste = AjusteForm(prefix="ajuste", initial={"saldo_real": material.quantidade})
    if request.method == "POST":
        if "entrada-quantidade" in request.POST:
            entrada = EntradaForm(request.POST, prefix="entrada", financeiro=aberto)
            if entrada.is_valid():
                with transaction.atomic():
                    _registrar_entrada(material, entrada.cleaned_data)
                messages.success(request, "Entrada registrada.")
                return redirect("estoque:detalhe", pk)
        else:
            ajuste = AjusteForm(request.POST, prefix="ajuste")
            if ajuste.is_valid():
                diferenca = ajuste.cleaned_data["saldo_real"] - material.quantidade
                if diferenca:
                    movimentar(material, diferenca, "ajuste", descricao=ajuste.cleaned_data["motivo"])
                    messages.success(request, "Estoque ajustado.")
                return redirect("estoque:detalhe", pk)
    return render(request, "estoque/detalhe.html", {
        "material": material, "entrada": entrada, "ajuste": ajuste,
        "movimentos": Movimento.objects.filter(material=material).select_related("agendamento__cliente")[:100],
        "usos": material.usos.select_related("procedimento"),
    })
