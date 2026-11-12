from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.caixa, name="caixa"),
    path("faturamento/", views.faturamento, name="faturamento"),
    path("formas/", views.formas, name="formas"),
    path("novo/<str:tipo>/", views.lancamento, name="novo"),
    path("<int:pk>/", views.lancamento, {"tipo": None}, name="editar"),
    path("<int:pk>/apagar/", views.apagar, name="apagar"),
]
