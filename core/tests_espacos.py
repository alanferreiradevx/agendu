"""Vários espaços no mesmo Agendu: cada profissional só vê o seu; só o master libera acessos."""

import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from agenda import servicos
from agenda.models import Agendamento, Pacote, Procedimento
from clientes.models import Cliente, Foto
from core.models import Estudio
from estoque.models import Material
from financeiro.models import Lancamento

from .tests import Base, imagem

User = get_user_model()


class OutroEspacoBase(Base):
    """Ana (espaço A, da classe Base) tem dados; Bia (espaço B) não pode ver nenhum deles."""

    def setUp(self):
        super().setUp()
        self.ag = self.marcar(dias=1, hora=10)
        servicos.concluir(self.marcar(dias=-1), forma=self.pix)
        self.pacote = servicos.vender_pacote(Pacote(cliente=self.cliente, procedimento=self.peeling, sessoes=3,
                                                    valor=Decimal("300")), forma=self.pix)
        self.foto = Foto.objects.create(cliente=self.cliente, imagem=imagem(), momento="antes")
        self.bia = User.objects.create_user("bia@b.com", email="bia@b.com", password="senha-forte-123")
        self.espaco_b = Estudio.objects.create(nome="Espaço Bia", dono=self.bia)
        self.espaco_b.criar_formas_padrao()
        self.espaco_b.definir_senha_financeiro("1111")

    def entrar_como_bia(self):
        self.client.force_login(self.bia)
        self.client.post("/financeiro/entrar/", {"senha": "1111"})


