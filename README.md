# Agendu

Agenda, clientes, caixa e estoque para quem atende estética, usado principalmente pelo celular.
Você (master) libera o acesso de outras profissionais: cada uma tem o próprio espaço, separado.

Endereço: **https://agendu.ativix.co** (mesmo servidor do Ativix, mas separado:
outra pasta, outro banco, outro serviço).

## O que tem

- **Agenda** da semana (no celular vira lista por dia). Agendar com cliente,
  procedimento, data, hora, duração e valor (duração e valor vêm do procedimento).
  Avisa se o horário bate com outro atendimento. Situações: agendado, confirmado,
  concluído, faltou, cancelado.
- **Como vai pagar e como pagou**: ao agendar, escolha PIX, Dinheiro, Cartão de débito, Cartão de crédito à
  vista ou parcelado (2x a 12x). Ao concluir, já vem marcado; se pagou de outro jeito, é só trocar.
- **Concluir atendimento** faz tudo de uma vez:
  1. tira do estoque os materiais do procedimento (e guarda quanto custaram);
  2. lança a entrada no caixa com a taxa da forma de pagamento (ou gasta uma sessão do pacote);
  3. grava a evolução e as fotos da sessão.
  Errou? "Desfazer conclusão" devolve o material e tira a entrada do caixa.
- **Clientes**: cadastro com CEP automático, **ficha de anamnese** estética
  (tipo de pele, fototipo, gestante, alergias, ácidos...), pontos de atenção em
  vermelho no topo da cliente e no atendimento, **evolução** (linha do tempo),
  **fotos** privadas (reduzidas no envio; só abrem com login) e **antes e depois**
  lado a lado. Ficha + termo de consentimento + autorização de uso de imagem
  para imprimir e assinar.
- **Pacotes** de sessões: valor, sessões, validade, quanto já foi pago e quanto falta.
- **Procedimentos**: preço, duração, retorno (dias), cor na agenda, cuidados
  pós-procedimento e os **materiais gastos por sessão** (custo e "sobra" calculados).
- **Estoque**: materiais com unidade (ml, g, unidade...), mínimo, validade,
  custo médio. Entrada de compra (pode lançar a despesa no caixa), ajuste de contagem,
  histórico de movimentações. Alerta de comprar, vencendo e vencido no painel.
- **Caixa**: entradas e despesas do mês, taxas da maquininha, lucro, despesas por
  tipo, Excel (CSV). **Faturamento**: por procedimento (receita, taxas, materiais,
  sobra), formas de pagamento e os últimos 6 meses.
- **WhatsApp com 1 clique** (grátis, sem API): lembrete do horário, cuidados pós,
  retorno e parabéns. Abre o WhatsApp com a mensagem pronta; você confere e envia.
  Textos editáveis em Configurações.
- **Painel**: primeiro os agendamentos (hoje e próximos dias), depois os que passaram sem
  fechar, números do mês (sem dinheiro), **hora do retorno** (quem chamar de volta),
  aniversariantes e alertas de estoque.
- **Senha do financeiro**: tudo que mostra dinheiro (caixa, faturamento, taxas, preços, custos do
  estoque, valores de pacotes e atendimentos) fica trancado atrás de uma senha separada da de login.
  Tranca sozinho depois de 15 minutos sem usar, ou no botão "Trancar". Trancado, dá para agendar e
  concluir atendimentos normalmente (o valor usado é o do procedimento, sem aparecer na tela).
  Esqueceu a senha: `agendu-manage redefinir_senha_financeiro email@da.profissional` no servidor.

- **Acessos** (só o master): liberar acesso para uma profissional (ela recebe um link pelo WhatsApp e cria a
  própria senha), bloquear/liberar, renovar +30 dias ou +1 ano, plano e valor mensal, link de senha nova.
  Acesso vencido ou bloqueado não entra (os dados ficam guardados). Você não vê os dados das profissionais.

## Rodar no computador (Windows)

```powershell
cd C:\Users\mixcom\Downloads\agendu
.venv\Scripts\activate
python manage.py migrate
python manage.py dados_demo      # exemplo: e-mail demo@agendu.local / senha Agendu#2026 / financeiro 1234
python manage.py runserver 8002  # abre em http://127.0.0.1:8002
python manage.py test            # rodar sempre antes de subir
```

Primeira vez numa máquina nova: `py -3.12 -m venv .venv` e
`.venv\Scripts\pip install -r requirements.txt`.

## Colocar no ar

1. **DNS** (uma vez): na Hostinger, zona DNS de `ativix.co`, crie um registro
   **A** com nome `agendu` apontando para `187.41.119.140`.
2. **Instalar** (uma vez):
   `.\deploy\enviar.ps1 -Servidor root@187.41.119.140 -Instalar -Dominio agendu.ativix.co -Email seu@email.com`
3. **Criar seu usuário** (uma vez; você mesmo digita a senha). **Preencha o e-mail**: é com ele que se entra:
   `ssh -t root@187.41.119.140 agendu-manage createsuperuser`
4. **Atualizar** depois de mudar o código:
   `.\deploy\enviar.ps1 -Servidor root@187.41.119.140`

No servidor: código em `/srv/agendu/app`, fotos em `/srv/agendu/dados/privado`,
segredos em `/etc/agendu/env`, serviço `agendu` (gunicorn em 127.0.0.1:8002),
atalhos `agendu-manage` e `agendu-backup` (backup diário às 3h30, 14 dias).
Log: `journalctl -u agendu -n 50`.
