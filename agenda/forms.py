from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from clientes.models import Cliente, Foto
from core.campos import DATA, DINHEIRO, HORA, QUANTIDADE, VariasImagensField
from estoque.models import Material
from financeiro.models import FormaPagamento

from .models import Agendamento, Pacote, Procedimento, ProcedimentoMaterial


def formas_ativas():
    return FormaPagamento.objects.filter(ativo=True)


class ProcedimentoForm(forms.ModelForm):
    class Meta:
        model = Procedimento
        fields = ["nome", "duracao_min", "preco", "retorno_dias", "cor", "descricao", "cuidados_pos", "ativo"]
        widgets = {
            "preco": DINHEIRO,
            "descricao": forms.Textarea(attrs={"rows": 2}),
            "cuidados_pos": forms.Textarea(attrs={"rows": 3}),
        }


class ProcedimentoMaterialForm(forms.ModelForm):
    class Meta:
        model = ProcedimentoMaterial
        fields = ["material", "quantidade"]
        widgets = {"quantidade": QUANTIDADE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["material"].queryset = Material.objects.filter(ativo=True)
        self.fields["material"].label_from_instance = lambda m: f"{m.nome} ({m.get_unidade_display()})"


MateriaisFormSet = forms.inlineformset_factory(
    Procedimento, ProcedimentoMaterial, form=ProcedimentoMaterialForm, extra=3, can_delete=True,
)


class AgendamentoForm(forms.ModelForm):
    """Data + hora + duração no lugar de início/fim (mais fácil de preencher no celular)."""

    data = forms.DateField(widget=DATA)
    hora = forms.TimeField(widget=HORA)
    duracao = forms.IntegerField(label="Duração (min)", min_value=5, max_value=720)

    class Meta:
        model = Agendamento
        fields = ["cliente", "procedimento", "valor", "pacote", "observacoes"]
        widgets = {"valor": DINHEIRO, "observacoes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True)
        procs = Procedimento.objects.filter(ativo=True)
        if self.instance.pk:  # procedimento desativado continua aparecendo no agendamento antigo
            procs = procs | Procedimento.objects.filter(pk=self.instance.procedimento_id)
        self.fields["procedimento"].queryset = procs
        # dados para o JavaScript preencher duração e valor ao escolher o procedimento
        self.fields["procedimento"].widget.attrs["data-procedimentos"] = "|".join(
            f"{p.pk}:{p.duracao_min}:{p.preco}" for p in procs)
        pacotes = Pacote.objects.select_related("cliente", "procedimento")
        self.fields["pacote"].queryset = pacotes
        self.fields["pacote"].label_from_instance = (
            lambda p: f"{p.cliente} - {p.sessoes}x {p.procedimento} ({p.restantes} restante(s))")
        self.fields["pacote"].required = False
        if self.instance.pk:
            inicio = timezone.localtime(self.instance.inicio)
            self.initial.update(data=inicio.date(), hora=inicio.time().replace(second=0, microsecond=0),
                                duracao=self.instance.duracao_min)

    def clean(self):
        dados = super().clean()
        data, hora, duracao = dados.get("data"), dados.get("hora"), dados.get("duracao")
        if data and hora and duracao:
            inicio = timezone.make_aware(datetime.combine(data, hora))
            self.instance.inicio = inicio
            self.instance.fim = inicio + timedelta(minutes=duracao)
        return dados


class ConcluirForm(forms.Form):
    usar_pacote = forms.ModelChoiceField(label="Usar sessão do pacote", queryset=Pacote.objects.none(), required=False,
                                         empty_label="Não, pagamento normal")
    valor = forms.DecimalField(label="Valor recebido", max_digits=10, decimal_places=2, min_value=0, widget=DINHEIRO,
                               required=False)
    forma = forms.ModelChoiceField(label="Forma de pagamento", queryset=FormaPagamento.objects.none(), required=False)
    parcelas = forms.IntegerField(min_value=1, max_value=24, initial=1, required=False)
    evolucao = forms.CharField(label="Evolução / como foi a sessão", widget=forms.Textarea(attrs={"rows": 3}),
                               required=False)
    medidas = forms.CharField(max_length=250, required=False, widget=forms.TextInput(attrs={"placeholder": "opcional"}))
    fotos = VariasImagensField(label="Fotos da sessão (opcional)")
    momento_fotos = forms.ChoiceField(label="As fotos são", choices=Foto.MOMENTO, initial="depois")

    def __init__(self, *args, agendamento, **kwargs):
        super().__init__(*args, **kwargs)
        self.agendamento = agendamento
        pacotes = Pacote.com_saldo(agendamento.cliente, agendamento.procedimento)
        self.fields["usar_pacote"].queryset = Pacote.objects.filter(pk__in=[p.pk for p in pacotes])
        self.fields["usar_pacote"].label_from_instance = (
            lambda p: f"{p.sessoes}x {p.procedimento} - {p.restantes} restante(s)")
        if agendamento.pacote_id and agendamento.pacote_id in [p.pk for p in pacotes]:
            self.initial["usar_pacote"] = agendamento.pacote_id
        elif len(pacotes) == 1:
            self.initial["usar_pacote"] = pacotes[0].pk
        self.fields["forma"].queryset = formas_ativas()
        self.initial.setdefault("valor", agendamento.valor)

    def clean(self):
        dados = super().clean()
        if not dados.get("usar_pacote") and (dados.get("valor") or 0) > 0 and not dados.get("forma"):
            self.add_error("forma", "Escolha como a cliente pagou.")
        return dados


class PacoteForm(forms.ModelForm):
    valor_pago = forms.DecimalField(label="Pago agora", max_digits=10, decimal_places=2, min_value=0, required=False,
                                    widget=DINHEIRO, help_text="Deixe o valor total se pagou tudo; 0 se vai pagar depois.")
    forma = forms.ModelChoiceField(label="Forma de pagamento", queryset=FormaPagamento.objects.none(), required=False)
    parcelas = forms.IntegerField(min_value=1, max_value=24, initial=1, required=False)

    class Meta:
        model = Pacote
        fields = ["cliente", "procedimento", "sessoes", "valor", "data_compra", "validade", "observacoes"]
        widgets = {"valor": DINHEIRO, "data_compra": DATA, "validade": DATA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True)
        self.fields["procedimento"].queryset = Procedimento.objects.filter(ativo=True)
        self.fields["forma"].queryset = formas_ativas()

    def clean(self):
        dados = super().clean()
        pago, valor = dados.get("valor_pago"), dados.get("valor")
        if pago and valor is not None and pago > valor:
            self.add_error("valor_pago", "O valor pago não pode passar do valor do pacote.")
        if pago and pago > 0 and not dados.get("forma"):
            self.add_error("forma", "Escolha como a cliente pagou.")
        return dados


class ReceberForm(forms.Form):
    valor = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01, widget=DINHEIRO)
    forma = forms.ModelChoiceField(label="Forma de pagamento", queryset=FormaPagamento.objects.none())
    parcelas = forms.IntegerField(min_value=1, max_value=24, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["forma"].queryset = formas_ativas()
