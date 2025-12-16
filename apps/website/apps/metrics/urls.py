from django.urls import path
from . import views

urlpatterns = [
    path("", views.metrics_home, name="metrics_home"),
    path("<str:indicator_id>/", views.indicator_detail, name="indicator_detail"),
    path("<str:indicator_id>/api/chart/", views.get_chart_image, name="get_chart_image"),
    path("api/kline/data/", views.get_kline_data, name="get_kline_data"),
    path("api/kline/symbols/", views.get_available_symbols, name="get_available_symbols"),
]