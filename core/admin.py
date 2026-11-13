from django.contrib import admin

from .models import Estudio


@admin.register(Estudio)
class EstudioAdmin(admin.ModelAdmin):
    """Só os dados de acesso. Use a área "Acessos" do sistema no dia a dia."""

    list_display = ("nome", "profissional", "dono", "ativo", "valido_ate", "plano", "valor_mensal")
    fields = ("nome", "profissional", "dono", "ativo", "valido_ate", "plano", "valor_mensal", "anotacoes")
