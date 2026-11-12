"""
Armazenamento privado das fotos dos clientes (e da logo).

Fica fora da pasta pública: a foto só sai pela view `clientes:foto`, que exige
login. Assim ninguém abre uma foto pelo endereço sem estar logado (LGPD).
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ArmazenamentoPrivado(FileSystemStorage):
    # Lê a pasta da configuração na hora (os testes trocam por uma pasta temporária).
    @property
    def base_location(self):
        return settings.PRIVADO_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


armazenamento_privado = ArmazenamentoPrivado()


def storage_privado():
    """Usado como callable nos campos de arquivo, para não gravar o caminho nas migrations."""
    return armazenamento_privado
