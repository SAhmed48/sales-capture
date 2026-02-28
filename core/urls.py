from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.form_view, name='form'),
    path('thank-you/', views.thank_you_view, name='thank_you'),
    path('t/<uuid:tracking_token>/', views.track_view, name='track'),
    path('api/track/<uuid:tracking_token>/', views.track_api_view, name='track_api'),
]
