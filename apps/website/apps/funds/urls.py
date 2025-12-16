from django.urls import path
from . import views

urlpatterns = [
    path("", views.fund_trends, name="fund_trends"),
    path("api/accounts/", views.get_accounts_list, name="get_accounts_list"),
    path("api/summary/", views.get_fund_summary, name="get_fund_summary"),
    path("api/trend/", views.get_fund_trend, name="get_fund_trend"),
    path("api/collector/status/", views.get_collector_status, name="get_collector_status"),
    path("api/collector/restart/", views.restart_collector, name="restart_collector"),
]

