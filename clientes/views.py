from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from agenda.models import Agendamento
from core.models import Estudio
from core.utils import formatar_mensagem
from financeiro.models import resumo

from .forms import ClienteForm, EvolucaoForm, FichaForm, FotosForm
from .models import Cliente, Evolucao, Ficha, Foto

ABAS = ["resumo", "ficha", "evolucao", "fotos", "agenda", "pacotes", "financeiro"]


def lista(request):
    termo = request.GET.get("q", "").strip()
    qs = Cliente.objects.annotate(ultima_visita=Max("agendamentos__inicio",
                                                    filter=Q(agendamentos__status=Agendamento.CONCLUIDO)))
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(telefone__icontains=termo) | Q(email__icontains=termo)
                       | Q(cpf__icontains=termo))
    if request.GET.get("inativos") != "1":
        qs = qs.filter(ativo=True)
    pagina = Paginator(qs.order_by("nome"), 30).get_page(request.GET.get("pagina"))
    return render(request, "clientes/lista.html", {"pagina": pagina, "termo": termo})


def editar(request, pk=None):
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        cliente = form.save()
        Ficha.objects.get_or_create(cliente=cliente)
        messages.success(request, f"{cliente} salva.")
        if pk is None:
            return redirect(f"/clientes/{cliente.pk}/?aba=ficha")
        return redirect("clientes:detalhe", cliente.pk)
    return render(request, "clientes/form.html", {"form": form, "cliente": cliente})


def detalhe(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    ficha, _ = Ficha.objects.get_or_create(cliente=cliente)
    aba = request.GET.get("aba", "resumo")
    if aba not in ABAS:
        aba = "resumo"
    estudio = Estudio.atual()
    agora = timezone.now()
    agendamentos = cliente.agendamentos.select_related("procedimento", "pacote").order_by("-inicio")
    proximos = [a for a in agendamentos if a.em_aberto and a.inicio >= agora][::-1]
    concluidos = [a for a in agendamentos if a.status == Agendamento.CONCLUIDO]
    ctx = {
        "cliente": cliente, "ficha": ficha, "aba": aba, "abas": ABAS,
        "agendamentos": agendamentos, "proximos": proximos,
        "ultima_visita": concluidos[0] if concluidos else None,
        "total_visitas": len(concluidos),
        "pacotes": cliente.pacotes.select_related("procedimento"),
        "evolucoes": cliente.evolucoes.prefetch_related("fotos").select_related("agendamento__procedimento"),
        "fotos": cliente.fotos.all(),
        "lancamentos": cliente.lancamentos.select_related("forma"),
        "financeiro": resumo(cliente.lancamentos.all()),
        "media_visita": (resumo(cliente.lancamentos.all())["entradas"] / len(concluidos)) if concluidos else 0,
        "msg_aniversario": cliente.whatsapp(formatar_mensagem(
            estudio.msg_aniversario, nome=cliente.primeiro_nome, estudio=estudio.nome)),
    }
    if aba == "ficha":
        ctx["form_ficha"] = FichaForm(instance=ficha)
    if aba == "evolucao":
        ctx["form_evolucao"] = EvolucaoForm(initial={"data": timezone.localdate()})
    if aba == "fotos":
        ctx["form_fotos"] = FotosForm(initial={"data": timezone.localdate()})
    return render(request, "clientes/detalhe.html", ctx)


@require_POST
def salvar_ficha(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    ficha, _ = Ficha.objects.get_or_create(cliente=cliente)
    form = FichaForm(request.POST, instance=ficha)
    if form.is_valid():
        form.save()
        messages.success(request, "Ficha salva.")
    else:
        messages.error(request, "Confira os campos da ficha.")
    return redirect(f"/clientes/{pk}/?aba=ficha")


@require_POST
def nova_evolucao(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    form = EvolucaoForm(request.POST, request.FILES)
    if form.is_valid():
        evo = form.save(commit=False)
        evo.cliente = cliente
        evo.save()
        for arquivo in form.cleaned_data["fotos"]:
            Foto.objects.create(cliente=cliente, evolucao=evo, imagem=arquivo,
                                momento=form.cleaned_data["momento"], data=evo.data)
        messages.success(request, "Evolução registrada.")
    else:
        messages.error(request, "Não salvei: " + "; ".join(e for erros in form.errors.values() for e in erros))
    return redirect(f"/clientes/{pk}/?aba=evolucao")


@require_POST
def apagar_evolucao(request, pk):
    evo = get_object_or_404(Evolucao, pk=pk)
    cliente_id = evo.cliente_id
    evo.delete()  # as fotos continuam na galeria
    messages.success(request, "Evolução apagada (as fotos continuam na galeria).")
    return redirect(f"/clientes/{cliente_id}/?aba=evolucao")


@require_POST
def enviar_fotos(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    form = FotosForm(request.POST, request.FILES)
    if form.is_valid():
        d = form.cleaned_data
        for arquivo in d["fotos"]:
            Foto.objects.create(cliente=cliente, imagem=arquivo, momento=d["momento"], regiao=d["regiao"],
                                data=d["data"], legenda=d["legenda"])
        messages.success(request, f"{len(d['fotos'])} foto(s) enviada(s).")
    else:
        messages.error(request, "Não salvei: " + "; ".join(e for erros in form.errors.values() for e in erros))
    return redirect(f"/clientes/{pk}/?aba=fotos")


@require_POST
def apagar_foto(request, pk):
    foto = get_object_or_404(Foto, pk=pk)
    cliente_id = foto.cliente_id
    foto.delete()
    messages.success(request, "Foto apagada.")
    return redirect(f"/clientes/{cliente_id}/?aba=fotos")


def foto_arquivo(request, pk, tamanho="grande"):
    """Entrega a foto só para quem está logado (o middleware garante). Nunca por link público."""
    foto = get_object_or_404(Foto, pk=pk)
    arquivo = foto.miniatura if tamanho == "mini" and foto.miniatura else foto.imagem
    resposta = FileResponse(arquivo.open("rb"), content_type="image/jpeg")
    resposta["Cache-Control"] = "private, max-age=86400"
    return resposta


def comparar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    ids = request.GET.getlist("f")[:2]
    fotos = list(cliente.fotos.filter(pk__in=ids).order_by("data", "pk"))
    if len(fotos) != 2:
        messages.error(request, "Marque duas fotos para comparar.")
        return redirect(f"/clientes/{pk}/?aba=fotos")
    dias = (fotos[1].data - fotos[0].data).days
    return render(request, "clientes/comparar.html", {"cliente": cliente, "fotos": fotos, "dias": dias})


def imprimir_ficha(request, pk):
    """Ficha de anamnese + termo de consentimento e de uso de imagem, para imprimir e assinar."""
    cliente = get_object_or_404(Cliente, pk=pk)
    ficha, _ = Ficha.objects.get_or_create(cliente=cliente)
    return render(request, "clientes/imprimir_ficha.html", {
        "cliente": cliente, "ficha": ficha, "estudio": Estudio.atual(), "hoje": timezone.localdate(),
    })

