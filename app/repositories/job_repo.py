"""Repository — CRUD collection be_jobs trên MongoDB (riêng của BE)."""
from __future__ import annotations

from typing import Optional

from pymongo import DESCENDING, MongoClient

from app.core.config import settings
from app.core.logging import logger
from app.schemas.job import Job


class JobRepository:
    def __init__(
        self,
        uri: Optional[str] = None,
        db: Optional[str] = None,
        collection: Optional[str] = None,
    ):
        self.uri = uri or settings.mongo_uri
        self.db_name = db or settings.mongo_db
        self.coll_name = collection or settings.mongo_collection
        self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
        self.collection = self.client[self.db_name][self.coll_name]

    # ------------------------------------------------------------
    def save(self, job: Job) -> str:
        """Upsert job theo _id."""
        doc = job.to_mongo_doc()
        self.collection.replace_one({"_id": job.id}, doc, upsert=True)
        return job.id

    def get(self, job_id: str) -> Optional[Job]:
        doc = self.collection.find_one({"_id": job_id})
        return Job.from_mongo_doc(doc) if doc else None

    def list(self, limit: int = 50, skip: int = 0) -> tuple[int, list[Job]]:
        total = self.collection.count_documents({})
        cursor = (
            self.collection.find({})
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        return total, [Job.from_mongo_doc(d) for d in cursor]

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception as e:
            logger.error(f"[JobRepo] Mongo ping lỗi — {e}")
            return False


# Singleton (khởi tạo lười để không cần Mongo lúc import)
_repo: Optional[JobRepository] = None


def get_job_repo() -> JobRepository:
    global _repo
    if _repo is None:
        _repo = JobRepository()
    return _repo
