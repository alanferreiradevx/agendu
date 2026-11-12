from django.contrib import admin

from .models import Cliente, Evolucao, Ficha, Foto


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "telefone", "nascimento", "ativo")
    search_fields = ("nome", "telefone", "email", "cpf")


admin.site.register([Ficha, Evolucao, Foto])
