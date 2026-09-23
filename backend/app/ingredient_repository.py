import json
import sqlite3
from typing import Any, Dict, List, Optional

from .database import get_connection, AIDERMY_DB


# ---------------------------------------------------------------------------
# Фаза 3A — seed-данные взаимодействий.
# Перенесены из shelf_compatibility.CONFLICT_RULES (классовые эвристики),
# развёрнутые в канонические пары ингредиентов.
# source="seed", evidence="legacy heuristic", confidence=0.2 (низкий) — НЕ выдаём
# за научно подтверждённые взаимодействия.
# ---------------------------------------------------------------------------
_SEED_RETINOIDS = ["retinol", "tretinoin", "adapalene", "tazarotene"]
_SEED_AHA = ["glycolic acid", "lactic acid", "mandelic acid", "malic acid"]
_SEED_BHA = ["salicylic acid"]
_SEED_VITC = ["ascorbic acid"]
_SEED_BP = ["benzoyl peroxide"]

# (axis, direction, list_a, list_b, label)
_SEED_RULES = [
    ("irritation", "positive", _SEED_RETINOIDS, _SEED_AHA + _SEED_BHA, "Ретиноиды + AHA/BHA-кислоты"),
    ("irritation", "positive", ["niacinamide"], _SEED_VITC, "Ниацинамид + L-аскорбиновая кислота"),
    ("irritation", "positive", _SEED_RETINOIDS, _SEED_BP, "Ретиноиды + бензоилпероксид"),
    ("barrier", "negative", _SEED_AHA, _SEED_BHA, "AHA + BHA (двойное отшелушивание)"),
]


# ---------------------------------------------------------------------------
# Фаза 4 — Taxonomy / Class layer (routing/index, НЕ доказательство interaction).
#
# _TAXONOMY_SEED: классы + подклассы + принадлежащие ингредиенты (canonical names).
# _CLASS_ROUTES: классовые routing-правила (из CONFLICT_RULES) — только для
# сокращения пространства поиска, НЕ для установления факта взаимодействия.
# ---------------------------------------------------------------------------
_TAXONOMY_SEED = {
    "retinoids": {
        "label": "Ретиноиды",
        "ingredients": ["retinol", "retinal", "retinyl palmitate", "tretinoin", "adapalene", "tazarotene"],
    },
    "exfoliants": {
        "label": "Отшелушивающие",
        "subclasses": {
            "aha": {"label": "AHA", "ingredients": ["glycolic acid", "lactic acid", "mandelic acid", "malic acid"]},
            "bha": {"label": "BHA", "ingredients": ["salicylic acid"]},
            "pha": {"label": "PHA", "ingredients": ["gluconolactone", "lactobionic acid"]},
        },
    },
    "vitamin_c": {
        "label": "Витамин C",
        "ingredients": [
            "ascorbic acid", "ascorbyl palmitate", "ascorbyl glucoside",
            "sodium ascorbyl phosphate", "magnesium ascorbyl phosphate",
            "3-o-ethyl ascorbic acid",
        ],
    },
    "niacinamide": {"label": "Ниацинамид", "ingredients": ["niacinamide", "nicotinamide"]},
    "benzoyl_peroxide": {"label": "Бензоилпероксид", "ingredients": ["benzoyl peroxide"]},
}

