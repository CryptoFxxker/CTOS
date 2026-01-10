from django.urls import path
from . import views

urlpatterns = [
    path("", views.strategies_home, name="strategies_home"),
]

