from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.semana, name="semana"),
    path("novo/", views.editar, name="novo"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/concluir/", views.concluir, name="concluir"),
    path("<int:pk>/desfazer/", views.desfazer, name="desfazer"),
    path("<int:pk>/apagar/", views.apagar, name="apagar"),
    path("<int:pk>/status/<str:status>/", views.mudar_status, name="status"),
    path("procedimentos/", views.procedimentos, name="procedimentos"),
    path("procedimentos/novo/", views.procedimento_editar, name="procedimento_novo"),
    path("procedimentos/<int:pk>/", views.procedimento_editar, name="procedimento_editar"),
    path("pacotes/", views.pacotes, name="pacotes"),
    path("pacotes/novo/", views.pacote_novo, name="pacote_novo"),
    path("pacotes/<int:pk>/", views.pacote, name="pacote"),
]
