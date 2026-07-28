from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("api/chat/", views.chat_api, name="api_chat"),
    path("api/presets/", views.presets_api, name="api_presets"),
]
