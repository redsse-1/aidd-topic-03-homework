from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.generic import View

from .forms import AuthForm, RegistrationForm


class AuthView(View):
    """Login and authentication."""

    @staticmethod
    def get(request):
        return render(request, "user/auth.html", {"form": AuthForm})

    @staticmethod
    def post(request):
        form = AuthForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "user/auth.html",
                {"form": form, "error": form.errors.as_text()},
            )

        user = authenticate(
            request,
            username=form.cleaned_data["email"].lower(),
            password=form.cleaned_data["password"],
        )
        if user is None:
            return render(
                request,
                "user/auth.html",
                {
                    "form": form,
                    "error": "Неверный логин или пароль! Повторите попытку.",
                },
            )

        login(request, user)
        return redirect("dashboard:index")


class RegistrationView(View):
    """Register and sign in a user."""

    @staticmethod
    def get(request):
        return render(request, "user/registration.html", {"form": RegistrationForm})

    @staticmethod
    def post(request):
        form = RegistrationForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "user/registration.html",
                {"form": form, "error": form.errors.as_text()},
            )

        user = form.save()
        login(request, user)
        return redirect("dashboard:index")


class LogoutView(View):
    """Log out the current user."""

    @staticmethod
    def get(request):
        logout(request)
        return redirect("dashboard:index")
