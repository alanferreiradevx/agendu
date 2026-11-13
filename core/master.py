"""
Área "Acessos": só o master (você) libera, bloqueia e renova o acesso das profissionais.

Cada profissional ganha um espaço próprio (agenda, clientes, caixa e estoque separados).
O master NÃO vê os dados delas: aqui só aparecem nome, e-mail, situação e números de uso.
A pessoa recebe um link de convite e cria a própria senha (ninguém digita a senha de outro).
"""

from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST

from .campos import DATA, DINHEIRO
from .espaco import master_obrigatorio
from .models import Estudio
from .utils import formatar_mensagem, whatsapp_url

User = get_user_model()

MSG_CONVITE = (
    "Olá, {nome}! Seu acesso ao Agendu foi liberado. Crie sua senha neste link (vale por 7 dias): {link}\n\n"
    "Depois é só entrar em {site} com o e-mail {email}."
)
MSG_SENHA = "Olá, {nome}! Para criar uma senha nova no Agendu, use este link (vale por 7 dias): {link}"


class AcessoForm(forms.ModelForm):
    email = forms.EmailField(label="E-mail de login", help_text="É com ele que a profissional entra no Agendu.")

    class Meta:
        model = Estudio
        fields = ["nome", "profissional", "email", "telefone", "plano", "valor_mensal", "valido_ate", "ativo", "anotacoes"]
        labels = {"profissional": "nome da profissional", "telefone": "WhatsApp"}
        widgets = {"valido_ate": DATA, "valor_mensal": DINHEIRO, "anotacoes": forms.Textarea(attrs={"rows": 3}),
                   "telefone": forms.TextInput(attrs={"data-mascara": "telefone", "inputmode": "tel"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profissional"].required = True
        if self.instance.dono_id:
            self.initial["email"] = self.instance.dono.email
        else:
            self.initial.setdefault("valido_ate", timezone.localdate() + timedelta(days=30))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        outros = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email))
        if self.instance.dono_id:
            outros = outros.exclude(pk=self.instance.dono_id)
        if outros.exists():
            raise forms.ValidationError("Já existe um acesso com este e-mail.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        estudio = super().save(commit=False)
        email = self.cleaned_data["email"]
        if estudio.dono_id:
            dono = estudio.dono
            dono.email = dono.username = email
            dono.first_name = estudio.profissional[:150]
            dono.save(update_fields=["email", "username", "first_name"])
        else:
            dono = User(username=email, email=email, first_name=estudio.profissional[:150])
            dono.set_unusable_password()  # a senha quem cria é ela, pelo link do convite
            dono.save()
            estudio.dono = dono
        estudio.save()
        estudio.criar_formas_padrao()
        return estudio


def _link(request, usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    return request.build_absolute_uri(reverse("aceitar_convite", args=[uid, token]))


def _mensagem_link(request, estudio, modelo):
    link = _link(request, estudio.dono)
    texto = formatar_mensagem(modelo, nome=(estudio.profissional or estudio.nome).split()[0], link=link,
                              email=estudio.dono.email, site=request.build_absolute_uri("/"))
    return {"link": link, "texto": texto, "whatsapp": whatsapp_url(estudio.telefone, texto)}


@master_obrigatorio
def acessos(request):
    espacos = (Estudio.objects.filter(dono__is_superuser=False).select_related("dono")
               .annotate(n_clientes=Count("clientes", distinct=True), n_agendamentos=Count("agendamentos", distinct=True))
               .order_by("nome"))
    filtro = request.GET.get("situacao", "")
    lista = [e for e in espacos if not filtro or e.situacao == filtro]
    ativos = [e for e in espacos if e.pode_entrar]
    return render(request, "core/master_acessos.html", {
        "espacos": lista, "filtro": filtro, "total": len(espacos), "ativos": len(ativos),
        "receita": sum((e.valor_mensal for e in ativos), 0),
        "vencendo": sum(1 for e in espacos if e.pode_entrar and e.dias_para_vencer is not None and e.dias_para_vencer <= 7),
        "bloqueados": sum(1 for e in espacos if e.situacao in ("bloqueado", "vencido")),
    })


@master_obrigatorio
def acesso_editar(request, pk=None):
    estudio = get_object_or_404(Estudio, pk=pk, dono__is_superuser=False) if pk else Estudio(nome="")
    form = AcessoForm(request.POST or None, instance=estudio)
    if request.method == "POST" and form.is_valid():
        novo = pk is None
        estudio = form.save()
        if novo:
            messages.success(request, f"Acesso de {estudio.profissional} criado. Mande o link do convite abaixo.")
            return redirect(f"{reverse('acesso_editar', args=[estudio.pk])}?link=convite")
        messages.success(request, "Acesso salvo.")
        return redirect("acesso_editar", estudio.pk)
    ctx = {"form": form, "estudio": estudio if pk else None}
    if pk and request.GET.get("link") in ("convite", "senha"):
        ctx["envio"] = _mensagem_link(request, estudio, MSG_CONVITE if request.GET["link"] == "convite" else MSG_SENHA)
        ctx["tipo_link"] = request.GET["link"]
    return render(request, "core/master_acesso.html", ctx)


@require_POST
@master_obrigatorio
def acesso_acao(request, pk, acao):
    estudio = get_object_or_404(Estudio, pk=pk, dono__is_superuser=False)
    if acao == "bloquear":
        estudio.ativo = False
        estudio.save(update_fields=["ativo"])
        messages.success(request, f"{estudio} bloqueado. Os dados continuam guardados.")
    elif acao == "liberar":
        estudio.ativo = True
        estudio.save(update_fields=["ativo"])
        messages.success(request, f"{estudio} liberado.")
    elif acao in ("renovar30", "renovar365"):
        estudio.renovar(30 if acao == "renovar30" else 365)
        messages.success(request, f"Acesso de {estudio} válido até {estudio.valido_ate:%d/%m/%Y}.")
    elif acao == "senha":
        tipo = "convite" if estudio.convite_pendente else "senha"
        return redirect(f"{reverse('acesso_editar', args=[estudio.pk])}?link={tipo}")
    voltar = request.POST.get("voltar", "")
    return redirect(voltar if voltar.startswith("/acessos/") else reverse("acesso_editar", args=[estudio.pk]))


def aceitar_convite(request, uidb64, token):
    """Link do convite / redefinir senha: a profissional cria a própria senha e já entra."""
    try:
        usuario = User.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        usuario = None
    valido = usuario is not None and default_token_generator.check_token(usuario, token)
    form = SetPasswordForm(usuario, request.POST or None) if valido else None
    if valido and request.method == "POST" and form.is_valid():
        form.save()
        login(request, usuario, backend="core.backends.EmailBackend")
        messages.success(request, "Senha criada! Bem-vinda ao Agendu.")
        return redirect("painel")
    return render(request, "core/aceitar_convite.html", {"form": form, "valido": valido, "usuario": usuario})
