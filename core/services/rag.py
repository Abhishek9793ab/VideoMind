
import os
import re
import math
import time
import random
import hashlib
from pathlib import Path

import chromadb
from google import genai
from django.conf import settings


DB_PATH = Path(settings.BASE_DIR) / "chroma_db"
EMBEDDING_SIZE = 384
MAX_GEMINI_ATTEMPTS = 3


# --------------------------------------------------
# TEXT EMBEDDING
# Lightweight lexical hashing, not a transformer model.
# --------------------------------------------------
def text_embedding(text):
    vector = [0.0] * EMBEDDING_SIZE

    words = re.findall(r"\w+", (text or "").lower(), flags=re.UNICODE)
    features = words + [
        f"{words[i]}_{words[i + 1]}"
        for i in range(len(words) - 1)
    ]

    for feature in features:
        digest = hashlib.blake2b(
            feature.encode("utf-8"),
            digest_size=8,
        ).digest()

        number = int.from_bytes(digest, "little")
        vector[number % EMBEDDING_SIZE] += (
            1.0 if (number >> 8) & 1 else -1.0
        )

    magnitude = math.sqrt(sum(value * value for value in vector))

    if magnitude:
        return [value / magnitude for value in vector]

    return vector


# --------------------------------------------------
# VIDEO COLLECTION
# Every video uses its own ChromaDB collection.
# --------------------------------------------------
def collection(video):
    DB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(DB_PATH))
    return client.get_or_create_collection(
        name=f"video_{video.pk}"
    )


# --------------------------------------------------
# TRANSCRIPT
# --------------------------------------------------
def transcript_text(video):
    text = (video.transcript or "").strip()

    if text:
        return text

    segments = video.transcript_segments or []

    return " ".join(
        str(item.get("text", "")).strip()
        for item in segments
        if isinstance(item, dict) and item.get("text")
    ).strip()


# --------------------------------------------------
# SPLIT TRANSCRIPT INTO CHUNKS
# --------------------------------------------------
def build_chunks(video, chunk_size=900):
    segments = video.transcript_segments or []
    chunks = []
    buffer = []
    start_time = 0.0
    end_time = 0.0
    timestamp = "00:00"
    current_length = 0

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        text = str(segment.get("text", "")).strip()

        if not text:
            continue

        if not buffer:
            start_time = float(segment.get("start", 0) or 0)
            timestamp = str(segment.get("timestamp", "00:00"))

        buffer.append(text)
        current_length += len(text) + 1
        end_time = float(
            segment.get("end", start_time) or start_time
        )

        if current_length >= chunk_size:
            chunks.append({
                "text": " ".join(buffer),
                "start": start_time,
                "end": end_time,
                "timestamp": timestamp,
            })

            buffer = []
            current_length = 0

    if buffer:
        chunks.append({
            "text": " ".join(buffer),
            "start": start_time,
            "end": end_time,
            "timestamp": timestamp,
        })

    # Fallback if transcript segments are unavailable.
    if not chunks:
        full_text = transcript_text(video)

        for offset in range(0, len(full_text), chunk_size):
            chunk = full_text[offset:offset + chunk_size].strip()

            if chunk:
                chunks.append({
                    "text": chunk,
                    "start": 0.0,
                    "end": 0.0,
                    "timestamp": "00:00",
                })

    return chunks


# --------------------------------------------------
# INDEX VIDEO TRANSCRIPT
# --------------------------------------------------
def index_video(video):
    chunks = build_chunks(video)

    if not chunks:
        raise RuntimeError(
            "No transcript is available. "
            "Process a YouTube video with accessible captions first."
        )

    col = collection(video)

    old = col.get()

    if old.get("ids"):
        col.delete(ids=old["ids"])

    documents = [item["text"] for item in chunks]

    col.add(
        ids=[f"{video.pk}_{i}" for i in range(len(chunks))],
        documents=documents,
        metadatas=[
            {
                "start": item["start"],
                "end": item["end"],
                "timestamp": item["timestamp"],
                "video_id": str(video.pk),
            }
            for item in chunks
        ],
        embeddings=[text_embedding(doc) for doc in documents],
    )

    return len(chunks)


# --------------------------------------------------
# GEMINI CLIENT
# --------------------------------------------------
def ask_gemini(prompt):
    key = os.getenv("GEMINI_API_KEY", "").strip()

    if not key or key == "put_your_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check your .env file."
        )

    # Correct environment variable lookup.
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash",
    ).strip()

    if not model:
        raise RuntimeError(
            "GEMINI_MODEL is empty. Check your .env file."
        )

    client = genai.Client(api_key=key)
    last_error = None

    for attempt in range(MAX_GEMINI_ATTEMPTS):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )

            result = (getattr(response, "text", None) or "").strip()

            if not result:
                raise RuntimeError(
                    "Gemini returned an empty response. Try generating again."
                )

            return result

        except Exception as exc:
            last_error = exc
            error = str(exc).upper()

            temporary = any(code in error for code in (
                "429",
                "500",
                "502",
                "503",
                "504",
                "UNAVAILABLE",
                "RESOURCE_EXHAUSTED",
                "DEADLINE_EXCEEDED",
                "TIMEOUT",
            ))

            # Do not retry permanent errors such as invalid API keys
            # or unsupported model names.
            if not temporary:
                break

            if attempt < MAX_GEMINI_ATTEMPTS - 1:
                delay = min(2 ** (attempt + 1), 8) + random.random()
                time.sleep(delay)

    raise RuntimeError(
        f"AI generation failed for model {model} after "
        f"{MAX_GEMINI_ATTEMPTS} attempts: {last_error}. "
        "Please try again later or configure another available model."
    ) from last_error


