from django.db import models
class Video(models.Model):
    youtube_id = models.CharField(max_length=20, db_index=True)
    url = models.URLField()
    title = models.CharField(max_length=255, default="YouTube Video")
    transcript = models.TextField(blank=True)
    transcript_segments = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.title
class ChatMessage(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=[("user","User"),("assistant","Assistant")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
class SavedNote(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=200, default="Study Notes")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
