from django.conf import settings
from django.contrib.auth.views import redirect_to_login

LIVRES = ("/entrar/", "/static/", "/admin/", "/favicon.ico")


class LoginObrigatorioMiddleware:
    """
    Todo o sistema exige login (dados de clientes, fotos, caixa).
    Assim nenhuma página nova fica aberta por esquecimento.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(LIVRES):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)
