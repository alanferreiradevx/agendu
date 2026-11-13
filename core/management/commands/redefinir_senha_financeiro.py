"""
Esqueceu a senha do financeiro? No servidor:

    agendu-manage redefinir_senha_financeiro email@da.profissional

Apaga a senha daquele espaço; no próximo acesso ao Financeiro o sistema pede uma nova.
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import Estudio


class Command(BaseCommand):
    help = "Apaga a senha do financeiro de um espaço (pelo e-mail de login)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="e-mail de login da profissional")

    def handle(self, *args, **opcoes):
        estudio = Estudio.objects.filter(dono__email__iexact=opcoes["email"].strip()).first()
        if estudio is None:
            raise CommandError("Nenhum espaço com esse e-mail de login.")
        estudio.definir_senha_financeiro("")
        self.stdout.write(self.style.SUCCESS(f"Senha do financeiro de {estudio} apagada. Abra o Financeiro e crie uma nova."))
