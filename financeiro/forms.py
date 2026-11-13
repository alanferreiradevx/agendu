from django import forms

from clientes.models import Cliente
from core.campos import DATA, DINHEIRO

from . import pagamento
from .models import FormaPagamento, Lancamento


class LancamentoForm(forms.ModelForm):
    class Meta:
        model = Lancamento
        fields = ["data", "descricao", "categoria", "valor", "forma", "parcelas", "cliente", "observacoes"]
        widgets = {"data": DATA, "valor": DINHEIRO}

    def __init__(self, *args, tipo, estudio, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.tipo = tipo
        self.instance.estudio = estudio
        entrada = tipo == Lancamento.ENTRADA
        self.fields["categoria"].choices = Lancamento.CATEGORIAS_ENTRADA if entrada else Lancamento.CATEGORIAS_SAIDA
        pagamento.preparar(self, estudio, vazio="Não informar")
        self.fields["forma"].required = False
        self.fields["cliente"].queryset = Cliente.objects.filter(estudio=estudio, ativo=True)
        self.fields["cliente"].required = False
        self.fields["valor"].min_value = 0.01
        if entrada:
            self.fields["parcelas"] = pagamento.campo_parcelas()
        else:
            del self.fields["parcelas"]
            del self.fields["cliente"]
            self.fields["forma"].help_text = "Opcional. Despesa não desconta taxa."

    def clean(self):
        dados = super().clean()
        pagamento.ajustar_parcelas(self, dados)
        return dados

    def save(self, commit=True):
        lanc = super().save(commit=False)
        # Taxa só nas entradas (é o que a maquininha cobra de você ao receber).
        lanc.taxa = lanc.forma.taxa_sobre(lanc.valor) if (lanc.tipo == Lancamento.ENTRADA and lanc.forma) else 0
        if commit:
            lanc.save()
        return lanc


class BaseFormasFormSet(forms.BaseModelFormSet):
    """Nome de forma de pagamento não repete no espaço."""

    def clean(self):
        super().clean()
        nomes = [f.cleaned_data.get("nome", "").strip().lower() for f in self.forms
                 if f.has_changed() or f.instance.pk if hasattr(f, "cleaned_data")]
        nomes = [n for n in nomes if n]
        if len(nomes) != len(set(nomes)):
            raise forms.ValidationError("Há duas formas de pagamento com o mesmo nome.")


FormasFormSet = forms.modelformset_factory(
    FormaPagamento, formset=BaseFormasFormSet, fields=["nome", "taxa_percentual", "parcelavel", "ordem", "ativo"], extra=1,
    widgets={"taxa_percentual": forms.NumberInput(attrs={"step": "0.01", "min": "0"})},
)
