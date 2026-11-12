# Agendu (contexto do projeto)

Sistema do Alan para atendimento de **estética**: agenda, clientes (ficha, evolução, fotos), pacotes, caixa,
faturamento e estoque. **Um usuário só** (a própria profissional). Responda em português do Brasil; Alan está
aprendendo Python/Django: explique de forma didática e passe comandos prontos para Windows (PowerShell, venv em `.venv`).

Projeto **separado do Ativix** (`C:\Users\mixcom\Downloads\ativix.co-main`), mas no mesmo servidor e com a mesma
base técnica. Não misturar código, banco nem usuários dos dois.

## Decisões
- Django 5.2 LTS, templates + CSS próprio (sem framework JS), `static/js/app.js` com máscaras, CEP (ViaCEP),
  preenchimento do agendamento e comparação de fotos. SQLite em dev, PostgreSQL em produção (`DB_*`).
- Marca **Agendu** ("by Ativix" discreto): berinjela `--primaria #3d2352` / `--primaria-escura #2a1838` e rosé
  `--destaque #e2a48c` / `--destaque-escuro #c9785f`. Verde/laranja/vermelho só para status; verde WhatsApp só no
  botão do WhatsApp. Fontes Manrope e JetBrains Mono. Logos SVG em `static/img/` (`logo.svg`, `logo-branco.svg`, `icone.svg`).
- Celular primeiro: menu lateral vira gaveta e aparece a barra de baixo (Painel, Agenda, +, Clientes, Caixa).
- **Todo o sistema exige login** (`core.middleware.LoginObrigatorioMiddleware`; livres só `/entrar/`, `/static/`, `/admin/`).
  Login com bloqueio (5 erros por IP = 15 min, cache em arquivo).
- **Fotos privadas** (LGPD): `config/storage.py` (`PRIVADO_ROOT`), servidas só por `clientes:foto`/`foto_mini`.
  Nunca criar `/media/` público. Fotos são reduzidas para 2000 px + miniatura 480 px ao salvar (`Foto.save`).
- WhatsApp: só link `wa.me` com texto pronto (`core.utils.whatsapp_url`), sem API paga. Textos em `core.Estudio`
  (`Estudio.atual()`, registro único com dados do espaço, logo, horário e mensagens).
- Dinheiro: `Decimal`, `core.utils.centavos/brl`, filtro `|dinheiro`. Não usar o filtro `add` do Django com valores
  (ele converte para inteiro e perde os centavos): calcule na view.

## Regras de negócio
- **Valores só com a senha do financeiro** (pedido do Alan em 12/11/2026; diferente da senha de login, guardada com hash em
  `Estudio.senha_financeiro`). `core/financeiro.py`: `liberado(request)`, `@financeiro_obrigatorio`, `FinanceiroMiddleware`
  (renova a cada página, tranca depois de `FINANCEIRO_MINUTOS`=15 parado, tranca `/admin/`), `{{ financeiro_liberado }}`
  nos templates e `{% valor x %}` (mostra `R$ •••` trancado). Caixa, faturamento, formas/taxas, vender pacote, receber
  pacote e desfazer conclusão exigem a senha. Trancado, os formulários **removem** os campos de valor (agendamento usa o
  preço do procedimento; concluir usa o valor combinado; estoque entra sem custo e sem despesa). **Toda tela nova com
  dinheiro segue a mesma regra, com teste** (`FinanceiroTrancadoTests`). Esqueceu: `agendu-manage redefinir_senha_financeiro`.
- **Como vai pagar / como pagou** (pedido do Alan): `Agendamento.forma_prevista` + `parcelas_previstas` (no agendamento) e o
  `Lancamento.forma` + `parcelas` (na conclusão, já vem marcado com o previsto). Formas em botões e parcelas 2x-12x só se a
  `FormaPagamento.parcelavel`: use `financeiro/pagamento.py` (`preparar`, `campo_parcelas`, `ajustar_parcelas`) e o
  template `_pagamento.html` em todo formulário novo com forma de pagamento. A forma aparece mesmo com o financeiro trancado.
- Painel: agendamentos primeiro (hoje e próximos 6 dias) e nenhum valor em dinheiro.
- **Estoque só muda por `estoque.models.movimentar()`** (grava `Movimento` e atualiza a quantidade; compra com custo
  faz média ponderada). Pode ficar negativo (não trava o atendimento; o painel avisa).
- **Concluir/desfazer atendimento só por `agenda/servicos.py`** (`concluir`, `desfazer_conclusao`), em transação:
  baixa os `ProcedimentoMaterial`, guarda `custo_material`, lança `Lancamento` (categoria `atendimento`, taxa da
  `FormaPagamento`) ou usa sessão de `Pacote`; evolução e fotos opcionais. Entrada de atendimento não se apaga pelo caixa.
- Pacote: `vender_pacote` / `receber_pacote` lançam a entrada (categoria `pacote`); sessão usada = agendamento
  concluído com o pacote; no faturamento, sessão de pacote vale `valor / sessões`.
- Agendamento em aberto (`agendado`/`confirmado`) não pode sobrepor outro em aberto (`Agendamento.clean`).
- Lucro = entradas − taxas − despesas (`financeiro.models.resumo`).
- Retorno: `Procedimento.retorno_dias`; `agenda/consultas.retornos()` usa o último atendimento concluído de cada
  cliente e some quando ela tem horário futuro.

## Estrutura
`core` (painel, configurações, login, utils, `dados_demo`, testes em `core/tests.py`), `clientes` (Cliente, Ficha,
Evolucao, Foto), `agenda` (Procedimento, ProcedimentoMaterial, Pacote, Agendamento, servicos, consultas),
`estoque` (Material, Movimento), `financeiro` (FormaPagamento com 5 formas criadas na migração 0002, Lancamento).

## Produção
**No ar desde 12/11/2026:** `https://agendu.ativix.co` (certificado Let's Encrypt registrado sem e-mail; renova sozinho) na VPS Hostinger do Ativix (`root@187.41.119.140`). `/srv/agendu` (app, venv, dados/privado,
dados/staticfiles, dados/cache, backups), segredos `/etc/agendu/env`, serviço `agendu` (gunicorn **127.0.0.1:8002**;
o Ativix usa 8001), site nginx `agendu`, atalhos `agendu-manage` (roda como usuário `agendu`) e `agendu-backup`
(cron 3h30). Instalar: `.\deploy\enviar.ps1 -Servidor root@187.41.119.140 -Instalar -Dominio agendu.ativix.co -Email ...`;
atualizar: `.\deploy\enviar.ps1 -Servidor root@187.41.119.140` (roda os testes antes). `.sh` com LF, `.ps1` com BOM.

## Comandos
```
.venv\Scripts\activate
python manage.py migrate
python manage.py dados_demo     # demo / Agendu#2026, senha do financeiro 1234 (só com DEBUG)
python manage.py runserver 8002
python manage.py test           # rodar sempre antes de entregar
```
