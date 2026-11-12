from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache

from .models import Estudio
from .utils import ip_do_cliente


class LoginForm(AuthenticationForm):
    """Login com bloqueio: 5 senhas erradas seguidas do mesmo IP = 15 minutos esperando."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuário ou senha incorretos.",
        "bloqueado": "Muitas tentativas erradas. Espere 15 minutos e tente de novo.",
    }

    def _chave(self):
        return "login-tentativas:" + ip_do_cliente(self.request) if self.request else "login-tentativas:?"

    def clean(self):
        chave = self._chave()
        if cache.get(chave, 0) >= settings.LOGIN_MAX_TENTATIVAS:
            raise forms.ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        try:
            dados = super().clean()
        except forms.ValidationError:
            cache.set(chave, cache.get(chave, 0) + 1, settings.LOGIN_BLOQUEIO_SEGUNDOS)
            raise
        cache.delete(chave)
        return dados


class EstudioForm(forms.ModelForm):
    class Meta:
        model = Estudio
        fields = [
            "nome", "profissional", "registro", "documento", "telefone", "endereco", "instagram", "logo",
            "hora_abre", "hora_fecha", "msg_lembrete", "msg_retorno", "msg_aniversario",
        ]
        widgets = {
            "hora_abre": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_fecha": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "msg_lembrete": forms.Textarea(attrs={"rows": 3}),
            "msg_retorno": forms.Textarea(attrs={"rows": 3}),
            "msg_aniversario": forms.Textarea(attrs={"rows": 2}),
        }


class CriarSenhaFinanceiroForm(forms.Form):
    senha = forms.CharField(label="Nova senha do financeiro", min_length=4, max_length=64,
                            widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                            help_text="Pelo menos 4 caracteres (pode ser só números). Diferente da senha de login.")
    confirmar = forms.CharField(label="Repita a senha", max_length=64,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean(self):
        dados = super().clean()
        if dados.get("senha") and dados.get("senha") != dados.get("confirmar"):
            self.add_error("confirmar", "As duas senhas não são iguais.")
        return dados


class SenhaFinanceiroForm(forms.Form):
    senha = forms.CharField(label="Senha do financeiro", max_length=64,
                            widget=forms.PasswordInput(attrs={"autocomplete": "off", "autofocus": True}))


class TrocarSenhaFinanceiroForm(CriarSenhaFinanceiroForm):
    atual = forms.CharField(label="Senha atual do financeiro", max_length=64,
                            widget=forms.PasswordInput(attrs={"autocomplete": "off"}))
    field_order = ["atual", "senha", "confirmar"]
