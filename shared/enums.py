from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Python 3.10-compatible substitute for enum.StrEnum."""


class JobState(StrEnum):
    DISCOVERED = "discovered"
    DEDUPED = "deduped"
    FILTERED_OUT = "filtered_out"
    EXTRACTED = "extracted"
    ANALYZED = "analyzed"
    SCORED = "scored"
    SHORTLISTED = "shortlisted"
    UPDATED = "updated"


class TriageStatus(StrEnum):
    NEW = "new"
    REJECTED = "rejected"
    SHORTLISTED = "shortlisted"
    QUEUED_FOR_PACKAGE = "queued_for_package"
    PACKAGE_READY = "package_ready"


class PackageStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    VALIDATING = "validating"
    PUBLISHING = "publishing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    FAILED = "failed"


class Recommendation(StrEnum):
    SHORTLISTED = "shortlisted"
    REVIEW = "review"
    MAYBE = "maybe"
    ARCHIVE = "archive"
