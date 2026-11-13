import shutil
import tempfile
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from agenda import servicos
from agenda.consultas import retornos
from agenda.models import Agendamento, Pacote, Procedimento, ProcedimentoMaterial
from clientes.models import Cliente, Foto
from core.models import Estudio
from core.utils import brl, whatsapp_url
from estoque.models import Material, movimentar
from financeiro.models import FormaPagamento, Lancamento, resumo

PASTA_TESTE = tempfile.mkdtemp()


def imagem(nome="foto.jpg", tamanho=(3000, 2000)):
    from PIL import Image

    saida = BytesIO()
    Image.new("RGB", tamanho, (200, 150, 140)).save(saida, "JPEG")
    return SimpleUploadedFile(nome, saida.getvalue(), content_type="image/jpeg")


@override_settings(PRIVADO_ROOT=PASTA_TESTE)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("ana", email="ana@estudio.com", password="senha-forte-123")
        self.client.force_login(self.user)
        self.estudio = Estudio.objects.create(nome="Studio Ana", profissional="Ana", dono=self.user)
        self.estudio.criar_formas_padrao()
        self.estudio.definir_senha_financeiro("4321")
        self.abrir_financeiro()
        self.cliente = Cliente.objects.create(estudio=self.estudio, nome="Maria Silva", telefone="(11) 98765-4321")
        self.luva = Material.objects.create(estudio=self.estudio, nome="Luva", unidade="par")
        movimentar(self.luva, 10, "entrada", custo_unitario=Decimal("0.50"))
        self.acido = Material.objects.create(estudio=self.estudio, nome="Ácido", unidade="ml")
        movimentar(self.acido, 30, "entrada", custo_unitario=Decimal("4"))
        self.peeling = Procedimento.objects.create(estudio=self.estudio, nome="Peeling", preco=Decimal("200"), duracao_min=60, retorno_dias=21)
        ProcedimentoMaterial.objects.create(procedimento=self.peeling, material=self.luva, quantidade=1)
        ProcedimentoMaterial.objects.create(procedimento=self.peeling, material=self.acido, quantidade=3)
        self.pix = FormaPagamento.objects.get(estudio=self.estudio, nome="PIX")
        self.credito = FormaPagamento.objects.get(estudio=self.estudio, nome="Cartão de crédito à vista")

    def abrir_financeiro(self):
        self.client.post("/financeiro/entrar/", {"senha": "4321"})

    def trancar(self):
        self.client.post("/financeiro/trancar/")

    def marcar(self, dias=0, hora=10, **extra):
        inicio = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=dias), time(hora)))
        dados = {"cliente": self.cliente, "procedimento": self.peeling, "inicio": inicio,
                 "fim": inicio + timedelta(minutes=60), "valor": self.peeling.preco, **extra}
        return Agendamento.objects.create(**dados)


