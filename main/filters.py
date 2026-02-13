import django_filters
from .models import TravelPackage

class TravelPackageFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains', label='Package Name')
    location = django_filters.CharFilter(lookup_expr='icontains', label='Location')
    price__gt = django_filters.NumberFilter(field_name='price', lookup_expr='gt', label='Price from')
    price__lt = django_filters.NumberFilter(field_name='price', lookup_expr='lt', label='Price to')
    start_date__gt = django_filters.DateFilter(field_name='start_date', lookup_expr='gt', label='Available from')
    start_date__lt = django_filters.DateFilter(field_name='start_date', lookup_expr='lt', label='Available to')
    
    # Get distinct travel types for the choices
    TRAVEL_TYPE_CHOICES = TravelPackage.objects.values_list('travel_type', 'travel_type').distinct()
    travel_type = django_filters.ChoiceFilter(choices=TRAVEL_TYPE_CHOICES, label='Travel Type')

    class Meta:
        model = TravelPackage
        fields = ['name', 'location', 'price__gt', 'price__lt', 'start_date__gt', 'start_date__lt', 'travel_type']
