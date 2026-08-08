from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('<int:pk>/', views.conversation_detail, name='detail'),
    path('start/<int:post_id>/<int:user_id>/', views.start_conversation, name='start'),
]
