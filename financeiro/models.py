from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from core.utils import centavos


class FormaPagamento(models.Model):
    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="formas_pagamento", verbose_name="espaço")
    nome = models.CharField(max_length=60)
    taxa_percentual = models.DecimalField("taxa (%)", max_digits=5, decimal_places=2, default=0,
                                          help_text="Taxa da maquininha/banco. Ex.: 3,49 para o crédito.")
    parcelavel = models.BooleanField("parcelado", default=False,
                                     help_text="Marcado: ao escolher esta forma, pergunta em quantas vezes (2x a 12x).")
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "forma de pagamento"
        verbose_name_plural = "formas de pagamento"
        constraints = [models.UniqueConstraint(fields=["estudio", "nome"], name="forma_nome_por_espaco")]

    def __str__(self):
        return self.nome

    def taxa_sobre(self, valor):
        return centavos(Decimal(valor) * self.taxa_percentual / 100)


class Lancamento(models.Model):
    """Tudo que entra ou sai do caixa."""

    ENTRADA, SAIDA = "entrada", "saida"
    TIPOS = [(ENTRADA, "Entrada"), (SAIDA, "Saída")]
    CATEGORIAS_ENTRADA = [
        ("atendimento", "Atendimento"), ("pacote", "Venda de pacote"), ("produto", "Venda de produto"),
        ("outra_entrada", "Outra entrada"),
    ]
    CATEGORIAS_SAIDA = [
        ("material", "Material / produtos"), ("aluguel", "Aluguel"), ("contas", "Água, luz, internet"),
        ("equipamento", "Equipamentos"), ("marketing", "Marketing / anúncios"), ("cursos", "Cursos"),
        ("impostos", "Impostos / MEI"), ("pro_labore", "Pró-labore (seu salário)"), ("outra_saida", "Outra despesa"),
    ]
    CATEGORIAS = CATEGORIAS_ENTRADA + CATEGORIAS_SAIDA

    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="lancamentos", verbose_name="espaço")
    tipo = models.CharField(max_length=8, choices=TIPOS)
    data = models.DateField(default=timezone.localdate)
    descricao = models.CharField("descrição", max_length=200)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    forma = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT, null=True, blank=True,
                              verbose_name="forma de pagamento")
    parcelas = models.PositiveSmallIntegerField(default=1)
    taxa = models.DecimalField("taxa cobrada", max_digits=12, decimal_places=2, default=0)
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="lancamentos")
    agendamento = models.ForeignKey("agenda.Agendamento", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="lancamentos")
    pacote = models.ForeignKey("agenda.Pacote", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="lancamentos")
    observacoes = models.CharField("observações", max_length=250, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-pk"]
        verbose_name = "lançamento"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.valor} - {self.descricao}"

    def save(self, *args, **kwargs):
        if not self.estudio_id:
            origem = self.cliente or self.agendamento or self.pacote
            if origem is not None:
                self.estudio_id = origem.estudio_id
        super().save(*args, **kwargs)

    @property
    def liquido(self):
        """Entrada já sem a taxa da maquininha."""
        return self.valor - self.taxa if self.tipo == self.ENTRADA else self.valor


def resumo(qs):
    """Totais de um conjunto de lançamentos: entradas, taxas, saídas e lucro."""
    entradas = qs.filter(tipo=Lancamento.ENTRADA).aggregate(v=Sum("valor"), t=Sum("taxa"))
    saidas = qs.filter(tipo=Lancamento.SAIDA).aggregate(v=Sum("valor"))["v"] or Decimal(0)
    bruto, taxas = entradas["v"] or Decimal(0), entradas["t"] or Decimal(0)
    return {"entradas": bruto, "taxas": taxas, "liquido": bruto - taxas, "saidas": saidas, "custos": saidas + taxas,
            "lucro": bruto - taxas - saidas}
