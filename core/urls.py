from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

app_name = 'core'

urlpatterns = [
    path('favicon.ico', views.favicon_view),
    path('', views.form_view, name='form'),
    path('thank-you/', views.thank_you_view, name='thank_you'),
    path('submission/<uuid:tracking_token>/confirmation/', views.track_view, name='track'),
    path('api/track/<uuid:tracking_token>/', views.track_api_view, name='track_api'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
]
