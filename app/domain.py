"""Cross-stage domain enums — the shared vocabulary every stage speaks.

These are deliberately small and stable. They encode the bedrock distinction from
CLAUDE.md: a recording is TWO copyrights (master vs composition), keyed and collected
differently. Keep the enum values lowercase/stable — they become Postgres enum types
and JSON wire values, so renaming a value is a migration, not a refactor.
"""

from __future__ import annotations

from enum import Enum


class CopyrightSide(str, Enum):
    """Which of the two copyrights a thing concerns.

    MASTER is keyed by ISRC; COMPOSITION is keyed by ISWC + writer IPI. This is the
    single most important distinction in the system — registries live on one side or
    the other, and ISRC does NOT join to the composition side.
    """

    MASTER = "master"
    COMPOSITION = "composition"


class RoyaltyType(str, Enum):
    """Royalty streams. Each has a DIFFERENT rate base — never one flat formula.

    - MECHANICAL: composition, per-stream/per-unit, collected by the MLC.
    - PERFORMANCE: composition, pooled/survey distribution, collected by PROs.
    - DIGITAL_PERFORMANCE: master, per-play on non-interactive only, SoundExchange.
    """

    MECHANICAL = "mechanical"
    PERFORMANCE = "performance"
    DIGITAL_PERFORMANCE = "digital_performance"


class RegistryName(str, Enum):
    """Collection societies / databases we check or estimate against."""

    MLC = "mlc"
    ASCAP = "ascap"
    BMI = "bmi"
    SESAC = "sesac"
    SOUNDEXCHANGE = "soundexchange"


class RegistrationStatus(str, Enum):
    """Outcome of checking one identity against one registry.

    NOT_FOUND is the money signal (a candidate leak). AMBIGUOUS / UNRESOLVED exist so we
    never assert a gap we aren't confident about — a false positive (telling someone they
    leak when they don't) is worse than a miss.
    """

    REGISTERED = "registered"  # confident match found at the registry
    NOT_FOUND = "not_found"  # checked, no match — candidate leak
    AMBIGUOUS = "ambiguous"  # matched but below confidence threshold — flag a human
    UNRESOLVED = "unresolved"  # couldn't even check (e.g. no work identity) — degrade gracefully
    ERROR = "error"  # the check itself failed (scraper/network)


class ConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PartyRole(str, Enum):
    """A party's role on a split. Writers/publishers sit on the composition side;
    performers/labels/distributors on the master side."""

    WRITER = "writer"
    PUBLISHER = "publisher"
    PERFORMER = "performer"
    LABEL = "label"
    DISTRIBUTOR = "distributor"


# Which copyright side each registry sits on. Adapters also declare this on themselves
# (`keys_on`), but a central map is handy for routing an identity to the right checks.
REGISTRY_SIDE: dict[RegistryName, CopyrightSide] = {
    RegistryName.MLC: CopyrightSide.COMPOSITION,
    RegistryName.ASCAP: CopyrightSide.COMPOSITION,
    RegistryName.BMI: CopyrightSide.COMPOSITION,
    RegistryName.SESAC: CopyrightSide.COMPOSITION,
    RegistryName.SOUNDEXCHANGE: CopyrightSide.MASTER,
}

# Which royalty type each registry collects — used to route estimates per royalty type.
REGISTRY_ROYALTY: dict[RegistryName, RoyaltyType] = {
    RegistryName.MLC: RoyaltyType.MECHANICAL,
    RegistryName.ASCAP: RoyaltyType.PERFORMANCE,
    RegistryName.BMI: RoyaltyType.PERFORMANCE,
    RegistryName.SESAC: RoyaltyType.PERFORMANCE,
    RegistryName.SOUNDEXCHANGE: RoyaltyType.DIGITAL_PERFORMANCE,
}
