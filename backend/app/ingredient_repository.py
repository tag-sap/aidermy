import json
import sqlite3
from typing import Any, Dict, List, Optional

from .database import get_connection, AIDERMY_DB


class IngredientRepository:
    def __init__(self, db_path: str = AIDERMY_DB):
        self.db_path = db_path

    def ensure_ingredient_tables(self) -> None:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS ingredients_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inci_name TEXT NOT NULL,
                canonical_name TEXT,
                normalized_name TEXT NOT NULL,
                synonyms TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_researched_at TIMESTAMP,
                research_status TEXT DEFAULT 'missing',
                knowledge_confidence REAL DEFAULT 0,
                knowledge_version TEXT DEFAULT 'v1'
            )
            '''
        )

        # Миграция: структурные поля ингредиента (skin_effects / безопасность),
        # требуемые архитектурой Ingredient DB. Не ломаем старые БД.
        catalog_cols = {r[1] for r in cursor.execute("PRAGMA table_info(ingredients_catalog)").fetchall()}
        for col, ddl in [
            ("functions", "TEXT DEFAULT ''"),
            ("skin_effects", "TEXT DEFAULT ''"),
            ("hydration", "REAL DEFAULT 0"),
            ("barrier_support", "REAL DEFAULT 0"),
            ("soothing", "REAL DEFAULT 0"),
            ("oil_control", "REAL DEFAULT 0"),
            ("brightening", "REAL DEFAULT 0"),
            ("irritation_risk", "REAL DEFAULT 0"),
            ("comedogenicity", "REAL DEFAULT 0"),
            ("sensitization", "REAL DEFAULT 0"),
            ("evidence_level", "TEXT DEFAULT 'moderate'"),
            ("sources", "TEXT DEFAULT ''"),
        ]:
            if col not in catalog_cols:
                cursor.execute(f"ALTER TABLE ingredients_catalog ADD COLUMN {col} {ddl}")

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS ingredient_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_id INTEGER NOT NULL,
                property_name TEXT NOT NULL,
                direction TEXT NOT NULL,
                strength REAL NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                evidence_level TEXT DEFAULT 'moderate',
                source_url TEXT,
                source_title TEXT,
                source_type TEXT,
                published_at TEXT,
                researched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                research_version TEXT DEFAULT 'v1',
                source_hash TEXT,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients_catalog(id)
            )
            '''
        )

        # Allergen / Sensitizer DB — отдельный слой, связанный с Ingredient DB.
        # Не смешиваем с irritation/comedogenicity (это поля ingredient record).
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS allergen_sensitizer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_id INTEGER NOT NULL,
                is_allergen INTEGER DEFAULT 0,
                is_sensitizer INTEGER DEFAULT 0,
                allergen_level TEXT DEFAULT 'none',
                sensitization_potential REAL DEFAULT 0,
                evidence_level TEXT DEFAULT 'moderate',
                confidence REAL DEFAULT 0,
                sources TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ingredient_id),
                FOREIGN KEY (ingredient_id) REFERENCES ingredients_catalog(id)
            )
            '''
        )

        # Уникальность normalized_name нужна для ON CONFLICT(normalized_name) в upsert.
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ingredients_catalog_normalized "
            "ON ingredients_catalog (normalized_name)"
        )
        conn.commit()
        conn.close()

    def upsert_ingredient(self, inci_name: str, canonical_name: str = '', normalized_name: str = '') -> int:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        canonical = canonical_name or inci_name
        normalized = normalized_name or inci_name.strip().lower()
        cursor.execute(
            '''
            INSERT INTO ingredients_catalog (inci_name, canonical_name, normalized_name, synonyms, updated_at)
            VALUES (?, ?, ?, '', CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            ''',
            (inci_name, canonical, normalized)
        )
        conn.commit()
        row = cursor.execute(
            'SELECT id FROM ingredients_catalog WHERE normalized_name = ? ORDER BY id DESC LIMIT 1',
            (normalized,)
        ).fetchone()
        conn.close()
        return int(row['id']) if row else 0

    def add_claim(self, ingredient_id: int, property_name: str, direction: str, strength: float, confidence: float,
                  evidence_level: str = 'moderate', source_url: str = '', source_title: str = '',
                  source_type: str = '', published_at: str = '', research_version: str = 'v1', source_hash: str = '') -> None:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO ingredient_claims (
                ingredient_id, property_name, direction, strength, confidence, evidence_level,
                source_url, source_title, source_type, published_at, research_version, source_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                ingredient_id,
                property_name,
                direction,
                strength,
                confidence,
                evidence_level,
                source_url,
                source_title,
                source_type,
                published_at,
                research_version,
                source_hash,
            )
        )
        conn.commit()
        conn.close()

    def get_knowledge_map(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        rows = cursor.execute(
            '''
            SELECT i.normalized_name, c.property_name, c.direction, c.strength, c.confidence
            FROM ingredients_catalog i
            LEFT JOIN ingredient_claims c ON c.ingredient_id = i.id
            '''
        ).fetchall()
        conn.close()

        knowledge: Dict[str, Dict[str, Dict[str, float]]] = {}
        for row in rows:
            if not row['normalized_name']:
                continue
            ingredient = row['normalized_name'].lower()
            property_name = row['property_name']
            direction = row['direction']
            if not property_name:
                continue
            knowledge.setdefault(ingredient, {})
            if direction and property_name:
                knowledge[ingredient][property_name] = {
                    'direction': direction,
                    'strength': float(row['strength'] or 0),
                    'confidence': float(row['confidence'] or 0),
                }
        return knowledge

    # ------------------------------------------------------------------
    # Методы для Ingredient Enrichment и Allergen/Sensitizer DB
    # ------------------------------------------------------------------

    def _synonym_names(self, synonyms_raw: str) -> List[str]:
        if not synonyms_raw:
            return []
        try:
            value = json.loads(synonyms_raw)
            if isinstance(value, list):
                return [str(x).strip().lower() for x in value if str(x).strip()]
        except Exception:
            pass
        return [x.strip().lower() for x in synonyms_raw.split(',') if x.strip()]

    def get_known_names(self) -> Dict[str, int]:
        """normalized_name + synonyms -> ingredient id (для быстрой проверки «известен?»)."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT id, normalized_name, synonyms FROM ingredients_catalog"
        ).fetchall()
        conn.close()

        known: Dict[str, int] = {}
        for row in rows:
            known.setdefault((row['normalized_name'] or '').strip().lower(), row['id'])
            for syn in self._synonym_names(row['synonyms']):
                known.setdefault(syn, row['id'])
        return known

    def resolve_ingredient(self, name: str) -> Optional[Dict[str, Any]]:
        """Ищет ингредиент по normalized_name или синониму."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT * FROM ingredients_catalog WHERE normalized_name = ? LIMIT 1",
            (name.strip().lower(),),
        ).fetchone()
        if row is None:
            for r in cursor.execute("SELECT id, normalized_name, synonyms FROM ingredients_catalog").fetchall():
                if name.strip().lower() in self._synonym_names(r['synonyms']):
                    row = cursor.execute(
                        "SELECT * FROM ingredients_catalog WHERE id = ?", (r['id'],)
                    ).fetchone()
                    break
        conn.close()
        return dict(row) if row else None

    def save_enriched_ingredient(self, data: Dict[str, Any]) -> int:
        """Сохраняет структурированную запись ингредиента (AI enrichment).

        data может содержать: inci_name, canonical_name, normalized_name,
        synonyms, functions, skin_effects, hydration, barrier_support, soothing,
        oil_control, brightening, irritation_risk, comedogenicity, sensitization,
        evidence_level, confidence, sources, claims[], allergen{}.
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        inci = str(data.get('inci_name') or data.get('canonical_name') or '').strip()
        if not inci:
            conn.close()
            return 0
        canonical = str(data.get('canonical_name') or inci)
        normalized = str(data.get('normalized_name') or inci.strip().lower())
        synonyms = data.get('synonyms') or []
        if isinstance(synonyms, str):
            synonyms = [s.strip() for s in synonyms.split(',') if s.strip()]

        def _num(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        functions = json.dumps(data.get('functions') or [], ensure_ascii=False)
        skin_effects = json.dumps(data.get('skin_effects') or [], ensure_ascii=False)
        sources = json.dumps(data.get('sources') or [], ensure_ascii=False)
        evidence_level = str(data.get('evidence_level') or 'moderate')
        knowledge_confidence = _num(data.get('confidence') or data.get('knowledge_confidence'), 0.0)

        cursor.execute(
            '''
            INSERT INTO ingredients_catalog (
                inci_name, canonical_name, normalized_name, synonyms,
                functions, skin_effects, hydration, barrier_support, soothing,
                oil_control, brightening, irritation_risk, comedogenicity,
                sensitization, evidence_level, sources,
                research_status, knowledge_confidence, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'researched', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(normalized_name) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                synonyms = excluded.synonyms,
                functions = excluded.functions,
                skin_effects = excluded.skin_effects,
                hydration = excluded.hydration,
                barrier_support = excluded.barrier_support,
                soothing = excluded.soothing,
                oil_control = excluded.oil_control,
                brightening = excluded.brightening,
                irritation_risk = excluded.irritation_risk,
                comedogenicity = excluded.comedogenicity,
                sensitization = excluded.sensitization,
                evidence_level = excluded.evidence_level,
                sources = excluded.sources,
                research_status = 'researched',
                knowledge_confidence = excluded.knowledge_confidence,
                last_researched_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (
                inci, canonical, normalized, json.dumps(synonyms, ensure_ascii=False),
                functions, skin_effects,
                _num(data.get('hydration')), _num(data.get('barrier_support')),
                _num(data.get('soothing')), _num(data.get('oil_control')),
                _num(data.get('brightening')), _num(data.get('irritation_risk')),
                _num(data.get('comedogenicity')), _num(data.get('sensitization')),
                evidence_level, sources, knowledge_confidence,
            ),
        )

        row = cursor.execute(
            "SELECT id FROM ingredients_catalog WHERE normalized_name = ?", (normalized,)
        ).fetchone()
        ingredient_id = int(row['id']) if row else 0

        # Claims (для scoring engine: property/direction/strength/confidence).
        for claim in data.get('claims') or []:
            prop = str(claim.get('property_name') or claim.get('property') or '').strip()
            direction = str(claim.get('direction') or 'neutral').strip().lower()
            if not prop:
                continue
            cursor.execute(
                '''
                INSERT INTO ingredient_claims (
                    ingredient_id, property_name, direction, strength, confidence, evidence_level
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    ingredient_id, prop, direction,
                    _num(claim.get('strength')), _num(claim.get('confidence')),
                    str(claim.get('evidence_level') or evidence_level),
                ),
            )

        # Allergen / Sensitizer DB.
        allergen = data.get('allergen') or {}
        if isinstance(allergen, dict):
            is_allergen = 1 if (allergen.get('is_allergen') or allergen.get('allergen')) else 0
            is_sensitizer = 1 if (allergen.get('is_sensitizer') or allergen.get('sensitizer')) else 0
            cursor.execute(
                '''
                INSERT INTO allergen_sensitizer (
                    ingredient_id, is_allergen, is_sensitizer, allergen_level,
                    sensitization_potential, evidence_level, confidence, sources, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ingredient_id) DO UPDATE SET
                    is_allergen = excluded.is_allergen,
                    is_sensitizer = excluded.is_sensitizer,
                    allergen_level = excluded.allergen_level,
                    sensitization_potential = excluded.sensitization_potential,
                    evidence_level = excluded.evidence_level,
                    confidence = excluded.confidence,
                    sources = excluded.sources,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (
                    ingredient_id, is_allergen, is_sensitizer,
                    str(allergen.get('allergen_level') or ('high' if is_allergen else 'none')),
                    _num(allergen.get('sensitization_potential')),
                    str(allergen.get('evidence_level') or evidence_level),
                    _num(allergen.get('confidence'), 0.5),
                    json.dumps(allergen.get('sources') or [], ensure_ascii=False),
                ),
            )

        conn.commit()
        conn.close()
        return ingredient_id

    def get_safety_map(self) -> Dict[str, Dict[str, Any]]:
        """normalized_name -> allergen/sensitizer сведения для проверки ограничений."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        rows = cursor.execute(
            '''
            SELECT i.normalized_name, a.is_allergen, a.is_sensitizer, a.allergen_level,
                   a.sensitization_potential, a.confidence
            FROM ingredients_catalog i
            LEFT JOIN allergen_sensitizer a ON a.ingredient_id = i.id
            '''
        ).fetchall()
        conn.close()

        safety: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if not row['normalized_name']:
                continue
            safety[row['normalized_name'].lower()] = {
                'is_allergen': bool(row['is_allergen']),
                'is_sensitizer': bool(row['is_sensitizer']),
                'allergen_level': row['allergen_level'] or 'none',
                'sensitization_potential': float(row['sensitization_potential'] or 0),
                'confidence': float(row['confidence'] or 0),
            }
        return safety
