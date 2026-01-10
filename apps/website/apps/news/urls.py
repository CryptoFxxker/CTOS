from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [
    path('', views.news_list, name='list'),
    path('article/<slug:slug>/', views.article_detail, name='detail'),
]

