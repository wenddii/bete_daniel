from django.urls import path
from . import views

app_name = 'rooms'

urlpatterns = [
    path('', views.room_category_list, name='category_list'),
    path('<int:category_id>/', views.room_category_detail, name='category_detail'),
]
