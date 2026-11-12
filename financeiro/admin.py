from django.contrib import admin

from .models import FormaPagamento, Lancamento


@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ("data", "tipo", "categoria", "descricao", "valor", "taxa")
    list_filter = ("tipo", "categoria")
    date_hierarchy = "data"


admin.site.register(FormaPagamento)
