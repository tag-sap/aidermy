from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class IngredientClaim:
    property_name: str
    direction: str
    strength: float
    confidence: float
    evidence_level: str = 'moderate'
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    source_type: Optional[str] = None
    published_at: Optional[str] = None
    researched_at: Optional[str] = None
    research_version: Optional[str] = None
    source_hash: Optional[str] = None


@dataclass
class IngredientRecord:
    id: Optional[int] = None
    inci_name: str = ''
    canonical_name: str = ''
    normalized_name: str = ''
    synonyms: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_researched_at: Optional[str] = None
    research_status: str = 'missing'
    knowledge_confidence: float = 0.0
    knowledge_version: str = 'v1'
    claims: List[IngredientClaim] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> 'IngredientRecord':
        record = cls(
            id=data.get('id'),
            inci_name=data.get('inci_name', ''),
            canonical_name=data.get('canonical_name', ''),
            normalized_name=data.get('normalized_name', ''),
            synonyms=data.get('synonyms') or [],
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            last_researched_at=data.get('last_researched_at'),
            research_status=data.get('research_status', 'missing'),
            knowledge_confidence=float(data.get('knowledge_confidence', 0.0) or 0.0),
            knowledge_version=data.get('knowledge_version', 'v1'),
        )
        return record
