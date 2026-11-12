from django.contrib import admin

from .models import Material, Movimento


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("nome", "quantidade", "unidade", "estoque_minimo", "custo_unitario", "validade", "ativo")


@admin.register(Movimento)
class MovimentoAdmin(admin.ModelAdmin):
    list_display = ("data", "material", "tipo", "quantidade", "saldo_depois")
    list_filter = ("tipo",)
