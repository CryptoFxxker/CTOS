from django.urls import path
from . import views

urlpatterns = [
    path("", views.metrics_home, name="metrics_home"),
]