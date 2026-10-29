from django.contrib import admin
from django.urls import path
from core import views
urlpatterns = [
 path("admin/", admin.site.urls), path("", views.home, name="home"),
 path("process/", views.process_video, name="process_video"),
 path("video/<int:video_id>/", views.workspace, name="workspace"),
 path("video/<int:video_id>/ask/", views.ask_question, name="ask_question"),
 path("video/<int:video_id>/summary/", views.generate_summary, name="generate_summary"),
 path("video/<int:video_id>/notes/", views.generate_notes, name="generate_notes"),
 path("video/<int:video_id>/mcqs/", views.generate_mcqs, name="generate_mcqs"),
 path("my-videos/", views.my_videos, name="my_videos"),
 path("chat-history/", views.chat_history, name="chat_history"),
 path("study-tools/", views.study_tools, name="study_tools"),
]
