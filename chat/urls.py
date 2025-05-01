from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    # Existing URLs
    path('chats/', views.ChatListView.as_view(), name='chat-list'),
    path('chats/create/', views.CreateChatView.as_view(), name='create-chat'),
    path('chats/<str:firebase_chat_id>/', views.ChatDetailView.as_view(), name='chat-detail'),
    path('chats/<str:firebase_chat_id>/messages/', views.ChatMessagesView.as_view(), name='chat-messages'),
    path('messages/send/', views.SendMessageView.as_view(), name='send-message'),
    path('chats/<str:firebase_chat_id>/mark-read/', views.MarkMessagesReadView.as_view(), name='mark-messages-read'),
    
    # New FCM token registration URLs
    path('notifications/register/', views.RegisterDeviceTokenView.as_view(), name='register-token'),
    path('notifications/unregister/', views.UnregisterDeviceTokenView.as_view(), name='unregister-token'),
]
