"""Spatial ML experiment boundary.

The current model does NOT include any location/spatial information. This module
defines the interface for future spatial modeling experiments without accidentally
implying the model is already spatially aware.

Current features (all temporal/rainfall-based):
  r1, sum3, sum7, sum14, sum30, rainy_frac14, dry_run, doy_sin, doy_cos

NO spatial features are used. The model is a pooled model trained on data from
multiple locations but treats all locations identically — it has no mechanism to
produce location-specific predictions beyond what the local rainfall history provides.

IMPORTANT: Do NOT simply add latitude, longitude, or location_id as features.
Such additions require careful experimental evaluation because:
  - 5 locations is far too few for a model to learn spatial patterns
  - location_id is a categorical variable that would overfit with so few locations
  - latitude/longitude as raw features assume a linear spatial relationship
  - any spatial feature must be validated against the existing baseline

Possible approaches for future evaluation (none implemented):
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class SpatialApproach:
    """Description of a candidate spatial modeling approach."""
    name: str
    description: str
    requirements: str
    status: Literal["not_implemented", "experimental", "evaluated"] = "not_implemented"
    notes: str | None = None


# Registry of candidate approaches — documentation only, no implementation
SPATIAL_APPROACHES = [
    SpatialApproach(
        name="pooled_with_geographic_features",
        description="Add geographic features (elevation, distance to coast, "
                    "climatological normal rainfall) to the existing pooled model.",
        requirements="Requires curated geographic/climatological data per location. "
                     "At least 20+ locations recommended to avoid overfitting.",
        notes="Elevation and distance-to-coast are physically motivated; raw lat/lon are not."
    ),
    SpatialApproach(
        name="climatology_derived_features",
        description="Add location-specific climatological features: long-term mean rainfall, "
                    "variability, typical onset date, seasonal cycle parameters.",
        requirements="Requires sufficient historical data per location (10+ years) to compute "
                     "stable climatological statistics.",
        notes="These features summarize what the model could learn from the data itself "
              "but make the information explicitly available."
    ),
    SpatialApproach(
        name="per_location_models",
        description="Train separate models per location, each specialized to local patterns.",
        requirements="Requires enough training data per location (15+ years each). "
                     "Not feasible with 5 pilot locations and limited history.",
        notes="Avoids the pooling assumption but sacrifices sample size."
    ),
    SpatialApproach(
        name="hierarchical_model",
        description="Mixed-effects or hierarchical Bayesian model with location-level "
                    "random effects and shared fixed effects.",
        requirements="Requires statistical modeling expertise and sufficient locations "
                     "(10+) to estimate random effects meaningfully.",
        notes="Theoretically attractive but complex; overkill for 5 locations."
    ),
    SpatialApproach(
        name="coordinate_aware_features",
        description="Spatial encoding of coordinates (e.g. spatial basis functions, "
                    "distance-based features, or learned embeddings).",
        requirements="Requires 50+ locations to learn spatial structure. "
                     "Not meaningful with 5 pilot locations.",
        notes="Risk of severe overfitting with few locations."
    ),
]


def spatial_awareness_status() -> dict:
    """Report the current state of spatial awareness in the ML system.

    This is the authoritative check: if this returns is_spatially_aware=False,
    no part of the system should claim spatial/location-specific predictions.
    """
    from .features import FEATURES

    spatial_features_present = any(
        f in FEATURES for f in ("latitude", "longitude", "location_id",
                                "elevation", "dist_coast")
    )

    return {
        "is_spatially_aware": False,
        "spatial_features_in_model": spatial_features_present,
        "current_features": list(FEATURES),
        "n_features": len(FEATURES),
        "location_treatment": "pooled_identical",
        "location_treatment_note": (
            "All locations are treated identically by the model. "
            "The model uses only temporal and rainfall-based features. "
            "Predictions differ between locations only because their "
            "input rainfall histories differ, not because the model "
            "has learned location-specific patterns."
        ),
        "candidate_approaches": [
            {"name": a.name, "status": a.status, "description": a.description}
            for a in SPATIAL_APPROACHES
        ],
    }
