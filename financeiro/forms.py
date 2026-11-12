from django import forms

from clientes.models import Cliente
from core.campos import DATA, DINHEIRO

from .models import FormaPagamento, Lancamento


class LancamentoForm(forms.ModelForm):
    class Meta:
        model = Lancamento
        fields = ["data", "descricao", "categoria", "valor", "forma", "parcelas", "cliente", "observacoes"]
        widgets = {"data": DATA, "valor": DINHEIRO}

    def __init__(self, *args, tipo, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.tipo = tipo
        entrada = tipo == Lancamento.ENTRADA
        self.fields["categoria"].choices = Lancamento.CATEGORIAS_ENTRADA if entrada else Lancamento.CATEGORIAS_SAIDA
        self.fields["forma"].queryset = FormaPagamento.objects.filter(ativo=True)
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True)
        self.fields["cliente"].required = False
        self.fields["valor"].min_value = 0.01
        if not entrada:
            del self.fields["parcelas"]
            del self.fields["cliente"]
            self.fields["forma"].help_text = "Opcional. Despesa não desconta taxa."

    def save(self, commit=True):
        lanc = super().save(commit=False)
        # Taxa só nas entradas (é o que a maquininha cobra de você ao receber).
        lanc.taxa = lanc.forma.taxa_sobre(lanc.valor) if (lanc.tipo == Lancamento.ENTRADA and lanc.forma) else 0
        if commit:
            lanc.save()
        return lanc


FormasFormSet = forms.modelformset_factory(
    FormaPagamento, fields=["nome", "taxa_percentual", "ordem", "ativo"], extra=1,
    widgets={"taxa_percentual": forms.NumberInput(attrs={"step": "0.01", "min": "0"})},
)