# --------------------------------------------------
# ASK A QUESTION ABOUT THE VIDEO
# --------------------------------------------------
def answer(video, question):
    question = (question or "").strip()

    if not question:
        raise ValueError("Please enter a question.")

    if not transcript_text(video):
        raise RuntimeError("This video has no transcript.")

    col = collection(video)

    if col.count() == 0:
        index_video(video)

    count = col.count()

    result = col.query(
        query_embeddings=[text_embedding(question)],
        n_results=min(5, count),
        include=["documents", "metadatas"],
    )

    docs = result.get("documents", [[]])[0]
    metadata = result.get("metadatas", [[]])[0]

    if not docs:
        raise RuntimeError(
            "No matching transcript sections were found."
        )

    context = "\n\n".join(
        f"[{item.get('timestamp', '00:00')}] {doc}"
        for doc, item in zip(docs, metadata)
    )

    prompt = f"""
You are LearnLens AI, an educational video tutor.

Answer using the transcript excerpts below.
Do not invent facts or claim that the transcript says something
that is not present.
If the excerpts do not answer the question, say so clearly.
Mention timestamps where useful.

VIDEO TITLE: {video.title}
YOUTUBE VIDEO ID: {video.youtube_id}

QUESTION:
{question}

TRANSCRIPT EXCERPTS:
{context}
"""

    return ask_gemini(prompt)


# --------------------------------------------------
# STUDY MATERIAL PROMPTS
# --------------------------------------------------
STUDY_TASKS = {
    "summary": """
Create a useful, detailed summary of this specific video.

Use this exact Markdown structure:

# Video Summary

## 1. Video Overview
Explain what the video covers using transcript-supported details.

## 2. Main Topics Explained
Explain each major topic separately.
Use clear headings and simple explanations.

## 3. Important Concepts
List and explain the most important concepts.

## 4. Key Takeaways
Provide the main lessons in bullet points.

## 5. Important Terms
Define terms only when their meanings are supported by the transcript.

## 6. Final Recap
Give a concise revision recap.

Do not invent the video duration, speaker identity, examples,
definitions, statistics or facts.
""",

    "notes": """
Create detailed, professional, exam-friendly revision notes
from this video's transcript.

Use this exact Markdown structure:

# Revision Notes

## 1. Learning Objectives
List the objectives that are supported by the transcript.

## 2. Topic-wise Explanation
Create a separate subsection for every major topic.

For each topic include:
- **Meaning:** Explain it using the transcript.
- **Key Points:** Important details in bullets.
- **Process or Steps:** Include only if the transcript describes them.
- **Example:** Include only if the transcript provides or explains one.

## 3. Important Definitions
Include definitions supported by the transcript.
If a definition is not provided, do not invent one.

## 4. Important Facts and Steps
Collect relevant facts, procedures and sequences from the video.

## 5. Differences and Comparisons
Include comparisons only when the transcript supports them.

## 6. Quick Revision Checklist
Create concise revision points.

## 7. Important Exam Questions
Write up to five short-answer questions based on the transcript.
Provide a concise answer under each question.

## 8. Final Recap
Summarize the most important learning points.

Make the notes informative, clear and specific to this video.
Avoid repeated points and generic filler.
Do not invent facts or examples.
""",

    "mcqs": """
Create multiple-choice questions using ONLY the supplied transcript.

Generate up to 10 distinct questions.
Create fewer if the transcript does not contain enough information.

Use this exact structure for EVERY question:

## Question 1
Write one clear question.

- A) First option
- B) Second option
- C) Third option
- D) Fourth option

**Correct Answer:** B) Write the complete correct option.
**Explanation:** Explain why this answer is correct using the transcript.

Repeat the structure with Question 2, Question 3, and so on.

MANDATORY RULES:
1. Every question must have exactly four options: A, B, C and D.
2. Every question must have exactly one correct answer.
3. Always include both Correct Answer and Explanation.
4. The answer must include the option letter and the full option text.
5. Vary the correct option position across the questions.
6. Do not use unsupported facts, dates, numbers or definitions.
7. Avoid duplicate questions and ambiguous options.
8. Do not omit answers to make the quiz more challenging.
9. If the transcript supports only a few questions, generate fewer.
10. End with a short score guide:
   - 9–10: Excellent
   - 7–8: Good
   - 5–6: Revise the topics
   - Below 5: Rewatch the key topics

# Practice MCQs
""",
}


# --------------------------------------------------
# GENERATE SUMMARY, NOTES OR MCQS
# --------------------------------------------------
def generate(video, kind):
    """
    Generate study material from the selected video's transcript.
    Each call generates fresh material for the requested task.
    """

    if kind not in STUDY_TASKS:
        raise ValueError(
            "Unknown study tool. Use summary, notes or mcqs."
        )

    transcript = transcript_text(video)

    if len(transcript) < 80:
        raise RuntimeError(
            "This video's transcript is empty or too short to "
            "create reliable study material."
        )

    # Keep the content tied to this particular video.
    prompt = f"""
You are LearnLens AI, a careful educational assistant.

SOURCE RULES:
- Use ONLY the transcript supplied in this prompt.
- Generate material specific to this video's actual content.
- Never reuse material from another video or previous conversation.
- Do not fill missing details with general knowledge.
- If a requested detail is missing, state that it is not covered.
- Do not invent examples, facts, statistics, names or definitions.
- Use readable Markdown headings, bullets and numbered lists.
- Return the requested study material only.

TASK:
{STUDY_TASKS[kind]}

VIDEO TITLE:
{video.title}

YOUTUBE VIDEO ID:
{video.youtube_id}

TRANSCRIPT:
{transcript[:30000]}
"""

    return ask_gemini(prompt)
