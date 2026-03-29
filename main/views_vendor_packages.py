from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import role_required
from .forms import PackageDayForm, PackageDayOptionForm, TravelPackageForm
from .models import PackageDayOption, TravelPackage
from .services.access import _get_vendor_or_403
from .services.itineraries import _sync_package_itinerary_json


@login_required
@role_required(allowed_roles=['vendor'])
def vendor_package_list(request):
    vendor = _get_vendor_or_403(request)
    packages = TravelPackage.objects.filter(vendor=vendor).order_by('-created_at')
    return render(request, 'main/vendor/vendor_package_list.html', {'packages': packages})


@login_required
@role_required(allowed_roles=['vendor'])
def create_package(request):
    if request.method == 'POST':
        form = TravelPackageForm(request.POST, request.FILES)
        if form.is_valid():
            package = form.save(commit=False)
            package.vendor = _get_vendor_or_403(request)
            package.moderation_status = 'pending'
            package.moderation_notes = ''
            package.moderated_at = None
            package.save()
            messages.success(request, "Package created and sent for admin review.")
            return redirect('vendor_dashboard')
    else:
        form = TravelPackageForm()
    return render(request, 'main/vendor/create_package.html', {'form': form})


@login_required
@role_required(allowed_roles=['vendor'])
def manage_itinerary(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)

    if package.vendor != _get_vendor_or_403(request):
        raise PermissionDenied
    package_days = package.package_days.prefetch_related('options').all()
    edit_day = None
    edit_option = None

    edit_day_id = request.GET.get('edit_day')
    if edit_day_id:
        edit_day = package_days.filter(pk=edit_day_id).first()

    edit_option_id = request.GET.get('edit_option')
    if edit_option_id:
        edit_option = PackageDayOption.objects.filter(
            package_day__package=package,
            pk=edit_option_id,
        ).select_related('package_day').first()

    day_form = PackageDayForm(instance=edit_day, package=package, prefix='day')
    option_form = PackageDayOptionForm(instance=edit_option, package=package, prefix='option')

    if request.method == 'POST':
        action = request.POST.get('action')
        day_id = request.POST.get('day_id') or None
        option_id = request.POST.get('option_id') or None

        if action == 'save_day':
            day_instance = package_days.filter(pk=day_id).first() if day_id else None
            day_form = PackageDayForm(request.POST, instance=day_instance, package=package, prefix='day')
            option_form = PackageDayOptionForm(package=package, prefix='option')
            if day_form.is_valid():
                day = day_form.save(commit=False)
                day.package = package
                day.save()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary day saved successfully.')
                return redirect('manage_itinerary', package_id=package.id)
        elif action == 'save_option':
            option_instance = (
                PackageDayOption.objects.filter(package_day__package=package, pk=option_id).first()
                if option_id else None
            )
            option_form = PackageDayOptionForm(request.POST, instance=option_instance, package=package, prefix='option')
            day_form = PackageDayForm(package=package, prefix='day')
            if option_form.is_valid():
                option_form.save()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary option saved successfully.')
                return redirect('manage_itinerary', package_id=package.id)
        elif action == 'delete_day':
            day_to_delete = package_days.filter(pk=day_id).first() if day_id else None
            if day_to_delete:
                day_to_delete.delete()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary day deleted.')
                return redirect('manage_itinerary', package_id=package.id)
        elif action == 'delete_option':
            option_to_delete = (
                PackageDayOption.objects.filter(package_day__package=package, pk=option_id).first()
                if option_id else None
            )
            if option_to_delete:
                option_to_delete.delete()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary option deleted.')
                return redirect('manage_itinerary', package_id=package.id)

    return render(request, 'main/vendor/manage_itinerary.html', {
        'package': package,
        'package_days': package_days,
        'day_form': day_form,
        'option_form': option_form,
        'editing_day': edit_day,
        'editing_option': edit_option,
    })
