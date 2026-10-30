from django.urls import path, re_path

from .views import (
    CreditReminderSettingsView,
    MessageHistoryView,
    NotificationDetailView,
    NotificationDispatchView,
    NotificationExportView,
    NotificationHistoryView,
    NotificationListCreateView,
    NotificationReadView,
    WeeklyCreditReminderView,
)

urlpatterns = [
    path('', NotificationListCreateView.as_view(), name='notification-list-create'),
    path('history/', NotificationHistoryView.as_view(), name='notification-history'),
    re_path(r'^history/?$', NotificationHistoryView.as_view(), name='notification-history-legacy'),
    path('export/', NotificationExportView, name='notification-export'),
    re_path(r'^export/?$', NotificationExportView, name='notification-export-legacy'),
    path('messages/', MessageHistoryView.as_view(), name='message-history'),
    path('reminders/settings/', CreditReminderSettingsView.as_view(), name='credit-reminder-settings'),
    path('reminders/weekly/', WeeklyCreditReminderView.as_view(), name='weekly-credit-reminder'),
    path('<int:pk>/read/', NotificationReadView.as_view(), name='notification-read'),
    path('<int:pk>/dispatch/', NotificationDispatchView.as_view(), name='notification-dispatch'),
    path('<int:pk>/', NotificationDetailView.as_view(), name='notification-detail'),
]
