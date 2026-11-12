from django import forms


class VariasImagensInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class VariasImagensField(forms.ImageField):
    """Campo que aceita várias fotos de uma vez (devolve uma lista)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", VariasImagensInput(attrs={"accept": "image/*", "multiple": True}))
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError("Escolha pelo menos uma foto.")
            return []
        unica = super().clean
        if isinstance(data, (list, tuple)):
            return [unica(d, initial) for d in data]
        return [unica(data, initial)]


DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
HORA = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
DINHEIRO = forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"})
QUANTIDADE = forms.NumberInput(attrs={"step": "0.001", "inputmode": "decimal"})
