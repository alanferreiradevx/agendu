from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.utils import centavos


def descrever_pagamento(forma, parcelas=1):
    if not forma:
        return ""
    if forma.parcelavel and parcelas and parcelas > 1:
        return f"{forma} em {parcelas}x"
    return str(forma)


class Procedimento(models.Model):
    CORES = [
        ("#8e5bb5", "Lilás"), ("#d9738b", "Rosa"), ("#e0a458", "Dourado"), ("#4f9d8f", "Verde-água"),
        ("#5b7fc7", "Azul"), ("#c4665a", "Terracota"), ("#7a8a5c", "Oliva"), ("#6b6b7b", "Cinza"),
    ]

    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="procedimentos", verbose_name="espaço")
    nome = models.CharField(max_length=120)
    descricao = models.TextField("descrição", blank=True)
    duracao_min = models.PositiveSmallIntegerField("duração (min)", default=60)
    preco = models.DecimalField("preço", max_digits=10, decimal_places=2, default=0)
    retorno_dias = models.PositiveSmallIntegerField(
        "retorno em (dias)", null=True, blank=True,
        help_text="Ex.: 30. O painel avisa quando chamar a cliente de volta. Em branco = sem retorno.",
    )
    cor = models.CharField(max_length=7, choices=CORES, default="#8e5bb5", help_text="Cor na agenda.")
    cuidados_pos = models.TextField("cuidados pós-procedimento", blank=True,
                                    help_text="Orientações para a cliente (dá para mandar pelo WhatsApp).")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(fields=["estudio", "nome"], name="procedimento_nome_por_espaco")]

    def __str__(self):
        return self.nome

    def custo_material(self):
        return sum((m.quantidade * m.material.custo_unitario for m in self.materiais.select_related("material")),
                   Decimal(0))

    def margem(self):
        return self.preco - self.custo_material()


class ProcedimentoMaterial(models.Model):
    """Quanto de cada material um procedimento gasta. Sai do estoque ao concluir o atendimento."""

    procedimento = models.ForeignKey(Procedimento, on_delete=models.CASCADE, related_name="materiais")
    material = models.ForeignKey("estoque.Material", on_delete=models.PROTECT, related_name="usos")
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)

    class Meta:
        unique_together = [("procedimento", "material")]
        verbose_name = "material do procedimento"
        verbose_name_plural = "materiais do procedimento"

    def __str__(self):
        return f"{self.quantidade} {self.material.unidade} de {self.material}"


