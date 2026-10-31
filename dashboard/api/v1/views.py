import re

from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from dashboard.models import Share

from .serializer import ShareSerializer


class ShareFilter(filters.FilterSet):
    class Meta:
        model = Share
        fields = ("name", "ticker")


class RegexSearchFilter(SearchFilter):
    """Поиск по регулярному выражению: ошибка в выражении даёт 400, а не сбой БД"""

    def filter_queryset(self, request, queryset, view):
        for term in request.query_params.get(self.search_param, "").split():
            try:
                re.compile(term)
            except re.error as e:
                raise ValidationError({self.search_param: str(e)}) from e
        return super().filter_queryset(request, queryset, view)


class ShareViewSet(viewsets.ModelViewSet):
    serializer_class = ShareSerializer
    queryset = Share.objects.order_by("name")
    permission_classes = (IsAuthenticatedOrReadOnly,)
    filter_backends = (OrderingFilter, filters.DjangoFilterBackend, RegexSearchFilter)
    filterset_class = ShareFilter
    ordering_fields = ["name", "ticker"]
    search_fields = ["$name"]
