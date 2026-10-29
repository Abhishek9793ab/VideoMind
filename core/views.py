
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import YouTubeURLForm, QuestionForm
from .models import Video, ChatMessage, SavedNote
from .services.youtube import extract_video_id, fetch_transcript


STUDY_TOOLS = {
    "summary": ("summary", "Video Summary"),
    "notes": ("notes", "Revision Notes"),
    "mcqs": ("mcqs", "Practice MCQs"),
}


def home(request):
    recent_videos = Video.objects.order_by("-created_at")[:3]

    return render(request, "core/home.html", {
        "form": YouTubeURLForm(),
        "recent": recent_videos,
        "videos": recent_videos,
    })


@require_POST
def process_video(request):
    form = YouTubeURLForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Please enter a valid YouTube URL.")
        return redirect("home")

    try:
        submitted_url = form.cleaned_data["url"].strip()
        youtube_id = extract_video_id(submitted_url)

        # Fetch captions for the submitted video only.
        segments = fetch_transcript(youtube_id)
        transcript = " ".join(
            str(segment.get("text", "")).strip()
            for segment in segments
            if isinstance(segment, dict) and segment.get("text")
        ).strip()

        if len(transcript) < 20:
            raise ValueError(
                "This video's captions are empty or too short to process."
            )

        canonical_url = (
            f"https://www.youtube.com/watch?v={youtube_id}"
        )

        # Reuse the record for this YouTube ID when it exists.
        # Lock the row during an update to avoid concurrent overwrites.
        with transaction.atomic():
            video = (
                Video.objects.select_for_update()
                .filter(youtube_id=youtube_id)
                .order_by("-created_at")
                .first()
            )

            if video is None:
                video = Video.objects.create(
                    youtube_id=youtube_id,
                    url=canonical_url,
                    title=f"YouTube Video ({youtube_id})",
                    transcript=transcript,
                    transcript_segments=segments,
                )
            else:
                transcript_changed = video.transcript != transcript

                video.url = canonical_url
                video.transcript = transcript
                video.transcript_segments = segments

                video.save(update_fields=[
                    "url",
                    "transcript",
                    "transcript_segments",
                ])

                # If the transcript changed, remove saved study material
                # so that old content is not shown as current content.
                if transcript_changed:
                    video.notes.all().delete()

        # Index only this video's transcript into its own collection.
        from .services.rag import index_video
        index_video(video)

        messages.success(
            request,
            "Video transcript processed successfully. "
            "You can now generate its summary, notes, and MCQs."
        )
        return redirect("workspace", video_id=video.pk)

    except Exception as exc:
        messages.error(
            request,
            f"Could not process this video: {str(exc)[:250]}"
        )
        return redirect("home")


def workspace(request, video_id):
    video = get_object_or_404(Video, pk=video_id)

    return render(request, "core/workspace.html", {
        "video": video,
        "segments": video.transcript_segments,
        "messages_list": video.messages.all().order_by("created_at"),
        "notes": video.notes.all().order_by("-created_at"),
        "form": QuestionForm(),
    })


@require_POST
def ask_question(request, video_id):
    video = get_object_or_404(Video, pk=video_id)
    form = QuestionForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Please enter a valid question.")
        return redirect("workspace", video_id=video.pk)

    question = form.cleaned_data["question"].strip()

    ChatMessage.objects.create(
        video=video,
        role="user",
        content=question,
    )

    try:
        from .services.rag import answer
        response = answer(video, question)

    except Exception as exc:
        response = (
            "I couldn't answer this question right now. "
            "Please check the AI configuration and try again. "
            f"Details: {str(exc)[:180]}"
        )

    ChatMessage.objects.create(
        video=video,
        role="assistant",
        content=response,
    )

    return redirect("workspace", video_id=video.pk)


def save_generated_note(video, kind, title):
    """
    Generate fresh material for this specific video's transcript.
    Update its existing note instead of reusing stale content.
    """
    from .services.rag import generate

    content = generate(video, kind)

    if not content or not content.strip():
        raise RuntimeError("The AI returned empty study material.")

    with transaction.atomic():
        note = (
            SavedNote.objects.select_for_update()
            .filter(video=video, title=title)
            .order_by("-created_at")
            .first()
        )

        if note is None:
            note = SavedNote.objects.create(
                video=video,
                title=title,
                content=content,
            )
        else:
            note.content = content
            note.save(update_fields=["content"])

    return note


def generate_action(request, video_id, kind, title):
    video = get_object_or_404(Video, pk=video_id)

    try:
        note = save_generated_note(video, kind, title)

        messages.success(
            request,
            f"{title} generated successfully for {video.title}."
        )

    except Exception as exc:
        messages.error(
            request,
            f"Could not generate {title}: {str(exc)[:220]}"
        )

    return redirect("workspace", video_id=video.pk)


@require_POST
def generate_summary(request, video_id):
    return generate_action(
        request, video_id, "summary", "Video Summary"
    )


@require_POST
def generate_notes(request, video_id):
    return generate_action(
        request, video_id, "notes", "Revision Notes"
    )


@require_POST
def generate_mcqs(request, video_id):
    return generate_action(
        request, video_id, "mcqs", "Practice MCQs"
    )


def my_videos(request):
    videos = Video.objects.order_by("-created_at")

    return render(request, "core/my_videos.html", {
        "videos": videos,
    })


def chat_history(request):
    videos = (
        Video.objects.filter(messages__isnull=False)
        .distinct()
        .order_by("-created_at")
    )

    return render(request, "core/chat_history.html", {
        "videos": videos,
    })


def study_tools(request):
    videos = Video.objects.order_by("-created_at")
    selected_video = None
    generated_note = None
    generation_error = None

    if request.method == "POST":
        video_id = request.POST.get("video_id")
        action = request.POST.get("action")

        if not video_id:
            generation_error = "Please select a video."
        else:
            selected_video = videos.filter(pk=video_id).first()

            if selected_video is None:
                generation_error = "The selected video was not found."

            elif action not in STUDY_TOOLS:
                generation_error = "Please select a valid study tool."

            else:
                kind, title = STUDY_TOOLS[action]

                try:
                    # Always generate new content for the selected video.
                    generated_note = save_generated_note(
                        selected_video, kind, title
                    )

                    messages.success(
                        request,
                        f"{title} generated for {selected_video.title}."
                    )

                except Exception as exc:
                    generation_error = (
                        f"Could not generate {title}: {str(exc)[:220]}"
                    )

    else:
        requested_video_id = request.GET.get("video")

        if requested_video_id:
            selected_video = videos.filter(
                pk=requested_video_id
            ).first()

        if selected_video is None:
            selected_video = videos.first()

        requested_note_id = request.GET.get("note")

        if selected_video and requested_note_id:
            generated_note = selected_video.notes.filter(
                pk=requested_note_id
            ).first()

    tool_cards = [
        (
            "summary",
            "AI Summary",
            "Understand the video's main topics and key takeaways.",
            "▤",
        ),
        (
            "notes",
            "Revision Notes",
            "Review structured explanations, definitions, and key points.",
            "✎",
        ),
        (
            "mcqs",
            "Practice MCQs",
            "Test your knowledge with transcript-based questions.",
            "?",
        ),
    ]

    return render(request, "core/study_tools.html", {
        "videos": videos,
        "selected_video": selected_video,
        "generated_note": generated_note,
        "generation_error": generation_error,
        "tool_cards": tool_cards,
    })
