from django.contrib import admin

from .models import Agendamento, Pacote, Procedimento, ProcedimentoMaterial


class MaterialInline(admin.TabularInline):
    model = ProcedimentoMaterial
    extra = 1


@admin.register(Procedimento)
class ProcedimentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "preco", "duracao_min", "retorno_dias", "ativo")
    inlines = [MaterialInline]


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("inicio", "cliente", "procedimento", "status", "valor")
    list_filter = ("status", "procedimento")
    date_hierarchy = "inicio"


admin.site.register(Pacote)
