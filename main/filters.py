import django_filters
from .models import TravelPackage

class TravelPackageFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains', label='Package Name')
    location = django_filters.CharFilter(lookup_expr='icontains', label='Location')
    travel_type = django_filters.CharFilter(lookup_expr='icontains', label='Travel Type')
    price__gt = django_filters.NumberFilter(field_name='price', lookup_expr='gt', label='Price from')
    price__lt = django_filters.NumberFilter(field_name='price', lookup_expr='lt', label='Price to')
    start_date__gt = django_filters.DateFilter(field_name='start_date', lookup_expr='gt', label='Available from')
    start_date__lt = django_filters.DateFilter(field_name='start_date', lookup_expr='lt', label='Available to')
    hotel__name = django_filters.CharFilter(field_name='hotel_options_name', lookup_expr='icontains', label='Hotel Name')
    
    class Meta:
        model = TravelPackage
        fields = ['name', 'location', 'travel_type', 'price__gt', 'price__lt', 'start_date__gt', 'start_date__lt']
