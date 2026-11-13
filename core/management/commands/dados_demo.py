"""
Cria dados de exemplo para conhecer o sistema (SÓ em desenvolvimento).

    python manage.py dados_demo

E-mail: demo@agendu.local / senha: Agendu#2026 · senha do financeiro: 1234
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from agenda import servicos
from agenda.models import Agendamento, Pacote, Procedimento, ProcedimentoMaterial
from clientes.models import Cliente, Ficha
from core.models import estudio_do_usuario
from estoque.models import Material, movimentar
from financeiro.models import FormaPagamento, Lancamento


class Command(BaseCommand):
    help = "Cria dados de demonstração (não use em produção)."

    def handle(self, *args, **opcoes):
        if not settings.DEBUG:
            raise CommandError("Só em desenvolvimento (DJANGO_DEBUG=true).")
        User = get_user_model()
        demo = User.objects.filter(username="demo").first() or User.objects.create_superuser(
            "demo", "demo@agendu.local", "Agendu#2026")

        e = estudio_do_usuario(demo)
        e.nome, e.profissional, e.telefone = "Studio Bella Pele", "Ana", "(11) 91234-5678"
        e.endereco, e.instagram = "Rua das Flores, 100 - São Paulo/SP", "@studiobellapele"
        e.save()
        if not e.tem_senha_financeiro:
            e.definir_senha_financeiro("1234")

        def mat(nome, unidade, qtd, total, minimo):
            m, criado = Material.objects.get_or_create(estudio=e, nome=nome, defaults={"unidade": unidade, "estoque_minimo": minimo})
            if criado:
                movimentar(m, qtd, "entrada", custo_unitario=Decimal(total) / qtd, descricao="Estoque inicial")
            return m

        gel = mat("Gel condutor", "ml", 1000, "45", 200)
        acido = mat("Ácido glicólico 10%", "ml", 30, "120", 10)
        mascara = mat("Máscara calmante", "g", 200, "80", 50)
        luva = mat("Luva de procedimento", "par", 100, "40", 20)
        agulha = mat("Cartucho de microagulhamento", "un", 4, "60", 5)
        oleo = mat("Óleo de massagem", "ml", 500, "70", 100)
        hoje = timezone.localdate()
        acido.validade = hoje + timedelta(days=20)
        acido.save()

        def proc(nome, preco, minutos, retorno, cor, materiais):
            p, _ = Procedimento.objects.get_or_create(estudio=e, nome=nome, defaults={
                "preco": preco, "duracao_min": minutos, "retorno_dias": retorno, "cor": cor,
                "cuidados_pos": "Evite sol por 48 h, use protetor solar FPS 50 e não esfolie a pele por 5 dias."})
            for m, q in materiais:
                ProcedimentoMaterial.objects.get_or_create(procedimento=p, material=m, defaults={"quantidade": q})
            return p

        limpeza = proc("Limpeza de pele profunda", "180", 90, 30, "#4f9d8f", [(luva, 1), (mascara, 15), (gel, 10)])
        peeling = proc("Peeling químico", "250", 60, 21, "#d9738b", [(luva, 1), (acido, 3)])
        micro = proc("Microagulhamento", "350", 75, 30, "#8e5bb5", [(luva, 1), (agulha, 1), (mascara, 10)])
        drenagem = proc("Drenagem linfática", "150", 60, 7, "#5b7fc7", [(oleo, 30)])

        nomes = [("Mariana Souza", date(1992, hoje.month, min(hoje.day + 3, 28)), "11987654321"),
                 ("Juliana Lima", date(1988, 3, 14), "11976543210"), ("Patrícia Alves", date(1995, 7, 2), "11965432109"),
                 ("Camila Rocha", date(1990, 11, 23), "11954321098"), ("Fernanda Dias", date(1985, 1, 30), "11943210987")]
        clientes = []
        for nome, nasc, fone in nomes:
            c, _ = Cliente.objects.get_or_create(estudio=e, nome=nome, defaults={"nascimento": nasc, "telefone": fone,
                                                                      "como_conheceu": "Instagram", "cidade": "São Paulo", "uf": "SP"})
            Ficha.objects.get_or_create(cliente=c, defaults={"queixa_principal": "Manchas e textura da pele",
                                                             "tipo_pele": "mista", "fototipo": "III", "usa_protetor": True})
            clientes.append(c)
        Ficha.objects.filter(cliente=clientes[1]).update(alergias="Dipirona", acidos_retinoides=True)

        if Agendamento.objects.filter(estudio=e).exists():
            self.stdout.write(self.style.WARNING("Já existiam atendimentos; só completei cadastros."))
            return

        pix = FormaPagamento.objects.get(estudio=e, nome="PIX")
        credito = FormaPagamento.objects.get(estudio=e, nome="Cartão de crédito à vista")

        def marcar(cliente, p, dia, hora, **extra):
            inicio = timezone.make_aware(datetime.combine(dia, time(hora)))
            return Agendamento.objects.create(cliente=cliente, procedimento=p, inicio=inicio,
                                              fim=Agendamento.fim_padrao(inicio, p), **{"valor": p.preco, **extra})

        # passado: atendimentos concluídos (baixa estoque e entra no caixa)
        for i, (c, p, dias) in enumerate([(clientes[0], limpeza, 34), (clientes[1], peeling, 25), (clientes[2], micro, 12),
                                          (clientes[3], limpeza, 9), (clientes[0], peeling, 5), (clientes[4], micro, 3)]):
            ag = marcar(c, p, hoje - timedelta(days=dias), 10 + i % 6)
            servicos.concluir(ag, forma=pix if i % 2 else credito, evolucao="Pele respondeu bem, sem vermelhidão.")

        pacote = servicos.vender_pacote(Pacote(cliente=clientes[2], procedimento=drenagem, sessoes=10, valor=Decimal("1200")),
                                        forma=credito, valor_pago=Decimal("600"), parcelas=3)
        for d in (6, 2):
            ag = marcar(clientes[2], drenagem, hoje - timedelta(days=d), 16, pacote=pacote, valor=0)
            servicos.concluir(ag, usar_pacote=pacote)

        # futuro
        marcar(clientes[1], limpeza, hoje, 14)
        marcar(clientes[3], micro, hoje, 16, status=Agendamento.CONFIRMADO)
        marcar(clientes[4], peeling, hoje + timedelta(days=1), 9)
        marcar(clientes[2], drenagem, hoje + timedelta(days=2), 15, pacote=pacote, valor=0)

        Lancamento.objects.create(estudio=e, tipo="saida", categoria="aluguel", descricao="Aluguel da sala", valor=Decimal("1200"),
                                  data=hoje.replace(day=1))
        Lancamento.objects.create(estudio=e, tipo="saida", categoria="marketing", descricao="Anúncio Instagram", valor=Decimal("150"))
        self.stdout.write(self.style.SUCCESS("Pronto! Entre com demo@agendu.local / Agendu#2026 (senha do financeiro: 1234)"))
