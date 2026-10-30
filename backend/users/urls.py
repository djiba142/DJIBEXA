from django.urls import path

from core.views import csrf_token
from .views import (
    LoginView,
    LogoutView,
    PinResetConfirmView,
    PinResetRequestView,
    RequiredPasswordChangeView,
    UserDetailView,
    UserListView,
    UserMeView,
)

urlpatterns = [
    path('csrf/', csrf_token, name='csrf-token'),
    path('pin-reset/request/', PinResetRequestView.as_view(), name='pin-reset-request'),
    path('pin-reset/confirm/', PinResetConfirmView.as_view(), name='pin-reset-confirm'),
    path('login/', LoginView.as_view(), name='user-login'),
    path('logout/', LogoutView.as_view(), name='user-logout'),
    path('change-password/', RequiredPasswordChangeView.as_view(), name='user-change-password'),
    path('me/', UserMeView.as_view(), name='user-me'),
    path('<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('', UserListView.as_view(), name='user-list'),
]
