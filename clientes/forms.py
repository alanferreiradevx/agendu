from django import forms

from core.campos import DATA, VariasImagensField

from .models import Cliente, Evolucao, Ficha, Foto


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nome", "telefone", "email", "nascimento", "cpf", "profissao", "como_conheceu",
            "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "observacoes", "ativo",
        ]
        widgets = {
            "nascimento": DATA,
            "telefone": forms.TextInput(attrs={"data-mascara": "telefone", "inputmode": "tel", "placeholder": "(11) 91234-5678"}),
            "cpf": forms.TextInput(attrs={"data-mascara": "cpf", "inputmode": "numeric", "placeholder": "000.000.000-00"}),
            "cep": forms.TextInput(attrs={"data-mascara": "cep", "data-cep": "1", "inputmode": "numeric", "placeholder": "00000-000"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {"cep": "Digite o CEP: rua, bairro, cidade e UF se preenchem sozinhos."}

    def clean_nome(self):
        nome = " ".join(self.cleaned_data["nome"].split())
        minusculas = {"da", "de", "do", "das", "dos", "e"}
        return " ".join(p if p.lower() in minusculas and i else p.capitalize()
                        for i, p in enumerate(nome.lower().split()))


class FichaForm(forms.ModelForm):
    class Meta:
        model = Ficha
        exclude = ["cliente", "atualizada_em"]
        widgets = {campo: forms.Textarea(attrs={"rows": 2}) for campo in (
            "queixa_principal", "alergias", "medicamentos", "cirurgias", "procedimentos_anteriores",
            "rotina_cuidados", "observacoes",
        )}


class EvolucaoForm(forms.ModelForm):
    fotos = VariasImagensField(label="Fotos (opcional)")
    momento = forms.ChoiceField(label="As fotos são", choices=Foto.MOMENTO, initial="depois")

    class Meta:
        model = Evolucao
        fields = ["data", "texto", "medidas"]
        widgets = {"data": DATA, "texto": forms.Textarea(attrs={"rows": 4})}


class FotosForm(forms.Form):
    fotos = VariasImagensField(label="Fotos", required=True)
    momento = forms.ChoiceField(label="Momento", choices=Foto.MOMENTO, initial="antes")
    regiao = forms.CharField(label="Região", max_length=60, required=False,
                             widget=forms.TextInput(attrs={"placeholder": "rosto, abdômen..."}))
    data = forms.DateField(label="Data", widget=DATA)
    legenda = forms.CharField(max_length=200, required=False)
