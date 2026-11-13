import uuid
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from config.storage import storage_privado
from core.utils import whatsapp_url

UF_CHOICES = [(uf, uf) for uf in (
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)]


class Cliente(models.Model):
    estudio = models.ForeignKey("core.Estudio", on_delete=models.CASCADE, related_name="clientes", verbose_name="espaço")
    nome = models.CharField(max_length=150)
    telefone = models.CharField("WhatsApp / telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    cpf = models.CharField("CPF", max_length=14, blank=True)
    nascimento = models.DateField("data de nascimento", null=True, blank=True)
    profissao = models.CharField("profissão", max_length=80, blank=True)
    como_conheceu = models.CharField("como conheceu", max_length=80, blank=True,
                                     help_text="Instagram, indicação de alguém, Google...")
    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField("rua", max_length=150, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField(max_length=80, blank=True)
    bairro = models.CharField(max_length=80, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def primeiro_nome(self):
        return self.nome.split()[0] if self.nome else ""

    @property
    def idade(self):
        if not self.nascimento:
            return None
        hoje = timezone.localdate()
        return hoje.year - self.nascimento.year - ((hoje.month, hoje.day) < (self.nascimento.month, self.nascimento.day))

    @property
    def endereco_formatado(self):
        rua = ", ".join(p for p in (self.logradouro, self.numero) if p)
        if self.complemento:
            rua += f" - {self.complemento}"
        partes = [rua, self.bairro, "/".join(p for p in (self.cidade, self.uf) if p), self.cep]
        return " - ".join(p for p in partes if p)

    def whatsapp(self, mensagem=""):
        return whatsapp_url(self.telefone, mensagem)

    @property
    def faltas(self):
        return self.agendamentos.filter(status="faltou").count()


class Ficha(models.Model):
    """Ficha de anamnese estética. Uma por cliente; atualize sempre que algo mudar."""

    TIPO_PELE = [("normal", "Normal"), ("seca", "Seca"), ("oleosa", "Oleosa"), ("mista", "Mista"), ("sensivel", "Sensível")]
    FOTOTIPO = [
        ("I", "I - muito clara, sempre queima"), ("II", "II - clara, queima fácil"),
        ("III", "III - morena clara, às vezes queima"), ("IV", "IV - morena moderada, raramente queima"),
        ("V", "V - morena escura, muito raramente queima"), ("VI", "VI - negra, nunca queima"),
    ]

    cliente = models.OneToOneField(Cliente, on_delete=models.CASCADE, related_name="ficha")
    queixa_principal = models.TextField("queixa principal / objetivo", blank=True,
                                        help_text="O que a cliente quer melhorar.")
    tipo_pele = models.CharField("tipo de pele", max_length=10, choices=TIPO_PELE, blank=True)
    fototipo = models.CharField("fototipo (Fitzpatrick)", max_length=3, choices=FOTOTIPO, blank=True)

    gestante_lactante = models.BooleanField("gestante ou amamentando", default=False)
    diabetes = models.BooleanField(default=False)
    hipertensao = models.BooleanField("hipertensão", default=False)
    cardiaco = models.BooleanField("problema cardíaco", default=False)
    marcapasso_metal = models.BooleanField("marcapasso ou metal no corpo", default=False)
    epilepsia = models.BooleanField(default=False)
    coagulacao = models.BooleanField("distúrbio de coagulação", default=False)
    queloide = models.BooleanField("tendência a queloide", default=False)
    herpes = models.BooleanField("herpes", default=False)
    cancer = models.BooleanField("câncer (atual ou em tratamento)", default=False)
    fumante = models.BooleanField(default=False)
    acidos_retinoides = models.BooleanField("usa ácidos / isotretinoína", default=False)
    exposicao_solar = models.BooleanField("exposição solar frequente", default=False)
    usa_protetor = models.BooleanField("usa protetor solar", default=False)

    alergias = models.TextField(blank=True)
    medicamentos = models.TextField("medicamentos em uso", blank=True)
    cirurgias = models.TextField("cirurgias", blank=True)
    procedimentos_anteriores = models.TextField("procedimentos estéticos anteriores", blank=True)
    rotina_cuidados = models.TextField("rotina de cuidados em casa", blank=True)
    observacoes = models.TextField("observações", blank=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    ALERTAS = ("gestante_lactante", "diabetes", "hipertensao", "cardiaco", "marcapasso_metal", "epilepsia",
               "coagulacao", "queloide", "herpes", "cancer", "acidos_retinoides")

    def __str__(self):
        return f"Ficha de {self.cliente}"

    def pontos_de_atencao(self):
        """Itens marcados que pedem cuidado antes de um procedimento (aparecem em destaque)."""
        itens = [self._meta.get_field(c).verbose_name for c in self.ALERTAS if getattr(self, c)]
        if self.alergias.strip():
            itens.append("alergias: " + self.alergias.strip())
        return itens

    def condicoes_marcadas(self):
        campos = self.ALERTAS + ("fumante", "exposicao_solar", "usa_protetor")
        return [self._meta.get_field(c).verbose_name for c in campos if getattr(self, c)]


class Evolucao(models.Model):
    """Registro de uma sessão/resultado. As fotos podem ficar ligadas a ele."""

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="evolucoes")
    agendamento = models.ForeignKey("agenda.Agendamento", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="evolucoes")
    data = models.DateField(default=timezone.localdate)
    texto = models.TextField("como foi / resultado")
    medidas = models.CharField("medidas", max_length=250, blank=True,
                               help_text="Opcional. Ex.: peso 68 kg, cintura 74 cm")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-criado_em"]
        verbose_name = "evolução"
        verbose_name_plural = "evoluções"

    def __str__(self):
        return f"{self.cliente} - {self.data:%d/%m/%Y}"


def caminho_foto(instancia, nome):
    return f"clientes/{instancia.cliente_id}/{uuid.uuid4().hex}.jpg"


def caminho_miniatura(instancia, nome):
    return f"clientes/{instancia.cliente_id}/mini_{uuid.uuid4().hex}.jpg"


class Foto(models.Model):
    MOMENTO = [("antes", "Antes"), ("depois", "Depois"), ("durante", "Durante o tratamento"), ("outro", "Outra")]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="fotos")
    evolucao = models.ForeignKey(Evolucao, on_delete=models.SET_NULL, null=True, blank=True, related_name="fotos")
    agendamento = models.ForeignKey("agenda.Agendamento", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="fotos")
    imagem = models.ImageField(upload_to=caminho_foto, storage=storage_privado)
    miniatura = models.ImageField(upload_to=caminho_miniatura, storage=storage_privado, blank=True)
    momento = models.CharField(max_length=10, choices=MOMENTO, default="outro")
    regiao = models.CharField("região", max_length=60, blank=True, help_text="Ex.: rosto, abdômen, glúteos")
    legenda = models.CharField(max_length=200, blank=True)
    data = models.DateField(default=timezone.localdate)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"Foto de {self.cliente} ({self.data:%d/%m/%Y})"

    @staticmethod
    def _jpeg(imagem, lado):
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(imagem))  # foto de celular "deitada" fica em pé
        img = img.convert("RGB")
        img.thumbnail((lado, lado))
        saida = BytesIO()
        img.save(saida, "JPEG", quality=85, optimize=True)
        return ContentFile(saida.getvalue())

    def save(self, *args, **kwargs):
        # Foto nova: reduz (celular tira fotos de 4000 px e 5 MB) e gera a miniatura da galeria.
        if self._state.adding and self.imagem and not self.miniatura:
            original = self.imagem
            original.seek(0)
            grande = self._jpeg(original, settings.FOTO_TAMANHO_MAXIMO)
            original.seek(0)
            mini = self._jpeg(original, 480)
            self.imagem.save("foto.jpg", grande, save=False)
            self.miniatura.save("mini.jpg", mini, save=False)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        arquivos = [f for f in (self.imagem, self.miniatura) if f]
        super().delete(*args, **kwargs)
        for f in arquivos:
            f.storage.delete(f.name)
