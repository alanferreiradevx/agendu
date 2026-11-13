from datetime import timedelta
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone


class Material(models.Model):
    UNIDADES = [
        ("un", "unidade"), ("ml", "ml"), ("g", "g"), ("fr", "frasco"), ("cx", "caixa"),
        ("pct", "pacote"), ("par", "par"), ("amp", "ampola"), ("m", "metro"),
    ]

    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="materiais", verbose_name="espaço")
    nome = models.CharField(max_length=120)
    unidade = models.CharField(max_length=4, choices=UNIDADES, default="un",
                               help_text="Como você conta este material ao usar (ml, g, unidade...).")
    quantidade = models.DecimalField("quantidade em estoque", max_digits=12, decimal_places=3, default=0)
    estoque_minimo = models.DecimalField("estoque mínimo", max_digits=12, decimal_places=3, default=0,
                                         help_text="Abaixo disso o painel avisa para comprar.")
    custo_unitario = models.DecimalField("custo por unidade", max_digits=12, decimal_places=4, default=0,
                                         help_text="Quanto custa 1 unidade (1 ml, 1 g...). Atualiza sozinho nas compras (média).")
    validade = models.DateField("validade do lote atual", null=True, blank=True)
    fornecedor = models.CharField(max_length=120, blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name_plural = "materiais"
        constraints = [models.UniqueConstraint(fields=["estudio", "nome"], name="material_nome_por_espaco")]

    def __str__(self):
        return self.nome

    @property
    def abaixo_do_minimo(self):
        return self.ativo and self.estoque_minimo > 0 and self.quantidade <= self.estoque_minimo

    @property
    def vencido(self):
        return bool(self.validade and self.validade < timezone.localdate())

    @property
    def vencendo(self):
        """Vence nos próximos 30 dias (e ainda não venceu)."""
        hoje = timezone.localdate()
        return bool(self.validade and hoje <= self.validade <= hoje + timedelta(days=30))

    @property
    def valor_em_estoque(self):
        return max(self.quantidade, 0) * self.custo_unitario


class Movimento(models.Model):
    TIPOS = [
        ("entrada", "Entrada (compra)"),
        ("saida", "Uso em atendimento"),
        ("ajuste", "Ajuste / perda"),
        ("estorno", "Estorno de atendimento"),
    ]

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="movimentos")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3,
                                     help_text="Positivo entra no estoque, negativo sai.")
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    saldo_depois = models.DecimalField(max_digits=12, decimal_places=3)
    agendamento = models.ForeignKey("agenda.Agendamento", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="movimentos")
    descricao = models.CharField("descrição", max_length=200, blank=True)
    data = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-data", "-pk"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.quantidade} {self.material}"


def movimentar(material, quantidade, tipo, *, custo_unitario=None, agendamento=None, descricao=""):
    """
    Única forma de mudar o estoque: grava o movimento e atualiza a quantidade.
    Na compra (entrada com custo), o custo por unidade vira a média ponderada
    entre o que já havia e o que chegou.
    O estoque pode ficar negativo (você usou algo que esqueceu de lançar):
    melhor registrar do que travar o atendimento; o painel mostra o alerta.
    """
    quantidade = Decimal(quantidade)
    with transaction.atomic():
        m = Material.objects.select_for_update().get(pk=material.pk)
        if tipo == "entrada" and custo_unitario is not None and quantidade > 0:
            custo_unitario = Decimal(custo_unitario)
            atual = max(m.quantidade, Decimal(0))
            if atual > 0 and m.custo_unitario > 0:
                m.custo_unitario = (atual * m.custo_unitario + quantidade * custo_unitario) / (atual + quantidade)
            else:
                m.custo_unitario = custo_unitario
        m.quantidade += quantidade
        m.save(update_fields=["quantidade", "custo_unitario"])
        mov = Movimento.objects.create(
            material=m, tipo=tipo, quantidade=quantidade, custo_unitario=custo_unitario,
            saldo_depois=m.quantidade, agendamento=agendamento, descricao=descricao[:200],
        )
    material.quantidade, material.custo_unitario = m.quantidade, m.custo_unitario
    return mov
