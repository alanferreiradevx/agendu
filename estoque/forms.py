from django import forms

from agenda.forms import NomeUnicoNoEspacoMixin
from core.campos import DATA, DINHEIRO, QUANTIDADE
from financeiro.models import FormaPagamento

from .models import Material


class MaterialForm(NomeUnicoNoEspacoMixin, forms.ModelForm):
    class Meta:
        model = Material
        fields = ["nome", "unidade", "estoque_minimo", "custo_unitario", "validade", "fornecedor", "observacoes", "ativo"]
        widgets = {
            "estoque_minimo": QUANTIDADE,
            "custo_unitario": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
            "validade": DATA,
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, financeiro=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not financeiro:
            del self.fields["custo_unitario"]


class EntradaForm(forms.Form):
    """Compra: quanto chegou e quanto pagou no total. O custo por unidade é calculado."""

    quantidade = forms.DecimalField(label="Quantidade que chegou", max_digits=12, decimal_places=3, min_value=0.001,
                                    widget=QUANTIDADE)
    valor_total = forms.DecimalField(label="Valor pago (total)", max_digits=12, decimal_places=2, min_value=0,
                                     required=False, widget=DINHEIRO)
    validade = forms.DateField(label="Validade deste lote", required=False, widget=DATA)
    lancar_despesa = forms.BooleanField(label="Lançar como despesa no caixa", required=False, initial=True)
    forma = forms.ModelChoiceField(label="Pago com", queryset=FormaPagamento.objects.none(), required=False)
    descricao = forms.CharField(label="Observação", max_length=150, required=False,
                                widget=forms.TextInput(attrs={"placeholder": "fornecedor, nota..."}))

    def __init__(self, *args, estudio, financeiro=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["forma"].queryset = FormaPagamento.objects.filter(estudio=estudio, ativo=True)
        if not financeiro:  # trancado: registra só a quantidade (o custo médio não muda)
            for campo in ("valor_total", "lancar_despesa", "forma"):
                del self.fields[campo]


class AjusteForm(forms.Form):
    saldo_real = forms.DecimalField(label="Quantidade que você tem de verdade", max_digits=12, decimal_places=3,
                                    min_value=0, widget=QUANTIDADE)
    motivo = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "contagem, perda, venceu..."}))
