"""
Regras que mexem em mais de uma coisa ao mesmo tempo (agenda + estoque + caixa).
Tudo dentro de uma transação: ou faz tudo, ou não faz nada.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from clientes.models import Evolucao, Foto
from core.utils import centavos
from estoque.models import movimentar
from financeiro.models import Lancamento

from .models import Agendamento, Pacote


@transaction.atomic
def concluir(agendamento, *, forma=None, valor=None, parcelas=1, usar_pacote=None, evolucao="", medidas="",
             fotos=(), momento_fotos="depois"):
    """
    Conclui o atendimento:
      1. tira do estoque os materiais do procedimento (e guarda o custo);
      2. se for sessão de pacote, gasta uma sessão; senão lança a entrada no caixa
         (com a taxa da forma de pagamento);
      3. grava a evolução e as fotos, se vierem.
    """
    ag = Agendamento.objects.select_for_update().select_related("cliente", "procedimento").get(pk=agendamento.pk)
    if ag.status == Agendamento.CONCLUIDO:
        raise ValidationError("Este atendimento já foi concluído.")
    if ag.status == Agendamento.CANCELADO:
        raise ValidationError("Atendimento cancelado não pode ser concluído.")

    if usar_pacote:
        pacote = Pacote.objects.select_for_update().get(pk=usar_pacote.pk)
        if pacote.cliente_id != ag.cliente_id or pacote.procedimento_id != ag.procedimento_id:
            raise ValidationError("O pacote precisa ser desta cliente e deste procedimento.")
        if pacote.restantes <= 0:
            raise ValidationError("Este pacote não tem mais sessões.")
        ag.pacote = pacote
    else:
        ag.pacote = None

    custo = Decimal(0)
    descricao = f"{ag.procedimento} - {ag.cliente}"
    for pm in ag.procedimento.materiais.select_related("material"):
        custo += pm.quantidade * pm.material.custo_unitario
        movimentar(pm.material, -pm.quantidade, "saida", agendamento=ag, descricao=descricao)
    ag.custo_material = centavos(custo)

    if not ag.pacote_id:
        valor = centavos(ag.valor if valor is None else valor)
        ag.valor = valor
        if valor > 0:
            Lancamento.objects.create(
                estudio=ag.estudio, tipo=Lancamento.ENTRADA, categoria="atendimento", descricao=descricao, valor=valor,
                forma=forma, parcelas=parcelas or 1, taxa=forma.taxa_sobre(valor) if forma else 0,
                cliente=ag.cliente, agendamento=ag, data=timezone.localdate(),
            )

    ag.status = Agendamento.CONCLUIDO
    ag.concluido_em = timezone.now()
    ag.save()

    evo = None
    if evolucao.strip() or fotos:
        evo = Evolucao.objects.create(
            cliente=ag.cliente, agendamento=ag, data=timezone.localdate(ag.inicio),
            texto=evolucao.strip() or f"Sessão de {ag.procedimento}.", medidas=medidas,
        )
    for arquivo in fotos:
        Foto.objects.create(cliente=ag.cliente, agendamento=ag, evolucao=evo, imagem=arquivo,
                            momento=momento_fotos, data=timezone.localdate(ag.inicio))
    return ag


@transaction.atomic
def desfazer_conclusao(agendamento):
    """
    Volta um atendimento concluído por engano: devolve os materiais ao estoque,
    apaga a entrada do caixa e libera a sessão do pacote. Evolução e fotos ficam.
    """
    ag = Agendamento.objects.select_for_update().get(pk=agendamento.pk)
    if ag.status != Agendamento.CONCLUIDO:
        raise ValidationError("Só dá para desfazer um atendimento concluído.")
    for mov in ag.movimentos.filter(tipo="saida").select_related("material"):
        movimentar(mov.material, -mov.quantidade, "estorno", agendamento=ag,
                   descricao=f"Desfeito: {ag.procedimento} - {ag.cliente}")
    ag.lancamentos.filter(categoria="atendimento").delete()
    ag.status = Agendamento.AGENDADO
    ag.concluido_em = None
    ag.custo_material = None
    ag.save()
    return ag


@transaction.atomic
def vender_pacote(pacote, *, forma=None, valor_pago=None, parcelas=1):
    """Grava o pacote e, se houver pagamento agora, lança a entrada no caixa."""
    if not pacote.estudio_id and pacote.cliente_id:
        pacote.estudio_id = pacote.cliente.estudio_id
    pacote.full_clean()
    pacote.save()
    valor_pago = centavos(pacote.valor if valor_pago is None else valor_pago)
    if valor_pago > 0:
        Lancamento.objects.create(
            estudio=pacote.estudio, tipo=Lancamento.ENTRADA, categoria="pacote", valor=valor_pago, forma=forma, parcelas=parcelas or 1,
            taxa=forma.taxa_sobre(valor_pago) if forma else 0, cliente=pacote.cliente, pacote=pacote,
            descricao=f"Pacote {pacote.sessoes}x {pacote.procedimento} - {pacote.cliente}",
        )
    return pacote


def receber_pacote(pacote, *, valor, forma=None, parcelas=1):
    """Pagamento de uma parte do pacote que ficou em aberto."""
    valor = centavos(valor)
    return Lancamento.objects.create(
        estudio=pacote.estudio, tipo=Lancamento.ENTRADA, categoria="pacote", valor=valor, forma=forma, parcelas=parcelas or 1,
        taxa=forma.taxa_sobre(valor) if forma else 0, cliente=pacote.cliente, pacote=pacote,
        descricao=f"Pagamento do pacote {pacote.sessoes}x {pacote.procedimento} - {pacote.cliente}",
    )