# Классовые routing-правила: (классы A, классы B). Пара классов «релевантна»,
# если существует пересечение. Это НЕ факт interaction.
_CLASS_ROUTES = [
    (("retinoids",), ("aha", "bha")),
    (("niacinamide",), ("vitamin_c",)),
    (("retinoids",), ("benzoyl_peroxide",)),
    (("aha",), ("bha",)),
]


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

        # Дедупликация: в старых БД upsert_ingredient мог создать несколько строк с
        # одинаковым normalized_name (без UNIQUE-индекса). Объединяем дубли, чтобы
        # ниже корректно создать уникальный индекс. Claims переносим на каноническую строку.
        self._dedupe_catalog(cursor)

        # Уникальность normalized_name нужна для ON CONFLICT(normalized_name) в upsert.
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ingredients_catalog_normalized "
            "ON ingredients_catalog (normalized_name)"
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _dedupe_catalog(cursor) -> int:
        """Объединяет дубликаты ingredients_catalog по normalized_name.

        Канонической считается строка с минимальным id; claims дублей переносятся
        на неё, строки-дубли удаляются. Возвращает число удалённых строк.
        """
        groups = cursor.execute(
            "SELECT normalized_name, COUNT(*) AS c FROM ingredients_catalog "
            "WHERE normalized_name IS NOT NULL AND normalized_name != '' "
            "GROUP BY normalized_name HAVING c > 1"
        ).fetchall()
        removed = 0
        for group in groups:
            name = group["normalized_name"]
            ids = [r["id"] for r in cursor.execute(
                "SELECT id FROM ingredients_catalog WHERE normalized_name = ? ORDER BY id ASC",
                (name,),
            ).fetchall()]
            keep = ids[0]
            for dup_id in ids[1:]:
                cursor.execute(
                    "UPDATE ingredient_claims SET ingredient_id = ? WHERE ingredient_id = ?",
                    (keep, dup_id),
                )
                cursor.execute(
                    "UPDATE allergen_sensitizer SET ingredient_id = ? WHERE ingredient_id = ?",
                    (keep, dup_id),
                )
                cursor.execute("DELETE FROM ingredients_catalog WHERE id = ?", (dup_id,))
                removed += 1
        return removed

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

    def get_canonical_knowledge_map(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Каноническая knowledge map на 6 осях (axes.AXES).

        НЕ используется scoring'ом на Фазе 1 — это read-слой для будущего
        Ingredient Graph (Фаза 2). Non-destructive: исходные claims не меняются.
        """
        from .axes import canonicalize_knowledge_map
        return canonicalize_knowledge_map(self.get_knowledge_map())

    # ------------------------------------------------------------------
    # Фаза 3A — Ingredient Interactions (глобальная knowledge-таблица)
    # ------------------------------------------------------------------
    def ensure_interaction_tables(self) -> None:
        """Создаёт ingredient_interactions (БЕЗ seed — seed отдельно)."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS ingredient_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_a TEXT NOT NULL,
                ingredient_b TEXT NOT NULL,
                axis TEXT NOT NULL,
                direction TEXT NOT NULL,
                strength REAL NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                evidence TEXT DEFAULT '',
                source TEXT DEFAULT '',
                source_type TEXT DEFAULT '',
                interaction_type TEXT DEFAULT '',
                research_version TEXT DEFAULT 'v1',
                knowledge_version TEXT DEFAULT 'v1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ingredient_a, ingredient_b, axis)
            )
            '''
        )
        conn.commit()
        conn.close()

    def seed_interactions(self) -> int:
        """Вставляет seed-данные взаимодействий (идемпотентно).

        Возвращает число вставленных строк в этот вызов (0 при повторном запуске).
        """
        from .ingredient_normalizer import normalize_ingredient_name

        self.ensure_interaction_tables()
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        inserted = 0
        for axis, direction, list_a, list_b, label in _SEED_RULES:
            for a in list_a:
                for b in list_b:
                    a_n = normalize_ingredient_name(a)
                    b_n = normalize_ingredient_name(b)
                    a_c, b_c = sorted([a_n, b_n])  # канонический порядок пары
                    cursor.execute(
                        '''
                        INSERT OR IGNORE INTO ingredient_interactions (
                            ingredient_a, ingredient_b, axis, direction, strength,
                            confidence, evidence, source, source_type, interaction_type,
                            research_version, knowledge_version, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''',
                        (
                            a_c, b_c, axis, direction, 0.5, 0.2,
                            f"legacy heuristic: {label}", "seed", "heuristic", "conflict",
                            "seed-v1", "v1",
                        ),
                    )
                    inserted += cursor.rowcount
        conn.commit()
        conn.close()
        return inserted

    def save_interaction(
        self,
        ingredient_a: str,
        ingredient_b: str,
        axis: str,
        direction: str,
        strength: float = 0.0,
        confidence: float = 0.0,
        evidence: str = "",
        source: str = "",
        source_type: str = "",
        interaction_type: str = "",
        research_version: str = "v1",
        knowledge_version: str = "v1",
    ) -> Optional[Dict[str, Any]]:
        """Сохраняет interaction (канонический порядок пары, без дублей)."""
        from .ingredient_normalizer import normalize_ingredient_name

        self.ensure_interaction_tables()
        a_c, b_c = sorted([normalize_ingredient_name(ingredient_a), normalize_ingredient_name(ingredient_b)])
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT OR IGNORE INTO ingredient_interactions (
                ingredient_a, ingredient_b, axis, direction, strength,
                confidence, evidence, source, source_type, interaction_type,
                research_version, knowledge_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''',
            (
                a_c, b_c, axis, direction, strength, confidence,
                evidence, source, source_type, interaction_type,
                research_version, knowledge_version,
            ),
        )
        conn.commit()
        row = cursor.execute(
            "SELECT * FROM ingredient_interactions WHERE ingredient_a = ? AND ingredient_b = ? AND axis = ?",
            (a_c, b_c, axis),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_interactions(self) -> List[Dict[str, Any]]:
        self.ensure_interaction_tables()
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        rows = [dict(r) for r in cursor.execute("SELECT * FROM ingredient_interactions").fetchall()]
        conn.close()
        return rows

    # ------------------------------------------------------------------
    # Фаза 4 — Taxonomy / Class layer
    # ------------------------------------------------------------------
    def ensure_taxonomy_tables(self) -> None:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS taxonomy_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                label TEXT DEFAULT '',
                kind TEXT DEFAULT 'class',
                parent_id INTEGER,
                taxonomy_version TEXT DEFAULT 'v1',
                metadata TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS ingredient_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_name TEXT NOT NULL,
                class_id INTEGER NOT NULL,
                taxonomy_version TEXT DEFAULT 'v1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ingredient_name, class_id),
                FOREIGN KEY (class_id) REFERENCES taxonomy_classes(id)
            )
            '''
        )
        conn.commit()
        conn.close()

    def seed_taxonomy(self) -> int:
        """Вставляет seed-таксономию (идемпотентно). Возвращает число классов."""
        from .ingredient_normalizer import normalize_ingredient_name

        self.ensure_taxonomy_tables()
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        created = 0

        def _upsert_class(name: str, label: str, kind: str, parent_id=None):
            nonlocal created
            cursor.execute(
                "INSERT OR IGNORE INTO taxonomy_classes (name, label, kind, parent_id) VALUES (?, ?, ?, ?)",
                (name, label, kind, parent_id),
            )
            if cursor.rowcount:
                created += 1
            row = cursor.execute("SELECT id FROM taxonomy_classes WHERE name = ?", (name,)).fetchone()
            return row["id"] if row else 0

        for cls_name, cfg in _TAXONOMY_SEED.items():
            cls_id = _upsert_class(cls_name, cfg.get("label", cls_name), "class")
            for ing in cfg.get("ingredients", []):
                cursor.execute(
                    "INSERT OR IGNORE INTO ingredient_classes (ingredient_name, class_id) VALUES (?, ?)",
                    (normalize_ingredient_name(ing), cls_id),
                )
            for sub_name, sub_cfg in (cfg.get("subclasses") or {}).items():
                sub_id = _upsert_class(sub_name, sub_cfg.get("label", sub_name), "subclass", cls_id)
                for ing in sub_cfg.get("ingredients", []):
                    cursor.execute(
                        "INSERT OR IGNORE INTO ingredient_classes (ingredient_name, class_id) VALUES (?, ?)",
                        (normalize_ingredient_name(ing), sub_id),
                    )
        conn.commit()
        conn.close()
        return created

    def get_all_classes(self) -> List[Dict[str, Any]]:
        self.ensure_taxonomy_tables()
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        rows = [dict(r) for r in cursor.execute("SELECT * FROM taxonomy_classes ORDER BY id").fetchall()]
        conn.close()
        return rows

    def get_ingredient_classes(self, ingredient_name: str) -> List[str]:
        """Классы ингредиента (листья + все предки). Пусто, если ингредиент неизвестен."""
        from .ingredient_normalizer import normalize_ingredient_name

        self.ensure_taxonomy_tables()
        key = normalize_ingredient_name(ingredient_name)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        classes = cursor.execute(
            '''
            SELECT c.id, c.name, c.parent_id FROM ingredient_classes ic
            JOIN taxonomy_classes c ON c.id = ic.class_id
            WHERE ic.ingredient_name = ?
            ''',
            (key,),
        ).fetchall()
        conn.close()

        # разрешаем цепочку предков
        all_nodes = {r["id"]: r for r in self.get_all_classes()}
        result: List[str] = []
        seen = set()
        for r in classes:
            cur = r
            while cur is not None:
                name = cur["name"]
                if name not in seen:
                    seen.add(name)
                    result.append(name)
                cur = all_nodes.get(cur["parent_id"]) if cur["parent_id"] else None
        return result

    def get_class_routes(self) -> List[Any]:
        return list(_CLASS_ROUTES)

    def get_ingredient_class_map(self) -> Dict[str, List[str]]:
        """{normalized_ingredient_name: [класс + предки]} для всех ингредиентов (1 запрос)."""
        self.ensure_taxonomy_tables()
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        nodes = {r["id"]: r for r in cursor.execute("SELECT id, name, parent_id FROM taxonomy_classes").fetchall()}
        rows = cursor.execute("SELECT ingredient_name, class_id FROM ingredient_classes").fetchall()
        conn.close()

        m: Dict[str, List[str]] = {}
        for row in rows:
            ing = row["ingredient_name"]
            names: List[str] = []
            seen = set()
            cur = nodes.get(row["class_id"])
            while cur is not None:
                name = cur["name"]
                if name not in seen:
                    seen.add(name)
                    names.append(name)
                cur = nodes.get(cur["parent_id"]) if cur["parent_id"] else None
            m.setdefault(ing, [])
            for n in names:
                if n not in m[ing]:
                    m[ing].append(n)
        return m

    def initialize_knowledge_graph(self) -> Dict[str, int]:
        """Startup/migration: создаёт таблицы + seed (идемпотентно).

        Вызывается ОДИН раз при старте, чтобы первый /recommend не нёс seed-нагрузку.
        """
        self.ensure_ingredient_tables()
        self.ensure_interaction_tables()
        interactions = self.seed_interactions()
        self.ensure_taxonomy_tables()
        classes = self.seed_taxonomy()
        return {"seed_interactions": interactions, "seed_classes": classes}

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
