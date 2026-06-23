"""The data model — the universal blocker everything else reads and writes.

Read CLAUDE.md "The two copyrights" first. The schema is composition-aware on purpose:

    Party --< Split >-- Work        (composition side: writers/publishers; key ISWC + IPI)
    Party --< Split >-- Recording   (master side: performers/label; key ISRC)
                              |
                              v
                        embodies one Work   (nullable FK — work may be unresolved)

A Split attaches to EXACTLY ONE parent (a Work XOR a Recording) — composition splits and
master splits are different ownership and must not be conflated. Splits must sum to 100%
per parent; Postgres can't enforce a cross-row sum cleanly, so that's app-level validation
(see `splits_sum_to_100` / `assert_splits_sum_to_100` below and tests/test_models.py).

RegistrationCheck carries provenance (what/where/when/confidence) behind every gap claim.
RateCard and RawRegistryResponse are defined now (used in Phases 2 and 3) so the schema
isn't a surprise later.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain import (
    ConfidenceBand,
    CopyrightSide,
    PartyRole,
    RegistrationStatus,
    RegistryName,
    RoyaltyType,
)


# --- Shared Postgres enum type objects -------------------------------------------------
# Define each SAEnum ONCE and reuse the instance across columns. If we instead inlined
# `SAEnum(RegistryName, ...)` per column, SQLAlchemy would try to create the same PG enum
# type multiple times. One instance per enum keeps a single canonical type.
#
# values_callable: by DEFAULT SQLAlchemy persists the enum MEMBER NAME (e.g. "MECHANICAL").
# We override it to persist the .value ("mechanical") so the Postgres labels match the JSON
# wire format and our StrEnum values — one canonical spelling everywhere.
def _pg_enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


copyright_side_enum = _pg_enum(CopyrightSide, "copyright_side")
royalty_type_enum = _pg_enum(RoyaltyType, "royalty_type")
registry_name_enum = _pg_enum(RegistryName, "registry_name")
registration_status_enum = _pg_enum(RegistrationStatus, "registration_status")
confidence_band_enum = _pg_enum(ConfidenceBand, "confidence_band")
party_role_enum = _pg_enum(PartyRole, "party_role")

# Percent columns: 0.00–100.00. Confidence scores: 0.0000–1.0000.
PERCENT = Numeric(5, 2)
CONFIDENCE = Numeric(5, 4)

SPLIT_SUM_TOLERANCE = Decimal("0.01")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# --- Core entities ---------------------------------------------------------------------


class Party(Base, TimestampMixin):
    """A person or organization with an interest in a copyright.

    `ipi` is the IPI name number — the key that lets a registry match a work to a writer.
    Nullable because labels/distributors may not have one and indie writers are often
    un-indexed; `role` is the party's role in THIS context (a human can be both a writer
    and a performer, represented as separate Party rows for v1 simplicity).
    """

    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    ipi: Mapped[str | None] = mapped_column(String(11), index=True, nullable=True)
    role: Mapped[PartyRole] = mapped_column(party_role_enum, nullable=False)

    splits: Mapped[list[Split]] = relationship(back_populates="party")


class Work(Base, TimestampMixin):
    """The composition (the song itself) — melody + lyrics.

    Keyed by ISWC, nullable because Stage 1's work_resolver can't always resolve it
    (MusicBrainz won't have work-relations for every indie track). When ISWC is missing we
    still keep the work + writer splits from manual entry so the composition-side checks
    have something to join on.
    """

    __tablename__ = "works"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # ISWC format T-123.456.789-0. Unique, but Postgres treats NULLs as distinct so many
    # unresolved works can coexist.
    iswc: Mapped[str | None] = mapped_column(String(15), unique=True, nullable=True)

    recordings: Mapped[list[Recording]] = relationship(back_populates="work")
    splits: Mapped[list[Split]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    registrations: Mapped[list[RegistrationCheck]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )

    def split_percents(self) -> list[Decimal]:
        return [s.percent for s in self.splits]


class Recording(Base, TimestampMixin):
    """The master (the specific sound recording).

    Keyed by ISRC. `work_id` is nullable on purpose: a recording can exist before (or
    without) its work being resolved — Stage 1 resolves the recording first, then attempts
    the work as a second step.
    """

    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # ISRC format CCXXXYYNNNNN (12 chars). Indexed but NOT unique for v1: manual entry and
    # re-identification can legitimately produce duplicates we'd rather dedupe in a service
    # than reject at insert. (Revisit once identity resolution is trusted.)
    isrc: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spotify_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id"), nullable=True)
    work: Mapped[Work | None] = relationship(back_populates="recordings")

    splits: Mapped[list[Split]] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    registrations: Mapped[list[RegistrationCheck]] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )

    def split_percents(self) -> list[Decimal]:
        return [s.percent for s in self.splits]


class Split(Base, TimestampMixin):
    """An ownership share: a Party owns `percent`% of a Work XOR a Recording.

    The XOR check constraint enforces "attaches to exactly one parent" at the DB level.
    The sum-to-100 rule per parent is enforced in the app (see helpers below).
    """

    __tablename__ = "splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id"), nullable=True)
    recording_id: Mapped[int | None] = mapped_column(
        ForeignKey("recordings.id"), nullable=True
    )
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), nullable=False)
    percent: Mapped[Decimal] = mapped_column(PERCENT, nullable=False)
    role: Mapped[PartyRole] = mapped_column(party_role_enum, nullable=False)

    work: Mapped[Work | None] = relationship(back_populates="splits")
    recording: Mapped[Recording | None] = relationship(back_populates="splits")
    party: Mapped[Party] = relationship(back_populates="splits")

    __table_args__ = (
        # Exactly one parent: (work XOR recording). `<>` is boolean XOR in Postgres.
        CheckConstraint(
            "(work_id IS NOT NULL) <> (recording_id IS NOT NULL)",
            name="split_exactly_one_parent",
        ),
        CheckConstraint("percent >= 0 AND percent <= 100", name="split_percent_range"),
    )


class RegistrationCheck(Base, TimestampMixin):
    """One check of one identity against one registry — WITH provenance.

    This is the evidence behind every "you're leaking money here": which registry, on
    which copyright side, what status, how confident, when, and a pointer to the cached raw
    response. Named `RegistrationCheck` (not `RegistrationStatus`) so the table doesn't
    collide with the `RegistrationStatus` enum it stores in its `status` column.
    """

    __tablename__ = "registration_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id"), nullable=True)
    recording_id: Mapped[int | None] = mapped_column(
        ForeignKey("recordings.id"), nullable=True
    )

    registry: Mapped[RegistryName] = mapped_column(registry_name_enum, nullable=False)
    side: Mapped[CopyrightSide] = mapped_column(copyright_side_enum, nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        registration_status_enum, nullable=False
    )

    confidence_band: Mapped[ConfidenceBand | None] = mapped_column(
        confidence_band_enum, nullable=True
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(CONFIDENCE, nullable=True)
    matched_identifier: Mapped[str | None] = mapped_column(String(64), nullable=True)

    checked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_response_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_registry_responses.id"), nullable=True
    )

    work: Mapped[Work | None] = relationship(back_populates="registrations")
    recording: Mapped[Recording | None] = relationship(back_populates="registrations")
    raw_response: Mapped[RawRegistryResponse | None] = relationship()

    __table_args__ = (
        # A check targets exactly one of work/recording (which one depends on `side`).
        CheckConstraint(
            "(work_id IS NOT NULL) <> (recording_id IS NOT NULL)",
            name="regcheck_exactly_one_target",
        ),
    )


class RawRegistryResponse(Base, TimestampMixin):
    """A timestamped raw response from a registry — dev-speed cache + the evidence trail.

    Lands with Phase 3. `content_hash` lets us dedupe identical responses and detect when a
    registry's HTML changed under us.
    """

    __tablename__ = "raw_registry_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    registry: Mapped[RegistryName] = mapped_column(registry_name_enum, nullable=False)
    request_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RateCard(Base, TimestampMixin):
    """A versioned royalty rate. Lands with Phase 2.

    Every row carries `version` + `effective_date` so a past estimate can be reproduced at
    the rate that was effective then. rates.yaml SEEDS this table — the table, not the file,
    is the source of truth. Never hardcode a rate in the calculator.
    """

    __tablename__ = "rate_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    royalty_type: Mapped[RoyaltyType] = mapped_column(royalty_type_enum, nullable=False)
    # Some rates are registry-specific (a given PRO's per-stream approximation); others are
    # statutory and registry-agnostic (mechanical) — hence nullable.
    registry: Mapped[RegistryName | None] = mapped_column(registry_name_enum, nullable=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)  # per_stream | per_play | percent
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "royalty_type",
            "registry",
            "version",
            "effective_date",
            name="rate_card_version_unique",
        ),
    )


# --- App-level validation (cross-row sum, which the DB can't enforce cleanly) -----------


def splits_sum_to_100(
    percents: list[Decimal] | list[float], tolerance: Decimal = SPLIT_SUM_TOLERANCE
) -> bool:
    """True if the given split percentages sum to 100 within `tolerance`.

    An empty list returns False — "no splits" is not a valid fully-owned parent. Tolerance
    absorbs rounding (e.g. three-way 33.33/33.33/33.34).
    """

    if not percents:
        return False
    total = sum(Decimal(str(p)) for p in percents)
    return abs(total - Decimal("100")) <= tolerance


def assert_splits_sum_to_100(
    percents: list[Decimal] | list[float], tolerance: Decimal = SPLIT_SUM_TOLERANCE
) -> None:
    """Raise ValueError if splits don't sum to 100 within tolerance.

    The service layer calls this before committing a Work/Recording with its splits. (We
    keep it an explicit call rather than an automatic before_flush listener so partial
    in-progress states during a transaction aren't rejected — revisit if we want hard
    enforcement.)
    """

    if not splits_sum_to_100(percents, tolerance):
        total = sum(Decimal(str(p)) for p in percents) if percents else Decimal("0")
        raise ValueError(
            f"Splits must sum to 100% (got {total}; tolerance ±{tolerance})."
        )
