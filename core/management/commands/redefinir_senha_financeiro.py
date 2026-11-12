"""
Esqueceu a senha do financeiro? No servidor:

    agendu-manage redefinir_senha_financeiro

Apaga a senha; no próximo acesso ao Financeiro o sistema pede para criar uma nova.
"""

from django.core.management.base import BaseCommand

from core.models import Estudio


class Command(BaseCommand):
    help = "Apaga a senha do financeiro (o sistema pede uma nova no próximo acesso)."

    def handle(self, *args, **opcoes):
        Estudio.atual().definir_senha_financeiro("")
        self.stdout.write(self.style.SUCCESS("Senha do financeiro apagada. Abra o Financeiro e crie uma nova."))
