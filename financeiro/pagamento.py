"""
Campos de "como paga": as formas aparecem como botões (PIX, Dinheiro, Cartão...) e,
se a forma for parcelada, aparece "em quantas vezes" (2x a 12x).
Usado no agendamento (como vai pagar), na conclusão (como pagou), nos pacotes e no caixa.
"""

from django import forms

from .models import FormaPagamento

PARCELAS = [(n, f"{n}x") for n in range(2, 13)]


def campo_parcelas(label="Parcelado em"):
    return forms.TypedChoiceField(label=label, choices=PARCELAS, coerce=int, required=False, empty_value=1)


def preparar(form, estudio, forma="forma", vazio=None):
    """Troca a lista suspensa por botões (só as formas do espaço) e guarda quais são parceladas (para o JS)."""
    campo = form.fields[forma]
    campo.widget = forms.RadioSelect()
    campo.empty_label = vazio  # None: sem a opção vazia
    campo.queryset = FormaPagamento.objects.filter(estudio=estudio, ativo=True)
    form.parcelaveis = ",".join(str(pk) for pk in campo.queryset.filter(parcelavel=True).values_list("pk", flat=True))


def ajustar_parcelas(form, dados, forma="forma", parcelas="parcelas"):
    """Forma à vista = 1 parcela; forma parcelada precisa de 2x ou mais."""
    if parcelas not in form.fields:
        return
    escolhida = dados.get(forma)
    if not escolhida or not escolhida.parcelavel:
        dados[parcelas] = 1
    elif (dados.get(parcelas) or 1) < 2:
        form.add_error(parcelas, "Escolha em quantas vezes.")
