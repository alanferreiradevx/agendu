"""Listas do painel: retornos a chamar e aniversariantes."""

from datetime import timedelta

from django.utils import timezone

from clientes.models import Cliente

from .models import Agendamento


def retornos(estudio, antecedencia_dias=7, atraso_max_dias=90):
    """
    Clientes que estão na hora (ou perto) de voltar, pelo "retorno em (dias)" do
    último procedimento feito. Some da lista quando ela já tem horário marcado.
    """
    hoje = timezone.localdate()
    agora = timezone.now()
    com_horario = set(
        Agendamento.objects.filter(estudio=estudio, status__in=Agendamento.EM_ABERTO, inicio__gte=agora)
        .values_list("cliente_id", flat=True)
    )
    vistos, lista = set(), []
    feitos = (Agendamento.objects.filter(estudio=estudio, status=Agendamento.CONCLUIDO, procedimento__retorno_dias__isnull=False,
                                         cliente__ativo=True)
              .select_related("cliente", "procedimento").order_by("-inicio"))
    for ag in feitos:
        if ag.cliente_id in vistos:
            continue  # só o atendimento mais recente de cada cliente conta
        vistos.add(ag.cliente_id)
        if ag.cliente_id in com_horario:
            continue
        data = timezone.localdate(ag.inicio) + timedelta(days=ag.procedimento.retorno_dias)
        if hoje - timedelta(days=atraso_max_dias) <= data <= hoje + timedelta(days=antecedencia_dias):
            lista.append({"cliente": ag.cliente, "procedimento": ag.procedimento, "data": data,
                          "atrasado": data < hoje, "ultimo": ag})
    return sorted(lista, key=lambda r: r["data"])


def aniversariantes(estudio, mes=None):
    mes = mes or timezone.localdate().month
    lista = list(Cliente.objects.filter(estudio=estudio, ativo=True, nascimento__month=mes))
    return sorted(lista, key=lambda c: c.nascimento.day)