class IsolamentoTests(OutroEspacoBase):
    def test_bia_nao_abre_nada_do_espaco_da_ana(self):
        self.entrar_como_bia()
        urls = [
            f"/clientes/{self.cliente.pk}/", f"/clientes/{self.cliente.pk}/editar/", f"/clientes/{self.cliente.pk}/ficha/imprimir/",
            f"/clientes/foto/{self.foto.pk}/", f"/clientes/foto/{self.foto.pk}/mini/",
            f"/clientes/{self.cliente.pk}/comparar/?f={self.foto.pk}&f={self.foto.pk}",
            f"/agenda/{self.ag.pk}/", f"/agenda/{self.ag.pk}/editar/", f"/agenda/{self.ag.pk}/concluir/",
            f"/agenda/procedimentos/{self.peeling.pk}/", f"/agenda/pacotes/{self.pacote.pk}/",
            f"/estoque/{self.luva.pk}/", f"/estoque/{self.luva.pk}/editar/",
            f"/caixa/{Lancamento.objects.filter(estudio=self.estudio).first().pk}/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        for url in [f"/clientes/{self.cliente.pk}/ficha/", f"/clientes/{self.cliente.pk}/fotos/",
                    f"/clientes/foto/{self.foto.pk}/apagar/", f"/agenda/{self.ag.pk}/status/cancelado/",
                    f"/agenda/{self.ag.pk}/apagar/", f"/agenda/{self.ag.pk}/forma/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)
        self.ag.refresh_from_db()
        self.assertEqual(self.ag.status, "agendado")
        self.assertTrue(Foto.objects.filter(pk=self.foto.pk).exists())

    def test_listas_e_telas_da_bia_vem_vazias(self):
        self.entrar_como_bia()
        for url in ["/", "/clientes/", "/clientes/?q=maria", "/agenda/", "/agenda/?modo=dia", "/agenda/pacotes/",
                    "/agenda/procedimentos/", "/estoque/", "/caixa/", "/caixa/faturamento/", "/agenda/novo/",
                    "/caixa/?csv=1", "/caixa/formas/"]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode("utf-8-sig")
                for dado_da_ana in ("Maria Silva", "Peeling", "Ácido", "Luva"):
                    self.assertNotIn(dado_da_ana, html)
        self.assertRedirects(self.client.get("/busca/?q=Maria"), "/clientes/?q=Maria", fetch_redirect_response=False)

    def test_bia_nao_consegue_usar_dados_da_ana_nos_formularios(self):
        self.entrar_como_bia()
        r = self.client.post("/agenda/novo/", {"cliente": self.cliente.pk, "procedimento": self.peeling.pk,
                                               "data": timezone.localdate() + timedelta(days=2), "hora": "10:00",
                                               "duracao": 60, "valor": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Agendamento.objects.filter(estudio=self.espaco_b).exists())
        self.client.post("/caixa/novo/entrada/", {"data": timezone.localdate(), "descricao": "x", "categoria": "produto",
                                                  "valor": "10", "forma": self.pix.pk, "cliente": self.cliente.pk})
        self.assertFalse(Lancamento.objects.filter(estudio=self.espaco_b).exists())

    def test_cada_espaco_tem_sua_agenda_e_seus_nomes(self):
        # mesmo horário em espaços diferentes não conflita
        maria_b = Cliente.objects.create(estudio=self.espaco_b, nome="Outra")
        proc_b = Procedimento.objects.create(estudio=self.espaco_b, nome="Peeling", preco=100)  # mesmo nome: pode
        ag_b = Agendamento(cliente=maria_b, procedimento=proc_b, inicio=self.ag.inicio, fim=self.ag.fim)
        ag_b.full_clean()
        ag_b.save()
        self.assertEqual(ag_b.estudio, self.espaco_b)
        # no mesmo espaço, nome repetido não
        self.client.force_login(self.user)
        r = self.client.post("/agenda/procedimentos/novo/", {"nome": "peeling", "duracao_min": 30, "preco": "1",
                                                             "cor": "#8e5bb5", "ativo": "on", "mat-TOTAL_FORMS": 0,
                                                             "mat-INITIAL_FORMS": 0})
        self.assertContains(r, "Já existe um cadastro com este nome")
        self.assertEqual(Material.objects.filter(nome="Luva").count(), 1)

    def test_espaco_novo_comeca_com_as_formas_de_pagamento(self):
        self.assertEqual(self.espaco_b.formas_pagamento.count(), 5)


class BloqueioTests(OutroEspacoBase):
    def test_bloqueado_nao_entra_e_ve_o_motivo(self):
        self.espaco_b.ativo = False
        self.espaco_b.save()
        self.client.force_login(self.bia)
        r = self.client.get("/", follow=True)
        self.assertContains(r, "Seu acesso ao Agendu está bloqueado")
        self.assertEqual(self.client.get("/clientes/").status_code, 302)  # saiu

    def test_vencido_nao_entra(self):
        self.espaco_b.valido_ate = timezone.localdate() - timedelta(days=1)
        self.espaco_b.save()
        self.client.logout()
        r = self.client.post("/entrar/", {"username": "bia@b.com", "password": "senha-forte-123"}, follow=True)
        self.assertContains(r, "venceu em")

    def test_vencendo_mostra_aviso(self):
        self.espaco_b.valido_ate = timezone.localdate() + timedelta(days=3)
        self.espaco_b.save()
        self.client.force_login(self.bia)
        self.assertContains(self.client.get("/"), "Seu acesso ao Agendu vence em 3 dia(s)")


class MasterTests(OutroEspacoBase):
    def setUp(self):
        super().setUp()
        self.master = User.objects.create_superuser("alan@ativix.co", "alan@ativix.co", "senha-forte-123")

    def test_so_o_master_ve_a_area_de_acessos(self):
        self.client.force_login(self.bia)
        self.assertEqual(self.client.get("/acessos/").status_code, 403)
        self.assertNotContains(self.client.get("/"), "/acessos/")
        self.client.force_login(self.master)
        r = self.client.get("/acessos/")
        self.assertContains(r, "Espaço Bia")
        self.assertContains(r, "Studio Ana")
        self.assertNotContains(r, "Maria Silva")  # nada de pacientes, só números de uso
        self.assertContains(self.client.get("/"), "/acessos/")

    def test_master_ganha_espaco_proprio_e_nao_aparece_na_lista(self):
        self.client.force_login(self.master)
        self.client.get("/")
        meu = Estudio.objects.get(dono=self.master)
        self.assertEqual(meu.formas_pagamento.count(), 5)
        self.assertNotIn(meu, self.client.get("/acessos/").context["espacos"])
        self.assertEqual(self.client.get(f"/acessos/{meu.pk}/").status_code, 404)

    def test_liberar_acesso_com_convite_e_a_profissional_cria_a_senha(self):
        self.client.force_login(self.master)
        r = self.client.post("/acessos/novo/", {"nome": "Clínica Carla", "profissional": "Carla Mendes",
                                                "email": "Carla@Clinica.com", "telefone": "(11) 99999-0000",
                                                "plano": "Mensal", "valor_mensal": "89.90", "ativo": "on",
                                                "valido_ate": timezone.localdate() + timedelta(days=30)}, follow=True)
        espaco = Estudio.objects.get(nome="Clínica Carla")
        carla = espaco.dono
        self.assertEqual((carla.email, carla.has_usable_password(), carla.is_superuser), ("carla@clinica.com", False, False))
        self.assertEqual(espaco.situacao, "convite")
        self.assertContains(r, "Enviar pelo WhatsApp")
        link = re.search(r"https?://[^\s<\"]+/convite/[^\s<\"]+/", r.content.decode()).group(0)
        caminho = link.split("testserver", 1)[1]
        # e-mail repetido é recusado
        r2 = self.client.post("/acessos/novo/", {"nome": "X", "profissional": "X", "email": "carla@clinica.com",
                                                 "valor_mensal": "0", "ativo": "on"})
        self.assertContains(r2, "Já existe um acesso com este e-mail")
        # a Carla abre o link, cria a senha e já entra
        self.client.logout()
        self.assertContains(self.client.get(caminho), "Crie sua senha")
        r = self.client.post(caminho, {"new_password1": "Minha-Senha-2026", "new_password2": "Minha-Senha-2026"})
        self.assertRedirects(r, "/")
        self.client.logout()
        self.assertTrue(self.client.login(username="carla@clinica.com", password="Minha-Senha-2026"))
        self.client.logout()
        self.assertContains(self.client.get(caminho), "Link expirado ou já usado")  # só vale uma vez

    def test_bloquear_liberar_renovar_e_link_de_senha(self):
        self.client.force_login(self.master)
        base = f"/acessos/{self.espaco_b.pk}/"
        self.client.post(base + "bloquear/")
        self.espaco_b.refresh_from_db()
        self.assertFalse(self.espaco_b.ativo)
        self.client.post(base + "liberar/")
        self.client.post(base + "renovar30/")
        self.espaco_b.refresh_from_db()
        self.assertTrue(self.espaco_b.ativo)
        self.assertEqual(self.espaco_b.valido_ate, timezone.localdate() + timedelta(days=30))
        self.client.post(base + "renovar30/")  # soma a partir do vencimento atual
        self.espaco_b.refresh_from_db()
        self.assertEqual(self.espaco_b.valido_ate, timezone.localdate() + timedelta(days=60))
        r = self.client.post(base + "senha/", follow=True)
        self.assertContains(r, "Link para criar senha nova")
        self.assertContains(r, "/convite/")
