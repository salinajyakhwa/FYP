from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..filters import TravelPackageFilter
from ..models import TravelPackage


def root_redirect_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('admin_dashboard')
        if hasattr(request.user, 'userprofile'):
            if request.user.userprofile.role == 'admin':
                return redirect('admin_dashboard')
            if request.user.userprofile.role == 'vendor':
                return redirect('vendor_dashboard')
        return redirect('dashboard')
    return redirect('dashboard')


def home(request):
    today = timezone.now().date()
    sponsored_packages = TravelPackage.objects.select_related('vendor').filter(
        moderation_status='approved',
        is_sponsored=True,
        sponsorship_start__isnull=False,
        sponsorship_end__isnull=False,
        sponsorship_start__lte=today,
        sponsorship_end__gte=today,
    ).order_by('-sponsorship_priority', '-created_at')[:4]
    packages = (
        TravelPackage.objects.select_related('vendor')
        .filter(moderation_status='approved')
        .exclude(id__in=sponsored_packages.values_list('id', flat=True))
        .order_by('-created_at')[:4]
    )
    return render(request, 'main/public/home.html', {
        'packages': packages,
        'sponsored_packages': sponsored_packages,
    })


def about(request):
    return render(request, 'main/public/about.html')


def search_results(request):
    query = request.GET.get('q', '')
    base_qs = TravelPackage.objects.filter(moderation_status='approved')
    if query:
        packages = base_qs.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(vendor__name__icontains=query)
        )
    else:
        packages = base_qs

    return render(request, 'main/public/_package_list_partial.html', {'packages': packages})


def package_list(request):
    packages_list = (
        TravelPackage.objects.select_related('vendor')
        .filter(moderation_status='approved')
        .order_by('-created_at')
    )
    package_filter = TravelPackageFilter(request.GET, queryset=packages_list)
    today = timezone.now().date()
    filtered_qs = package_filter.qs.select_related('vendor')
    sponsored_packages = filtered_qs.filter(
        is_sponsored=True,
        sponsorship_start__isnull=False,
        sponsorship_end__isnull=False,
        sponsorship_start__lte=today,
        sponsorship_end__gte=today,
    ).order_by('-sponsorship_priority', '-created_at')

    organic_packages_qs = filtered_qs.exclude(
        id__in=sponsored_packages.values_list('id', flat=True)
    ).order_by('-created_at')

    paginator = Paginator(organic_packages_qs, 9)
    page_number = request.GET.get('page')
    packages = paginator.get_page(page_number)

    return render(request, 'main/public/package_list.html', {
        'packages': packages,
        'filter': package_filter,
        'sponsored_packages': sponsored_packages,
    })


def compare_packages(request):
    def _find_similar_packages(base_package, limit=3):
        base_queryset = TravelPackage.objects.exclude(id=base_package.id)
        similarity_score = Case(
            When(travel_type=base_package.travel_type, then=Value(3)),
            default=Value(0),
            output_field=IntegerField(),
        ) + Case(
            When(location=base_package.location, then=Value(2)),
            default=Value(0),
            output_field=IntegerField(),
        ) + Case(
            When(
                price__gte=base_package.price * Decimal('0.80'),
                price__lte=base_package.price * Decimal('1.20'),
                then=Value(1),
            ),
            default=Value(0),
            output_field=IntegerField(),
        )

        deluxe_q = (
            Q(name__icontains='deluxe')
            | Q(description__icontains='deluxe')
            | Q(travel_type__icontains='deluxe')
        )
        base_is_deluxe = TravelPackage.objects.filter(id=base_package.id).filter(deluxe_q).exists()

        if base_is_deluxe:
            base_queryset = base_queryset.filter(deluxe_q)

        return list(
            base_queryset
            .annotate(similarity_score=similarity_score)
            .order_by('-similarity_score', '-created_at')[:limit]
        )

    if request.method == 'GET' and request.GET.get('package_id'):
        base_package = get_object_or_404(TravelPackage, id=request.GET.get('package_id'))
        similar_packages = _find_similar_packages(base_package)
        packages = [base_package] + similar_packages
        return render(request, 'main/public/compare_packages.html', {
            'packages': packages,
            'base_package': base_package,
            'auto_generated': True,
        })

    if request.method == 'POST':
        package_ids = request.POST.getlist('package_ids')
        if not package_ids:
            messages.warning(request, "Select at least one package to compare.")
            return redirect('package_list')

        selected_packages = list(TravelPackage.objects.filter(id__in=package_ids))

        if len(selected_packages) == 1:
            base_package = selected_packages[0]
            packages = [base_package] + _find_similar_packages(base_package)
            messages.info(
                request,
                "Showing similar packages automatically based on your selected package.",
            )
            return render(request, 'main/public/compare_packages.html', {
                'packages': packages,
                'base_package': base_package,
                'auto_generated': True,
            })

        return render(request, 'main/public/compare_packages.html', {
            'packages': selected_packages,
            'auto_generated': False,
        })

    return redirect('package_list')
