from django.db import migrations

FORMAS = [
    ("PIX", 0, 1), ("Dinheiro", 0, 2), ("Cartão de débito", "1.99", 3),
    ("Cartão de crédito à vista", "3.49", 4), ("Cartão de crédito parcelado", "4.99", 5),
]


def criar(apps, schema_editor):
    # Taxas comuns de maquininha; ajuste em Configurações para as da sua.
    FormaPagamento = apps.get_model("financeiro", "FormaPagamento")
    for nome, taxa, ordem in FORMAS:
        FormaPagamento.objects.get_or_create(nome=nome, defaults={"taxa_percentual": taxa, "ordem": ordem})


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0001_initial")]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
