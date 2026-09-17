import sqlite3
from typing import Dict, List, Optional

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
