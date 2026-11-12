from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from agenda.models import Agendamento
from financeiro.models import FormaPagamento, Lancamento

from .tests import Base


class ComoPagaTests(Base):
    """Como vai pagar (no agendamento) e como pagou (na conclusão): PIX, dinheiro, cartão, parcelado em X vezes."""

    def setUp(self):
        super().setUp()
        self.parcelado = FormaPagamento.objects.get(nome="Cartão de crédito parcelado")
        self.dados = {"cliente": self.cliente.pk, "procedimento": self.peeling.pk, "duracao": 60, "valor": "200",
                      "data": timezone.localdate() + timedelta(days=1), "hora": "10:00"}

    def test_formas_aparecem_como_botoes_com_parcelas(self):
        r = self.client.get("/agenda/novo/")
        for texto in ("Forma de pagamento", 'type="radio"', "PIX", "Dinheiro", "Cartão de débito",
                      "Cartão de crédito parcelado", "Ainda não sei", "12x", f'data-parcelaveis="{self.parcelado.pk}"'):
            self.assertContains(r, texto)

    def test_agenda_parcelado_e_a_conclusao_ja_vem_marcada(self):
        self.client.post("/agenda/novo/", {**self.dados, "forma_prevista": self.parcelado.pk, "parcelas_previstas": 3})
        ag = Agendamento.objects.get()
        self.assertEqual((ag.forma_prevista, ag.parcelas_previstas), (self.parcelado, 3))
        self.assertEqual(ag.pagamento_previsto, "Cartão de crédito parcelado em 3x")
        self.assertContains(self.client.get(f"/agenda/{ag.pk}/"), "Cartão de crédito parcelado em 3x")
        r = self.client.get(f"/agenda/{ag.pk}/concluir/")
        self.assertContains(r, f'value="{self.parcelado.pk}" id="id_forma_', html=False)
        self.assertEqual(r.context["form"].initial["forma"], self.parcelado.pk)
        self.assertEqual(r.context["form"].initial["parcelas"], 3)
        # pagou de outro jeito: em 5x
        self.client.post(f"/agenda/{ag.pk}/concluir/", {"forma": self.parcelado.pk, "parcelas": 5, "valor": "200",
                                                         "momento_fotos": "depois"})
        lanc = Lancamento.objects.get(agendamento=ag)
        self.assertEqual((lanc.forma, lanc.parcelas), (self.parcelado, 5))
        ag.refresh_from_db()
        self.assertEqual(ag.pagamento_feito, "Cartão de crédito parcelado em 5x")

    def test_a_vista_ignora_parcelas_e_parcelado_exige(self):
        self.client.post("/agenda/novo/", {**self.dados, "forma_prevista": self.pix.pk, "parcelas_previstas": 4})
        self.assertEqual(Agendamento.objects.get().parcelas_previstas, 1)  # PIX é à vista
        ag = Agendamento.objects.get()
        r = self.client.post(f"/agenda/{ag.pk}/concluir/", {"forma": self.parcelado.pk, "parcelas": "", "valor": "200",
                                                             "momento_fotos": "depois"})
        self.assertContains(r, "Escolha em quantas vezes")

    def test_forma_aparece_mesmo_com_o_financeiro_trancado(self):
        self.client.post("/agenda/novo/", {**self.dados, "forma_prevista": self.parcelado.pk, "parcelas_previstas": 2})
        ag = Agendamento.objects.get()
        self.trancar()
        r = self.client.get(f"/agenda/{ag.pk}/concluir/")
        self.assertContains(r, "Cartão de crédito parcelado")
        self.assertContains(r, 'name="parcelas"')
        self.assertNotContains(r, 'name="valor"')
        self.client.post(f"/agenda/{ag.pk}/concluir/", {"forma": self.parcelado.pk, "parcelas": 2, "momento_fotos": "depois"})
        lanc = Lancamento.objects.get(agendamento=ag)
        self.assertEqual((lanc.valor, lanc.parcelas), (Decimal("200"), 2))

    def test_sessao_de_pacote_nao_guarda_forma(self):
        from agenda.models import Pacote

        pacote = Pacote.objects.create(cliente=self.cliente, procedimento=self.peeling, sessoes=2, valor=300)
        self.client.post("/agenda/novo/", {**self.dados, "pacote": pacote.pk, "forma_prevista": self.pix.pk})
        self.assertIsNone(Agendamento.objects.get().forma_prevista)

    def test_escolher_a_forma_direto_no_atendimento(self):
        ag = self.marcar(dias=1)
        r = self.client.get(f"/agenda/{ag.pk}/")
        self.assertContains(r, "Forma de pagamento")
        self.assertContains(r, "Salvar forma de pagamento")
        self.assertNotContains(r, "não informado")
        self.client.post(f"/agenda/{ag.pk}/forma/", {"forma_prevista": self.parcelado.pk, "parcelas_previstas": 4})
        ag.refresh_from_db()
        self.assertEqual(ag.pagamento_previsto, "Cartão de crédito parcelado em 4x")
        self.trancar()  # não é valor: dá para escolher com o financeiro trancado
        self.client.post(f"/agenda/{ag.pk}/forma/", {"forma_prevista": self.pix.pk, "parcelas_previstas": 2})
        ag.refresh_from_db()
        self.assertEqual((ag.pagamento_previsto, ag.parcelas_previstas), ("PIX", 1))
