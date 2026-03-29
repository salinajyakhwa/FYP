from django.urls import path

from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('tours/', views.package_list, name='package_list'),
    path('search/', views.search_results, name='search_results'),
    path('about/', views.about, name='about'),
    path('compare/', views.compare_packages, name='compare_packages'),
]
