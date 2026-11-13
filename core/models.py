from datetime import time, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

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

FORMAS_PADRAO = [
    ("PIX", 0, False, 1), ("Dinheiro", 0, False, 2), ("Cartão de débito", "1.99", False, 3),
    ("Cartão de crédito à vista", "3.49", False, 4), ("Cartão de crédito parcelado", "4.99", True, 5),
]


class Estudio(models.Model):
    """
    Um espaço que usa o Agendu (o seu e o de cada profissional a quem você libera acesso).
    TUDO (clientes, agenda, caixa, estoque...) pertence a um espaço, e cada pessoa só vê o seu.
    O acesso (ativo, validade, plano) é controlado pelo master na área "Acessos".
    """

    dono = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="estudio", verbose_name="profissional (login)")
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

    # ----- Acesso (só o master mexe) -----
    ativo = models.BooleanField("acesso liberado", default=True)
    valido_ate = models.DateField("acesso válido até", null=True, blank=True,
                                  help_text="Depois desta data o acesso bloqueia sozinho. Em branco = sem vencimento.")
    plano = models.CharField(max_length=60, blank=True, help_text="Ex.: Mensal, Anual, Cortesia")
    valor_mensal = models.DecimalField("valor mensal", max_digits=10, decimal_places=2, default=0)
    anotacoes = models.TextField("anotações (só você vê)", blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "espaço"
        verbose_name_plural = "espaços"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    # ----- acesso -----
    @property
    def vencido(self):
        return bool(self.valido_ate and self.valido_ate < timezone.localdate())

    @property
    def dias_para_vencer(self):
        if not self.valido_ate:
            return None
        return (self.valido_ate - timezone.localdate()).days

    @property
    def pode_entrar(self):
        return self.ativo and not self.vencido

    @property
    def convite_pendente(self):
        """A profissional ainda não criou a senha (nunca usou o link do convite)."""
        return bool(self.dono and not self.dono.has_usable_password())

    @property
    def situacao(self):
        if not self.ativo:
            return "bloqueado"
        if self.vencido:
            return "vencido"
        if self.convite_pendente:
            return "convite"
        if self.dias_para_vencer is not None and self.dias_para_vencer <= 7:
            return "vencendo"
        return "ativo"

    def renovar(self, dias=30):
        """Estende a validade a partir de hoje (se já venceu) ou da data atual de vencimento."""
        base = max(self.valido_ate or timezone.localdate(), timezone.localdate())
        self.valido_ate = base + timedelta(days=dias)
        self.save(update_fields=["valido_ate"])

    # ----- senha do financeiro -----
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

    def criar_formas_padrao(self):
        """PIX, dinheiro e cartões, com taxas comuns (cada espaço ajusta as suas)."""
        from financeiro.models import FormaPagamento

        for nome, taxa, parcelavel, ordem in FORMAS_PADRAO:
            FormaPagamento.objects.get_or_create(estudio=self, nome=nome, defaults={
                "taxa_percentual": taxa, "parcelavel": parcelavel, "ordem": ordem})


def estudio_do_usuario(usuario):
    """O espaço do usuário. O master sem espaço ganha um (o primeiro sem dono, ou um novo)."""
    if not usuario.is_authenticated:
        return None
    try:
        return usuario.estudio
    except Estudio.DoesNotExist:
        pass
    if not usuario.is_superuser:
        return None
    estudio = Estudio.objects.filter(dono__isnull=True).order_by("pk").first() or Estudio(nome="Meu espaço")
    estudio.dono = usuario
    estudio.save()
    estudio.criar_formas_padrao()
    return estudio
