from django.http import HttpResponseRedirect
from django.urls import reverse

class LoginCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.white_list = [
            '/',
            '/contact/',
            '/price/',
            '/about/',
            '/home/',
            '/login/',
            '/register/',
            '/katex/',
        ]

    def __call__(self, request):
        if not request.user.is_authenticated and request.path not in self.white_list and not request.path.startswith('/api/') and not request.path.startswith('/katex/'):
            return HttpResponseRedirect(f"/?next={request.path}")

        response = self.get_response(request)
        return response
