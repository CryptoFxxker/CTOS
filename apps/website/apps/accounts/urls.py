from django.urls import path
from . import views

urlpatterns = [
    path("", views.account_list, name="account_list"),
]