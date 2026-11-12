"""
Login pelo e-mail (no lugar do nome de usuário).

O formulário de entrada continua mandando o campo "username"; aqui ele é tratado
como e-mail, sem diferença entre maiúsculas e minúsculas.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip()
        if not email or password is None:
            return None
        User = get_user_model()
        usuarios = list(User.objects.filter(email__iexact=email)[:2])
        if len(usuarios) != 1:
            # Nenhum (ou e-mail repetido): gasta o mesmo tempo de uma senha conferida,
            # para não dar pista de quais e-mails existem.
            User().set_password(password)
            return None
        usuario = usuarios[0]
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
