from unicodedata import category
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.views.generic.edit import FormView
from itertools import chain
from .models import AccountCategorySettings, Card, DictionaryEntry
import random
from django.shortcuts import get_object_or_404, redirect
from .forms import CardForm, get_category_choices, get_default_category
from .forms import CardCheckForm
from .forms import CardCategoriesFilterForm
from django.shortcuts import render


def dictionary_suggestions(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    results = DictionaryEntry.objects.filter(
        language_pair="en-ar",
        search_key__startswith=query.casefold(),
    ).order_by("search_key", "headword").values(
        "id",
        "headword",
        "translation",
        "vocalized_translation",
    )[:10]
    return JsonResponse({"results": list(results)})


class SignUpView(FormView):
    template_name = "registration/signup.html"
    form_class = UserCreationForm
    success_url = reverse_lazy("fiter-categories")

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
            AccountCategorySettings.objects.create(
                user=user,
                arabic_only=(
                    user.get_username() != settings.LEGACY_CARD_USERNAME
                ),
            )
            if user.get_username() == settings.LEGACY_CARD_USERNAME:
                Card.objects.filter(user__isnull=True).update(user=user)
        login(self.request, user)
        return super().form_valid(form)


class FilterView(LoginRequiredMixin, ListView):
    model = Card
    form_class = CardCategoriesFilterForm
    template = "cards/filter_category.html"

    def get_queryset(self):
        return Card.objects.filter(user=self.request.user).order_by(
            "box", "-date_created"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


    def get(self, request, *args, **kwargs):

            initial = {
                "category": get_default_category(request.user),
                "language": "de",
            }
            form = self.form_class(request.GET or None, user=request.user)
            if form.is_valid():
                categoryForm = form.cleaned_data["category"]
                languageForm = form.cleaned_data["language"]
            else:
                form = self.form_class(initial=initial, user=request.user)
                categoryForm = initial["category"]
                languageForm = initial["language"]

            request.session['category']=categoryForm
            request.session['language']=languageForm
            self.object_list = self.get_queryset()
            self.queryset = self.get_queryset()
            queryset = self.queryset.filter(category = categoryForm )
            context = self.get_context_data(**kwargs)
            context["object_list"] = queryset
            context["card_list"]  = queryset
            context["form"] = form
            context["category"] = categoryForm
            context["language"] = languageForm
            return render(request, self.template, context)

class CardListView(LoginRequiredMixin, ListView):
    model = Card
    template = "cards/card_list.html"

    def get_category(self):
        category = self.request.session.get(
            "category",
            get_default_category(self.request.user),
        )
        allowed_categories = {
            value for value, _ in get_category_choices(self.request.user)
        }
        if category not in allowed_categories:
            category = get_default_category(self.request.user)
            self.request.session["category"] = category
        return category

    def get_queryset(self):
            return Card.objects.filter(
                user=self.request.user,
                category=self.get_category(),
            ).order_by("box", "-date_created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category"] = self.get_category()
        context["language"] = self.request.session.get("language", "de")
        return context


class CardCreateView(LoginRequiredMixin, CreateView):
    model = Card
    form_class = CardForm
    success_url = reverse_lazy("card-create")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class CardUpdateView(LoginRequiredMixin, UpdateView):
    model = Card
    form_class = CardForm
    template_name = "cards/card_form.html"
    success_url = reverse_lazy("card-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return Card.objects.filter(user=self.request.user)


class CardDeleteView(LoginRequiredMixin, DeleteView):
    model = Card
    template = "cards/card_confirm_delete.html"
    success_url = reverse_lazy("card-list")

    def get_queryset(self):
        return Card.objects.filter(user=self.request.user)


class BoxView(CardListView):
    template_name = "cards/box.html"
    def get_queryset(self):
        return Card.objects.filter(
            user=self.request.user,
            box=self.kwargs["box_num"],
            category=self.get_category(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["box_number"] = self.kwargs["box_num"]
        context["object_list"] = self.get_queryset()
        context["category"] = self.get_category()
        context["language"] = self.request.session.get("language", "de")
        return context

class CardRepeatView(CardListView):
    template_name = "cards/repeat.html"
    form_class = CardCheckForm

    def get_queryset(self):
        object_list = [
            card
            for card in Card.objects.filter(
                user=self.request.user,
                category=self.get_category(),
            )
            if card.to_repeat
        ]
        return object_list

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object_list"] = self.get_queryset()
        context["card_count"] = len(self.get_queryset())
        context["category"] = self.get_category()
        context["language"] = self.request.session.get("language", "de")

        self.queryset = self.object_list
        if context["card_count"] >0:
            context["check_card"] = random.choice(self.get_queryset())

        return context

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            card = get_object_or_404(
                Card,
                id=form.cleaned_data["card_id"],
                user=request.user,
            )
            card.move(form.cleaned_data["solved"])
            card.to_repeat
        return redirect(request.META.get("HTTP_REFERER"))