class LoginTests(Base):
    def test_tudo_exige_login(self):
        self.client.logout()
        for url in ["/", "/agenda/", "/clientes/", "/caixa/", "/estoque/", f"/clientes/{self.cliente.pk}/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/entrar/", r["Location"])

    def test_bloqueia_depois_de_5_senhas_erradas(self):
        self.client.logout()
        for _ in range(5):
            self.client.post("/entrar/", {"username": "ana@estudio.com", "password": "errada"})
        r = self.client.post("/entrar/", {"username": "ana@estudio.com", "password": "senha-forte-123"})
        self.assertContains(r, "Muitas tentativas")

    def test_manter_conectado(self):
        self.client.logout()
        self.client.post("/entrar/", {"username": "ana@estudio.com", "password": "senha-forte-123", "lembrar": "1"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.client.logout()
        self.client.post("/entrar/", {"username": "ana@estudio.com", "password": "senha-forte-123"})
        self.assertTrue(self.client.session.get_expire_at_browser_close())  # sem marcar: sai ao fechar o navegador

    def test_tela_de_entrada(self):
        self.client.logout()
        r = self.client.get("/entrar/")
        for texto in ("Bem-vindo de volta", "Manter conectado", "Esqueceu a senha?", "Entrar na plataforma",
                      "AGENDAR. ORGANIZAR. CRESCER."):
            self.assertContains(r, texto)

    def test_entra_pelo_email_e_nao_pelo_usuario(self):
        self.client.logout()
        r = self.client.get("/entrar/")
        self.assertContains(r, 'type="email"')
        r = self.client.post("/entrar/", {"username": "ana", "password": "senha-forte-123"})
        self.assertContains(r, "E-mail ou senha incorretos")
        r = self.client.post("/entrar/", {"username": "  ANA@Estudio.com ", "password": "senha-forte-123"})
        self.assertRedirects(r, "/")


class PaginasTests(Base):
    def test_todas_as_paginas_abrem(self):
        ag = self.marcar()
        servicos.concluir(self.marcar(dias=-3), forma=self.pix)
        pacote = servicos.vender_pacote(Pacote(cliente=self.cliente, procedimento=self.peeling, sessoes=5,
                                               valor=Decimal("800")), forma=self.pix)
        urls = [
            "/", "/agenda/", "/agenda/novo/", f"/agenda/{ag.pk}/", f"/agenda/{ag.pk}/editar/", f"/agenda/{ag.pk}/concluir/",
            "/agenda/procedimentos/", "/agenda/procedimentos/novo/", f"/agenda/procedimentos/{self.peeling.pk}/",
            "/agenda/pacotes/", "/agenda/pacotes/novo/", f"/agenda/pacotes/{pacote.pk}/",
            "/clientes/", "/clientes/nova/", f"/clientes/{self.cliente.pk}/editar/",
            f"/clientes/{self.cliente.pk}/ficha/imprimir/",
            "/estoque/", "/estoque/?filtro=alerta", "/estoque/novo/", f"/estoque/{self.luva.pk}/",
            f"/estoque/{self.luva.pk}/editar/",
            "/caixa/", "/caixa/?tipo=saida", "/caixa/faturamento/", "/caixa/novo/entrada/", "/caixa/novo/saida/",
            "/configuracoes/", "/senha/", "/caixa/formas/", "/financeiro/senha/",
        ] + [f"/clientes/{self.cliente.pk}/?aba={a}" for a in
             ("resumo", "ficha", "evolucao", "fotos", "agenda", "pacotes", "financeiro")]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_busca_vai_direto_para_a_cliente(self):
        r = self.client.get("/busca/?q=maria")
        self.assertRedirects(r, f"/clientes/{self.cliente.pk}/")


class AgendamentoTests(Base):
    def test_agendar_pela_tela_e_conflito_de_horario(self):
        dados = {"cliente": self.cliente.pk, "procedimento": self.peeling.pk, "data": timezone.localdate() + timedelta(days=1),
                 "hora": "14:00", "duracao": 60, "valor": "200"}
        r = self.client.post("/agenda/novo/", dados)
        ag = Agendamento.objects.get()
        self.assertRedirects(r, f"/agenda/{ag.pk}/")
        self.assertEqual(timezone.localtime(ag.fim).hour, 15)
        outra = Cliente.objects.create(estudio=self.estudio, nome="Joana")
        r = self.client.post("/agenda/novo/", {**dados, "cliente": outra.pk, "hora": "14:30"})
        self.assertContains(r, "Esse horário bate com Maria Silva")
        # cancelado libera o horário
        ag.status = Agendamento.CANCELADO
        ag.save()
        r = self.client.post("/agenda/novo/", {**dados, "cliente": outra.pk, "hora": "14:30"})
        self.assertEqual(Agendamento.objects.count(), 2)

    def test_lembrete_whatsapp_com_mensagem(self):
        ag = self.marcar(dias=1, hora=15)
        r = self.client.get(f"/agenda/{ag.pk}/")
        self.assertContains(r, "https://wa.me/5511987654321?text=")
        self.assertContains(r, "amanh%C3%A3%20%C3%A0s%2015%3A00")


class ConcluirTests(Base):
    def test_concluir_baixa_estoque_e_lanca_no_caixa_com_taxa(self):
        ag = self.marcar()
        r = self.client.post(f"/agenda/{ag.pk}/concluir/", {"valor": "200", "forma": self.credito.pk, "parcelas": 2,
                                                             "evolucao": "Ótima resposta", "momento_fotos": "depois",
                                                             "fotos": [imagem()]})
        self.assertRedirects(r, f"/agenda/{ag.pk}/")
        ag.refresh_from_db()
        self.luva.refresh_from_db()
        self.acido.refresh_from_db()
        self.assertEqual(ag.status, "concluido")
        self.assertEqual((self.luva.quantidade, self.acido.quantidade), (9, 27))
        self.assertEqual(ag.custo_material, Decimal("12.50"))  # 1 luva 0,50 + 3 ml x 4,00
        lanc = Lancamento.objects.get()
        self.assertEqual((lanc.valor, lanc.taxa), (Decimal("200"), Decimal("6.98")))  # 3,49%
        self.assertEqual(ag.margem(), Decimal("200") - Decimal("6.98") - Decimal("12.50"))
        evo = self.cliente.evolucoes.get()
        self.assertEqual(evo.fotos.count(), 1)
        # não conclui duas vezes
        r = self.client.post(f"/agenda/{ag.pk}/concluir/", {"valor": "200", "forma": self.pix.pk})
        self.assertEqual(Lancamento.objects.count(), 1)

    def test_valor_sem_forma_de_pagamento_e_recusado(self):
        ag = self.marcar()
        r = self.client.post(f"/agenda/{ag.pk}/concluir/", {"valor": "200", "momento_fotos": "depois"})
        self.assertContains(r, "Escolha como a cliente pagou")

    def test_desfazer_devolve_estoque_e_tira_do_caixa(self):
        ag = servicos.concluir(self.marcar(), forma=self.pix)
        self.client.post(f"/agenda/{ag.pk}/desfazer/")
        ag.refresh_from_db()
        self.luva.refresh_from_db()
        self.assertEqual((ag.status, self.luva.quantidade, Lancamento.objects.count()), ("agendado", 10, 0))
        self.assertEqual(self.luva.movimentos.filter(tipo="estorno").count(), 1)

    def test_entrada_de_atendimento_nao_se_apaga_pelo_caixa(self):
        servicos.concluir(self.marcar(), forma=self.pix)
        lanc = Lancamento.objects.get()
        self.client.post(f"/caixa/{lanc.pk}/apagar/")
        self.assertTrue(Lancamento.objects.exists())


class PacoteTests(Base):
    def test_pacote_gasta_sessao_sem_lancar_de_novo_e_controla_saldo(self):
        r = self.client.post("/agenda/pacotes/novo/", {
            "cliente": self.cliente.pk, "procedimento": self.peeling.pk, "sessoes": 2, "valor": "300",
            "data_compra": timezone.localdate(), "valor_pago": "100", "forma": self.pix.pk, "parcelas": 2})
        pacote = Pacote.objects.get()
        self.assertRedirects(r, f"/agenda/pacotes/{pacote.pk}/")
        self.assertEqual((pacote.recebido, pacote.a_receber), (Decimal("100"), Decimal("200")))
        for dias in (-2, -1):
            ag = self.marcar(dias=dias, valor=0)
            self.client.post(f"/agenda/{ag.pk}/concluir/", {"usar_pacote": pacote.pk, "momento_fotos": "depois"})
        self.assertEqual((pacote.usadas, pacote.restantes), (2, 0))
        self.assertEqual(Lancamento.objects.count(), 1)  # só o pagamento do pacote
        self.acido.refresh_from_db()
        self.assertEqual(self.acido.quantidade, 24)  # material sai mesmo em sessão de pacote
        # sem saldo: não dá para usar de novo
        ag = self.marcar(dias=1)
        with self.assertRaises(Exception):
            servicos.concluir(ag, usar_pacote=pacote)
        # pagar o restante
        self.client.post(f"/agenda/pacotes/{pacote.pk}/", {"valor": "200", "forma": self.pix.pk, "parcelas": 2})
        self.assertEqual(pacote.a_receber, 0)

    def test_nao_agenda_mais_sessoes_que_o_pacote_tem(self):
        pacote = Pacote.objects.create(cliente=self.cliente, procedimento=self.peeling, sessoes=1, valor=100)
        base = {"cliente": self.cliente.pk, "procedimento": self.peeling.pk, "duracao": 60, "valor": "0",
                "pacote": pacote.pk, "hora": "10:00"}
        self.client.post("/agenda/novo/", {**base, "data": timezone.localdate() + timedelta(days=1)})
        r = self.client.post("/agenda/novo/", {**base, "data": timezone.localdate() + timedelta(days=2)})
        self.assertContains(r, "não tem mais sessões livres")


class EstoqueTests(Base):
    def test_compra_faz_custo_medio_e_lanca_despesa(self):
        r = self.client.post(f"/estoque/{self.acido.pk}/", {"entrada-quantidade": "30", "entrada-valor_total": "180",
                                                            "entrada-lancar_despesa": "on", "entrada-forma": self.pix.pk})
        self.assertRedirects(r, f"/estoque/{self.acido.pk}/")
        self.acido.refresh_from_db()
        self.assertEqual(self.acido.quantidade, 60)
        self.assertEqual(self.acido.custo_unitario, Decimal("5"))  # (30x4 + 30x6) / 60
        self.assertEqual(Lancamento.objects.get().categoria, "material")

    def test_ajuste_e_alertas(self):
        self.client.post(f"/estoque/{self.luva.pk}/", {"ajuste-saldo_real": "2", "ajuste-motivo": "contagem"})
        self.luva.refresh_from_db()
        self.luva.estoque_minimo = 5
        self.assertEqual(self.luva.quantidade, 2)
        self.assertTrue(self.luva.abaixo_do_minimo)
        self.luva.save()
        self.assertContains(self.client.get("/"), "comprar")

    def test_material_novo_com_estoque_inicial(self):
        self.client.post("/estoque/novo/", {"nome": "Sérum", "unidade": "ml", "estoque_minimo": "5", "custo_unitario": "0",
                                            "ativo": "on", "entrada-quantidade": "50", "entrada-valor_total": "100"})
        m = Material.objects.get(nome="Sérum")
        self.assertEqual((m.quantidade, m.custo_unitario), (50, Decimal("2")))
        self.assertFalse(Lancamento.objects.exists())  # "lançar despesa" desmarcado


class FotosTests(Base):
    def test_foto_reduzida_privada_e_comparacao(self):
        self.client.post(f"/clientes/{self.cliente.pk}/fotos/", {"fotos": [imagem("a.jpg"), imagem("b.jpg")],
                                                                 "momento": "antes", "data": timezone.localdate()})
        fotos = list(Foto.objects.all())
        self.assertEqual(len(fotos), 2)
        from PIL import Image

        self.assertEqual(max(Image.open(fotos[0].imagem.path).size), 2000)
        self.assertEqual(max(Image.open(fotos[0].miniatura.path).size), 480)
        self.assertEqual(self.client.get(f"/clientes/foto/{fotos[0].pk}/").status_code, 200)
        r = self.client.get(f"/clientes/{self.cliente.pk}/comparar/?f={fotos[0].pk}&f={fotos[1].pk}")
        self.assertContains(r, "Antes e depois")
        self.client.logout()
        self.assertEqual(self.client.get(f"/clientes/foto/{fotos[0].pk}/").status_code, 302)


class CaixaTests(Base):
    def test_resumo_do_mes_e_csv(self):
        servicos.concluir(self.marcar(), forma=self.credito)
        self.client.post("/caixa/novo/saida/", {"data": timezone.localdate(), "descricao": "Aluguel", "categoria": "aluguel",
                                                 "valor": "100"})
        r = resumo(Lancamento.objects.all())
        self.assertEqual((r["entradas"], r["taxas"], r["saidas"], r["lucro"]),
                         (Decimal("200"), Decimal("6.98"), Decimal("100"), Decimal("93.02")))
        csv = self.client.get("/caixa/?csv=1").content.decode("utf-8-sig")
        self.assertIn("Aluguel", csv)
        self.assertIn("200,00", csv)
        r = self.client.get("/caixa/faturamento/")
        self.assertContains(r, "Peeling")


class PainelTests(Base):
    def test_retorno_aparece_e_some_quando_agenda(self):
        servicos.concluir(self.marcar(dias=-20), forma=self.pix)  # retorno em 21 dias -> amanhã
        self.assertEqual([r["cliente"] for r in retornos(self.estudio)], [self.cliente])
        self.marcar(dias=3)
        self.assertEqual(retornos(self.estudio), [])

    def test_aniversariante_do_mes(self):
        hoje = timezone.localdate()
        self.cliente.nascimento = hoje.replace(year=1990)
        self.cliente.save()
        self.assertContains(self.client.get("/"), "Aniversariantes")
        self.assertContains(self.client.get("/"), "Maria Silva")


class FinanceiroTrancadoTests(Base):
    """Valores só aparecem com a senha do financeiro (diferente da senha de login)."""

    def setUp(self):
        super().setUp()
        self.ag = self.marcar(dias=1)
        servicos.concluir(self.marcar(dias=-2), forma=self.pix)
        self.pacote = servicos.vender_pacote(Pacote(cliente=self.cliente, procedimento=self.peeling, sessoes=3,
                                                    valor=Decimal("540")), forma=self.pix, valor_pago=Decimal("100"))
        self.trancar()

    def test_paginas_de_valores_pedem_a_senha(self):
        for url in ["/caixa/", "/caixa/faturamento/", "/caixa/formas/", "/caixa/novo/saida/", "/agenda/pacotes/novo/",
                    "/caixa/?csv=1", "/admin/", "/financeiro/senha/"]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith("/financeiro/entrar/"), r["Location"])

    def test_nenhum_valor_aparece_nas_outras_telas(self):
        urls = ["/", "/agenda/", f"/agenda/{self.ag.pk}/", f"/agenda/{self.ag.pk}/concluir/", "/agenda/procedimentos/",
                f"/agenda/procedimentos/{self.peeling.pk}/", "/agenda/pacotes/", f"/agenda/pacotes/{self.pacote.pk}/",
                "/estoque/", f"/estoque/{self.acido.pk}/", "/estoque/novo/", f"/agenda/{self.ag.pk}/editar/",
                f"/clientes/{self.cliente.pk}/?aba=financeiro", f"/clientes/{self.cliente.pk}/?aba=pacotes",
                f"/clientes/{self.cliente.pk}/?aba=agenda", f"/clientes/{self.cliente.pk}/"]
        for url in urls:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for proibido in ("R$ 200", "200,00", "540", "R$ 4,00", 'name="valor"', 'name="preco"',
                                 'name="custo_unitario"', 'name="entrada-valor_total"'):
                    self.assertNotIn(proibido, html)

    def test_senha_errada_bloqueia_e_certa_libera(self):
        r = self.client.post("/financeiro/entrar/", {"senha": "0000", "next": "/caixa/"})
        self.assertContains(r, "Senha incorreta")
        for _ in range(5):
            self.client.post("/financeiro/entrar/", {"senha": "0000"})
        r = self.client.post("/financeiro/entrar/", {"senha": "4321"})
        self.assertContains(r, "Muitas tentativas")
        cache.clear()
        r = self.client.post("/financeiro/entrar/", {"senha": "4321", "next": "/caixa/"})
        self.assertRedirects(r, "/caixa/")
        self.assertContains(self.client.get(f"/agenda/pacotes/{self.pacote.pk}/"), "R$ 540,00")
        self.assertContains(self.client.get("/"), "Trancar")

    def test_tranca_sozinho_depois_do_prazo(self):
        self.abrir_financeiro()
        sessao = self.client.session
        sessao["financeiro_ate"] = 1  # venceu
        sessao.save()
        self.assertEqual(self.client.get("/caixa/").status_code, 302)

    def test_trancado_ainda_agenda_e_conclui_com_o_preco_do_procedimento(self):
        dados = {"cliente": self.cliente.pk, "procedimento": self.peeling.pk, "data": timezone.localdate() + timedelta(days=3),
                 "hora": "09:00", "duracao": 60, "valor": "1"}  # valor mandado à força é ignorado
        self.client.post("/agenda/novo/", dados)
        novo = Agendamento.objects.get(inicio__date=timezone.localdate() + timedelta(days=3))
        self.assertEqual(novo.valor, Decimal("200"))
        r = self.client.post(f"/agenda/{novo.pk}/concluir/", {"forma": self.credito.pk, "valor": "1",
                                                               "momento_fotos": "depois"})
        self.assertRedirects(r, f"/agenda/{novo.pk}/")
        self.assertEqual(Lancamento.objects.get(agendamento=novo).valor, Decimal("200"))
        # desfazer mexe no caixa: pede a senha
        r = self.client.post(f"/agenda/{novo.pk}/desfazer/")
        self.assertTrue(r["Location"].startswith("/financeiro/entrar/"))

    def test_trancado_entrada_de_estoque_sem_custo_e_sem_despesa(self):
        self.client.post(f"/estoque/{self.acido.pk}/", {"entrada-quantidade": "10", "entrada-valor_total": "999",
                                                        "entrada-lancar_despesa": "on"})
        self.acido.refresh_from_db()
        self.assertEqual((self.acido.quantidade, self.acido.custo_unitario), (Decimal("37"), Decimal("4")))
        self.assertFalse(Lancamento.objects.filter(categoria="material").exists())

    def test_primeiro_acesso_cria_a_senha(self):
        self.estudio.definir_senha_financeiro("")
        r = self.client.get("/financeiro/entrar/")
        self.assertContains(r, "Criar senha do financeiro")
        r = self.client.post("/financeiro/entrar/", {"senha": "9876", "confirmar": "9876", "next": "/caixa/"})
        self.assertRedirects(r, "/caixa/")
        self.estudio.refresh_from_db()
        self.assertTrue(self.estudio.confere_senha_financeiro("9876"))
        self.assertNotIn("9876", self.estudio.senha_financeiro)  # guardada criptografada


class UtilTests(TestCase):
    def test_brl_e_whatsapp(self):
        self.assertEqual(brl(Decimal("1234.5")), "R$ 1.234,50")
        self.assertEqual(whatsapp_url("(11) 98765-4321", "Oi"), "https://wa.me/5511987654321?text=Oi")
        self.assertEqual(whatsapp_url(""), "")


class TrocarAcessoTests(TestCase):
    def test_troca_email_e_senha_pelo_comando(self):
        from unittest import mock

        from io import StringIO

        from django.core.management import call_command

        get_user_model().objects.create_user("x", email="velho@a.com", password="senha-forte-123")
        with mock.patch("builtins.input", return_value="Novo@Estudio.com"), \
                mock.patch("getpass.getpass", side_effect=["Outra-senha-2026", "Outra-senha-2026"]):
            call_command("trocar_acesso", stdout=StringIO())
        self.assertTrue(self.client.login(username="novo@estudio.com", password="Outra-senha-2026"))
        self.assertFalse(self.client.login(username="velho@a.com", password="senha-forte-123"))


class AgendaGradeTests(Base):
    def test_semana_e_dia_em_grade_com_blocos_no_horario(self):
        ag = self.marcar(dias=0, hora=14)
        r = self.client.get("/agenda/?modo=semana")
        self.assertContains(r, 'class="cal"')
        self.assertContains(r, "Maria Silva")
        item = next(i for c in r.context["colunas"] for i in c["itens"] if i["ag"] == ag)
        horas = r.context["horas"]
        self.assertEqual(item["top"], (14 - horas[0]) * 64)  # 64 px por hora
        self.assertEqual(item["altura"], 64 - 2)  # 60 minutos
        r = self.client.get(f"/agenda/?modo=dia&data={timezone.localdate():%Y-%m-%d}")
        self.assertEqual(len(r.context["colunas"]), 1)
        self.assertContains(r, "faixa-dias")
        # horário vazio leva ao agendamento já com dia e hora
        self.assertContains(r, f"/agenda/novo/?data={timezone.localdate():%Y-%m-%d}&hora=10:00")

    def test_atendimentos_no_mesmo_horario_ficam_lado_a_lado(self):
        from agenda.views import _faixas

        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        h = lambda m: base + timedelta(minutes=m)  # noqa: E731
        itens = [{"inicio": h(0), "fim": h(60)}, {"inicio": h(30), "fim": h(90)}, {"inicio": h(60), "fim": h(120)},
                 {"inicio": h(180), "fim": h(240)}]
        _faixas(itens)
        self.assertEqual([(i["faixa"], i["faixas"]) for i in itens], [(0, 2), (1, 2), (0, 2), (0, 1)])

    def test_horario_fora_do_expediente_estica_a_grade(self):
        self.marcar(dias=0, hora=6)
        r = self.client.get(f"/agenda/?modo=dia&data={timezone.localdate():%Y-%m-%d}")
        self.assertEqual(r.context["horas"][0], 6)
