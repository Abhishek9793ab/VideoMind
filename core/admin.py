from django.contrib import admin
from .models import Video, ChatMessage, SavedNote
admin.site.register(Video)
admin.site.register(ChatMessage)
admin.site.register(SavedNote)
