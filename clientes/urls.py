from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nova/", views.editar, name="nova"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/ficha/", views.salvar_ficha, name="salvar_ficha"),
    path("<int:pk>/ficha/imprimir/", views.imprimir_ficha, name="imprimir_ficha"),
    path("<int:pk>/evolucao/", views.nova_evolucao, name="nova_evolucao"),
    path("<int:pk>/fotos/", views.enviar_fotos, name="enviar_fotos"),
    path("<int:pk>/comparar/", views.comparar, name="comparar"),
    path("evolucao/<int:pk>/apagar/", views.apagar_evolucao, name="apagar_evolucao"),
    path("foto/<int:pk>/", views.foto_arquivo, name="foto"),
    path("foto/<int:pk>/mini/", views.foto_arquivo, {"tamanho": "mini"}, name="foto_mini"),
    path("foto/<int:pk>/apagar/", views.apagar_foto, name="apagar_foto"),
]
