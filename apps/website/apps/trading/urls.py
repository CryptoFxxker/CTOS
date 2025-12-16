from django.urls import path
from . import views

urlpatterns = [
    path("", views.trading_home, name="trading_home"),
]

