/* Agendu: máscaras, CEP automático e preenchimento do agendamento. Sem bibliotecas. */
(function () {
  "use strict";

  function so(d) { return (d || "").replace(/\D/g, ""); }
  var mascaras = {
    telefone: function (v) {
      v = so(v).slice(0, 11);
      if (v.length <= 2) return v.length ? "(" + v : "";
      if (v.length <= 6) return "(" + v.slice(0, 2) + ") " + v.slice(2);
      if (v.length <= 10) return "(" + v.slice(0, 2) + ") " + v.slice(2, 6) + "-" + v.slice(6);
      return "(" + v.slice(0, 2) + ") " + v.slice(2, 7) + "-" + v.slice(7);
    },
    cpf: function (v) {
      v = so(v).slice(0, 11);
      return v.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    },
    cep: function (v) { v = so(v).slice(0, 8); return v.length > 5 ? v.slice(0, 5) + "-" + v.slice(5) : v; }
  };

  document.addEventListener("input", function (e) {
    var m = e.target.getAttribute && e.target.getAttribute("data-mascara");
    if (m && mascaras[m]) e.target.value = mascaras[m](e.target.value);
  });

  // CEP: preenche rua, bairro, cidade e UF (ViaCEP, gratuito)
  document.addEventListener("input", function (e) {
    if (!e.target.hasAttribute || !e.target.hasAttribute("data-cep")) return;
    var cep = so(e.target.value);
    if (cep.length !== 8) return;
    var form = e.target.form;
    fetch("https://viacep.com.br/ws/" + cep + "/json/").then(function (r) { return r.json(); }).then(function (d) {
      if (d.erro) return;
      var mapa = { logradouro: d.logradouro, bairro: d.bairro, cidade: d.localidade, uf: d.uf };
      Object.keys(mapa).forEach(function (nome) {
        var campo = form.querySelector("[name='" + nome + "']");
        if (campo && mapa[nome]) campo.value = mapa[nome];
      });
      var numero = form.querySelector("[name='numero']");
      if (numero) numero.focus();
    }).catch(function () {});
  });

  // Agendamento: ao escolher o procedimento, preenche duração e valor
  document.addEventListener("change", function (e) {
    var dados = e.target.getAttribute && e.target.getAttribute("data-procedimentos");
    if (!dados) return;
    var form = e.target.form, escolhido = e.target.value;
    dados.split("|").forEach(function (item) {
      var p = item.split(":");
      if (p[0] !== escolhido) return;
      var duracao = form.querySelector("[name='duracao']"), valor = form.querySelector("[name='valor']");
      var pacote = form.querySelector("[name='pacote']");
      if (duracao) duracao.value = p[1];
      if (valor && !(pacote && pacote.value)) valor.value = p[2];
    });
  });

  // Concluir: com pacote, esconde os campos de pagamento
  function alternarPagamento() {
    var sel = document.querySelector("[name='usar_pacote']");
    var bloco = document.getElementById("pagamento");
    if (sel && bloco) bloco.hidden = !!sel.value;
  }
  document.addEventListener("change", function (e) { if (e.target.name === "usar_pacote") alternarPagamento(); });
  document.addEventListener("DOMContentLoaded", alternarPagamento);

  // Comparar fotos: no máximo duas marcadas
  document.addEventListener("change", function (e) {
    if (e.target.name !== "f") return;
    var marcadas = document.querySelectorAll("input[name='f']:checked");
    if (marcadas.length > 2) e.target.checked = false;
    var botao = document.getElementById("btn-comparar");
    if (botao) botao.disabled = document.querySelectorAll("input[name='f']:checked").length !== 2;
  });
})();

/* Pagamento: mostra "Parcelado em" só quando a forma escolhida é parcelada */
(function () {
  "use strict";
  function atualizar(bloco) {
    var parcelaveis = (bloco.getAttribute("data-parcelaveis") || "").split(",");
    var marcado = bloco.querySelector("input[type=radio]:checked");
    var parcelas = bloco.querySelector("[data-so-parcelado]");
    if (parcelas) parcelas.hidden = !(marcado && parcelaveis.indexOf(marcado.value) !== -1);
  }
  document.addEventListener("change", function (e) {
    var bloco = e.target.closest && e.target.closest("[data-parcelaveis]");
    if (bloco) atualizar(bloco);
  });
  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll("[data-parcelaveis]"), atualizar);
  });
})();
