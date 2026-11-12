"""
Troca o e-mail e a senha de entrada do Agendu (pergunta tudo na tela).

No servidor:
    ssh -t root@187.41.119.140 agendu-manage trocar_acesso

A senha não aparece enquanto você digita. Também libera o bloqueio de
"aguarde 15 minutos" das tentativas de login.
"""

import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = "Troca o e-mail e a senha de entrada (pergunta na tela)."

    def handle(self, *args, **opcoes):
        User = get_user_model()
        usuarios = list(User.objects.filter(is_active=True).order_by("pk"))
        if not usuarios:
            raise CommandError("Nenhum usuário. Crie com: agendu-manage createsuperuser")
        usuario = usuarios[0]
        if len(usuarios) > 1:
            self.stdout.write("Usuários:")
            for i, u in enumerate(usuarios, 1):
                self.stdout.write(f"  {i}. {u.email or '(sem e-mail)'}")
            escolha = input("Qual número? ").strip()
            try:
                usuario = usuarios[int(escolha) - 1]
            except (ValueError, IndexError):
                raise CommandError("Número inválido.")

        self.stdout.write(f"E-mail atual: {usuario.email or '(sem e-mail)'}")
        email = input("Novo e-mail (Enter para manter o atual): ").strip().lower() or usuario.email
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("E-mail inválido. Nada foi alterado.")
        if User.objects.filter(email__iexact=email).exclude(pk=usuario.pk).exists():
            raise CommandError("Esse e-mail já é de outro usuário. Nada foi alterado.")

        for _ in range(3):
            senha = getpass.getpass("Nova senha (não aparece ao digitar): ")
            if senha != getpass.getpass("Repita a nova senha: "):
                self.stderr.write("As duas senhas não são iguais. Tente de novo.")
                continue
            try:
                validate_password(senha, usuario)
            except ValidationError as e:
                self.stderr.write("Senha fraca: " + " ".join(e.messages))
                continue
            break
        else:
            raise CommandError("Senha não trocada. Nada foi alterado.")

        usuario.email = email
        usuario.set_password(senha)
        usuario.save()
        cache.clear()  # libera o "aguarde 15 minutos"
        self.stdout.write(self.style.SUCCESS(f"Pronto! Entre em https://agendu.ativix.co com {email} e a senha nova."))
