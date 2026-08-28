from fastapi import APIRouter

from . import (
    ai,
    ai_settings,
    analytics,
    backup,
    chat,
    courses,
    exercises,
    flashcards,
    folders,
    fs,
    health,
    jobs,
    materials,
    notes,
    onboarding,
    profiles,
    quiz,
    search,
    skills,
    sources,
    trash,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(materials.router)
api_router.include_router(materials.blobs_router)
api_router.include_router(search.router)
api_router.include_router(folders.router)
api_router.include_router(courses.router)
api_router.include_router(chat.router)
api_router.include_router(quiz.router)
api_router.include_router(exercises.router)
api_router.include_router(notes.router)
api_router.include_router(flashcards.router)
api_router.include_router(analytics.router)
api_router.include_router(backup.router)
api_router.include_router(profiles.router)
api_router.include_router(sources.router)
api_router.include_router(fs.router)
api_router.include_router(skills.router)
api_router.include_router(onboarding.router)
api_router.include_router(ai_settings.router)
api_router.include_router(ai.router)
api_router.include_router(trash.router)
