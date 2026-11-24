"""Engineering assumptions the calculation reads. They come from a data file, never from code."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.model import RoofType


@dataclass(frozen=True, slots=True)
class EngineeringAssumptions:
    coverage_ratio_by_roof_type: Mapping[RoofType, Decimal]
    system_loss_percent: Decimal
    flat_roof_tilt_deg: Decimal

    def coverage_ratio(self, roof_type: RoofType) -> Decimal:
        try:
            return self.coverage_ratio_by_roof_type[roof_type]
        except KeyError:
            raise ValueError(f"no coverage ratio configured for {roof_type} roofs") from None