class Pacote(models.Model):
    """Pacote de sessões vendido para uma cliente (ex.: 10 sessões de drenagem)."""

    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="pacotes", verbose_name="espaço")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="pacotes")
    procedimento = models.ForeignKey(Procedimento, on_delete=models.PROTECT, related_name="pacotes")
    sessoes = models.PositiveSmallIntegerField("número de sessões")
    valor = models.DecimalField("valor total", max_digits=10, decimal_places=2)
    data_compra = models.DateField("data da compra", default=timezone.localdate)
    validade = models.DateField(null=True, blank=True, help_text="Opcional: até quando as sessões valem.")
    observacoes = models.CharField("observações", max_length=250, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_compra", "-pk"]

    def __str__(self):
        return f"{self.sessoes}x {self.procedimento} - {self.cliente}"

    def clean_fields(self, exclude=None):
        if not self.estudio_id and self.cliente_id:
            self.estudio_id = self.cliente.estudio_id
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        if not self.estudio_id and self.cliente_id:
            self.estudio_id = self.cliente.estudio_id
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.cliente_id and self.procedimento_id and self.cliente.estudio_id != self.procedimento.estudio_id:
            raise ValidationError("Cliente e procedimento precisam ser do mesmo espaço.")

    @property
    def usadas(self):
        return self.agendamentos.filter(status=Agendamento.CONCLUIDO).count()

    @property
    def restantes(self):
        return max(self.sessoes - self.usadas, 0)

    @property
    def vencido(self):
        return bool(self.validade and self.validade < timezone.localdate())

    @property
    def valor_sessao(self):
        return centavos(self.valor / self.sessoes) if self.sessoes else Decimal(0)

    @property
    def recebido(self):
        return sum((l.valor for l in self.lancamentos.all()), Decimal(0))

    @property
    def a_receber(self):
        return max(self.valor - self.recebido, Decimal(0))

    def reservadas(self, exceto=None):
        """Sessões já marcadas na agenda (ainda não feitas) usando este pacote."""
        qs = self.agendamentos.filter(status__in=Agendamento.EM_ABERTO)
        if exceto is not None and exceto.pk:
            qs = qs.exclude(pk=exceto.pk)
        return qs.count()

    @classmethod
    def com_saldo(cls, cliente, procedimento=None):
        qs = cls.objects.filter(cliente=cliente, estudio_id=cliente.estudio_id).select_related("procedimento")
        if procedimento is not None:
            qs = qs.filter(procedimento=procedimento)
        return [p for p in qs if p.restantes > 0 and not p.vencido]


class Agendamento(models.Model):
    AGENDADO, CONFIRMADO, CONCLUIDO, FALTOU, CANCELADO = "agendado", "confirmado", "concluido", "faltou", "cancelado"
    STATUS = [
        (AGENDADO, "Agendado"), (CONFIRMADO, "Confirmado"), (CONCLUIDO, "Concluído"),
        (FALTOU, "Faltou"), (CANCELADO, "Cancelado"),
    ]
    EM_ABERTO = (AGENDADO, CONFIRMADO)  # ocupam o horário e ainda vão acontecer

    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="agendamentos", verbose_name="espaço")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="agendamentos")
    procedimento = models.ForeignKey(Procedimento, on_delete=models.PROTECT, related_name="agendamentos")
    inicio = models.DateTimeField("início")
    fim = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS, default=AGENDADO)
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                help_text="Preço combinado (vem do procedimento; mude se der desconto).")
    pacote = models.ForeignKey(Pacote, on_delete=models.SET_NULL, null=True, blank=True, related_name="agendamentos",
                               help_text="Se a sessão for de um pacote já pago.")
    forma_prevista = models.ForeignKey("financeiro.FormaPagamento", on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="+", verbose_name="como vai pagar")
    parcelas_previstas = models.PositiveSmallIntegerField("parcelas", default=1)
    observacoes = models.TextField("observações", blank=True)
    custo_material = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                         help_text="Custo dos materiais no dia em que foi concluído.")
    concluido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["inicio"]

    def __str__(self):
        return f"{self.cliente} - {self.procedimento} ({timezone.localtime(self.inicio):%d/%m %H:%M})"

    def clean_fields(self, exclude=None):
        if not self.estudio_id and self.cliente_id:
            self.estudio_id = self.cliente.estudio_id
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        if not self.estudio_id and self.cliente_id:
            self.estudio_id = self.cliente.estudio_id
        super().save(*args, **kwargs)

    @property
    def em_aberto(self):
        return self.status in self.EM_ABERTO

    @property
    def pagamento_previsto(self):
        """Ex.: "PIX" ou "Cartão de crédito parcelado em 3x"."""
        return descrever_pagamento(self.forma_prevista, self.parcelas_previstas)

    @property
    def pagamento_feito(self):
        """Como foi pago de verdade (do lançamento no caixa), ou "pacote"."""
        if self.status != self.CONCLUIDO:
            return ""
        if self.pacote_id:
            return "Sessão do pacote"
        lanc = self.lancamentos.select_related("forma").first()
        return descrever_pagamento(lanc.forma, lanc.parcelas) if lanc else ""

    @property
    def duracao_min(self):
        return int((self.fim - self.inicio).total_seconds() // 60)

    def conflitos(self):
        """Outros atendimentos em aberto que se sobrepõem a este horário."""
        estudio_id = self.estudio_id or (self.cliente.estudio_id if self.cliente_id else None)
        qs = Agendamento.objects.filter(estudio_id=estudio_id, status__in=self.EM_ABERTO,
                                        inicio__lt=self.fim, fim__gt=self.inicio)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        return qs.select_related("cliente")

    def clean(self):
        super().clean()
        if self.inicio and self.fim and self.fim <= self.inicio:
            raise ValidationError("O fim precisa ser depois do início.")
        if self.cliente_id and self.procedimento_id and self.cliente.estudio_id != self.procedimento.estudio_id:
            raise ValidationError("Cliente e procedimento precisam ser do mesmo espaço.")
        if self.inicio and self.fim and self.em_aberto:
            outro = self.conflitos().first()
            if outro:
                hora = timezone.localtime(outro.inicio)
                raise ValidationError(f"Esse horário bate com {outro.cliente} às {hora:%H:%M}.")
        if self.pacote_id and self.cliente_id and self.procedimento_id:
            p = self.pacote
            if p.cliente_id != self.cliente_id or p.procedimento_id != self.procedimento_id:
                raise ValidationError({"pacote": "O pacote precisa ser desta cliente e deste procedimento."})
            if self.status != self.CONCLUIDO and p.restantes - p.reservadas(exceto=self) <= 0:
                raise ValidationError({"pacote": "Este pacote não tem mais sessões livres."})

    def margem(self):
        """Valor recebido (ou valor da sessão do pacote) menos materiais e taxas."""
        if self.status != self.CONCLUIDO:
            return None
        receita = self.pacote.valor_sessao if self.pacote_id else sum(
            (l.liquido for l in self.lancamentos.all()), Decimal(0))
        return receita - (self.custo_material or 0)

    @staticmethod
    def fim_padrao(inicio, procedimento):
        return inicio + timedelta(minutes=procedimento.duracao_min or 60)
