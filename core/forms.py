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
