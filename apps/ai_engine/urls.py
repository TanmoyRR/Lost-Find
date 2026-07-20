from django.urls import path
from . import views

app_name = 'ai'

urlpatterns = [
    path('search/', views.ai_search, name='search'),
    path('matches/', views.my_matches, name='matches'),
    path('matches/<int:match_id>/dismiss/', views.dismiss_match, name='dismiss_match'),
    path('matches/<int:match_id>/accept/', views.accept_match, name='accept_match'),
    path('matches/<int:match_id>/contact/', views.contact_match_user, name='contact_match'),
    path('api/matches/count/', views.api_matches_count, name='api_matches_count'),
]
