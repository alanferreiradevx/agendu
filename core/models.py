from datetime import time

from django.db import models

from config.storage import storage_privado

LEMBRETE_PADRAO = (
    "Olá, {nome}! Passando para lembrar do seu horário de {procedimento} "
    "{quando} às {hora}. Qualquer imprevisto, me avise por aqui. Até lá! {estudio}"
)
RETORNO_PADRAO = (
    "Olá, {nome}! Já está na hora do seu retorno de {procedimento}. "
    "Vamos agendar? Me diga o melhor dia e horário. {estudio}"
)
ANIVERSARIO_PADRAO = "Feliz aniversário, {nome}! Desejo um dia lindo. Com carinho, {estudio}"


class Estudio(models.Model):
    """Dados do seu espaço. Existe um só (pk=1): use Estudio.atual()."""

    nome = models.CharField("nome do espaço", max_length=120, default="Meu espaço")
    profissional = models.CharField("seu nome", max_length=120, blank=True)
    registro = models.CharField("registro profissional", max_length=60, blank=True,
                                help_text="Ex.: CRBM, COREN... (sai nos documentos, opcional)")
    documento = models.CharField("CPF ou CNPJ", max_length=20, blank=True)
    telefone = models.CharField("telefone / WhatsApp", max_length=20, blank=True)
    endereco = models.CharField("endereço", max_length=250, blank=True)
    instagram = models.CharField(max_length=60, blank=True)
    logo = models.ImageField(upload_to="logo/", storage=storage_privado, blank=True)

    hora_abre = models.TimeField("abre às", default=time(8, 0))
    hora_fecha = models.TimeField("fecha às", default=time(20, 0))

    msg_lembrete = models.TextField("mensagem de lembrete", default=LEMBRETE_PADRAO,
                                    help_text="Use {nome}, {procedimento}, {quando}, {hora}, {data} e {estudio}.")
    msg_retorno = models.TextField("mensagem de retorno", default=RETORNO_PADRAO,
                                   help_text="Use {nome}, {procedimento} e {estudio}.")
    senha_financeiro = models.CharField(max_length=128, blank=True, editable=False,
                                        help_text="Guardada criptografada (nunca em texto).")

    msg_aniversario = models.TextField("mensagem de aniversário", default=ANIVERSARIO_PADRAO,
                                       help_text="Use {nome} e {estudio}.")

    class Meta:
        verbose_name = "dados do espaço"
        verbose_name_plural = "dados do espaço"

    def __str__(self):
        return self.nome

    @property
    def tem_senha_financeiro(self):
        return bool(self.senha_financeiro)

    def definir_senha_financeiro(self, senha):
        from django.contrib.auth.hashers import make_password

        self.senha_financeiro = make_password(senha) if senha else ""
        self.save(update_fields=["senha_financeiro"])

    def confere_senha_financeiro(self, senha):
        from django.contrib.auth.hashers import check_password

        return bool(self.senha_financeiro) and check_password(senha, self.senha_financeiro)

    @classmethod
    def atual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
