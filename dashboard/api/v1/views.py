import re

from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from dashboard.forms import PeriodForm
from dashboard.models import Share
from dashboard.services.price_history import compute_stats, get_series

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

    @action(detail=True, filter_backends=(), pagination_class=None)
    def history(self, request, pk=None):
        """История цен: параметры period или date_from и date_to"""
        form = PeriodForm(request.query_params)
        if not form.is_valid():
            raise ValidationError(form.errors)
        points = get_series(self.get_object(), *form.get_range())
        return Response(
            {
                "stats": compute_stats(points),
                "points": [
                    {"time": timezone.localtime(point.moment), "price": point.price}
                    for point in points
                ],
            }
        )
