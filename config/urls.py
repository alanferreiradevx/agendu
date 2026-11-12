from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core import views as core_views
from core.forms import LoginForm

urlpatterns = [
    path("", core_views.painel, name="painel"),
    path("entrar/", auth_views.LoginView.as_view(authentication_form=LoginForm, redirect_authenticated_user=True), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("senha/", auth_views.PasswordChangeView.as_view(success_url="/senha/ok/"), name="senha_trocar"),
    path("senha/ok/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("configuracoes/", core_views.configuracoes, name="configuracoes"),
    path("configuracoes/logo/", core_views.logo, name="logo"),
    path("busca/", core_views.busca, name="busca"),
    path("clientes/", include("clientes.urls")),
    path("agenda/", include("agenda.urls")),
    path("estoque/", include("estoque.urls")),
    path("caixa/", include("financeiro.urls")),
    path("admin/", admin.site.urls),
]

admin.site.site_header = "Agendu - administração"
admin.site.site_title = "Agendu"
