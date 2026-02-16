"""
Entity Graph Engine — Neo4j-Backed Company Knowledge Graph
============================================================
Shifts architecture from document-centric → entity-centric.

Companies are NODES. Documents are EVIDENCE.
Relationships encode carrier partnerships, regulatory filings,
corporate hierarchies, and vendor connections.

Design:
  - Neo4j for graph storage and traversal
  - Fallback: in-memory graph for development
  - Every node carries full provenance chain
  - Supports multi-hop queries: "Who are Dorial's upstream carriers?"
"""

import os
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from core.schemas.company import CompanyProfile, CompanyNode, CompanyRelationship
from core.schemas.enums import AuditAction
from config.settings import settings


class EntityGraphEngine:
    """
    Neo4j-backed entity graph for telecom company intelligence.
    Falls back to JSON-based graph if Neo4j is unavailable.
    """

    def __init__(self):
        self._driver = None
        self._use_neo4j = settings.ENABLE_GRAPH
        self._fallback_store: Dict[str, CompanyProfile] = {}
        self._fallback_relationships: List[CompanyRelationship] = []
        self._store_path = os.path.join(settings.MEMORY_STORE_PATH, "entity_graph.json")

        if self._use_neo4j:
            self._init_neo4j()
        else:
            self._load_fallback_store()

    def _init_neo4j(self):
        """Initialize Neo4j driver."""
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            self._ensure_constraints()
            print("[GRAPH] Neo4j connected successfully.")

        except ImportError:
            print("[GRAPH] neo4j driver not installed. pip install neo4j")
            print("[GRAPH] Falling back to JSON-based graph store.")
            self._use_neo4j = False
            self._load_fallback_store()

        except Exception as e:
            print(f"[GRAPH] Neo4j connection failed: {e}")
            print("[GRAPH] Falling back to JSON-based graph store.")
            self._use_neo4j = False
            self._load_fallback_store()

    def _ensure_constraints(self):
        """Create Neo4j uniqueness constraints and indexes."""
        if not self._driver:
            return

        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.company_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.document_id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.ein)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.fcc_499_id)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.company_name)",
        ]

        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception:
                    pass  # Constraint may already exist

    # ── Company CRUD ─────────────────────────────────────────

    def upsert_company(self, profile: CompanyProfile) -> CompanyProfile:
        """
        Create or update a company node in the graph.
        Merges new data with existing profile.
        """
        if self._use_neo4j:
            return self._upsert_company_neo4j(profile)
        return self._upsert_company_fallback(profile)

    def get_company(self, company_id: str) -> Optional[CompanyProfile]:
        """Retrieve a company profile by ID."""
        if self._use_neo4j:
            return self._get_company_neo4j(company_id)
        return self._fallback_store.get(company_id)

    def search_companies(
        self,
        query: str,
        limit: int = 10,
    ) -> List[CompanyProfile]:
        """Search companies by name, EIN, or FCC ID."""
        if self._use_neo4j:
            return self._search_companies_neo4j(query, limit)
        return self._search_companies_fallback(query, limit)

    def list_companies(self, limit: int = 50) -> List[str]:
        """List all company IDs."""
        if self._use_neo4j:
            return self._list_companies_neo4j(limit)
        return list(self._fallback_store.keys())[:limit]

    # ── Relationship Management ──────────────────────────────

    def add_relationship(self, relationship: CompanyRelationship) -> None:
        """Add an edge between two company nodes."""
        if self._use_neo4j:
            self._add_relationship_neo4j(relationship)
        else:
            self._fallback_relationships.append(relationship)
            self._save_fallback_store()

    def get_relationships(
        self,
        company_id: str,
        relationship_type: Optional[str] = None,
    ) -> List[CompanyRelationship]:
        """Get all relationships for a company."""
        if self._use_neo4j:
            return self._get_relationships_neo4j(company_id, relationship_type)

        results = [
            r for r in self._fallback_relationships
            if r.source_company_id == company_id or r.target_company_id == company_id
        ]
        if relationship_type:
            results = [r for r in results if r.relationship_type == relationship_type]
        return results

    # ── Document Linking ─────────────────────────────────────

    def link_document(
        self,
        company_id: str,
        document_id: str,
        document_type: str,
        filename: str,
    ) -> None:
        """Link a document node to a company node."""
        if self._use_neo4j:
            self._link_document_neo4j(company_id, document_id, document_type, filename)
        else:
            profile = self._fallback_store.get(company_id)
            if profile and document_id not in profile.linked_documents:
                profile.linked_documents.append(document_id)
                self._save_fallback_store()

    def get_company_documents(self, company_id: str) -> List[Dict[str, Any]]:
        """Get all documents linked to a company."""
        if self._use_neo4j:
            return self._get_company_documents_neo4j(company_id)

        profile = self._fallback_store.get(company_id)
        if profile:
            return [{"document_id": d} for d in profile.linked_documents]
        return []

    # ── Deduplication ────────────────────────────────────────

    def find_duplicates(
        self,
        ein: Optional[str] = None,
        company_name: Optional[str] = None,
        fcc_id: Optional[str] = None,
    ) -> List[CompanyProfile]:
        """
        Find potential duplicate companies by EIN, name, or FCC ID.
        Used during entity resolution to prevent duplicate profiles.
        """
        candidates: List[CompanyProfile] = []

        if self._use_neo4j:
            return self._find_duplicates_neo4j(ein, company_name, fcc_id)

        for profile in self._fallback_store.values():
            if ein and profile.get_field_value("ein") == ein:
                candidates.append(profile)
            elif company_name:
                existing_name = profile.get_field_value("company_name") or ""
                if existing_name.lower().strip() == company_name.lower().strip():
                    candidates.append(profile)
            elif fcc_id and profile.get_field_value("fcc_499_id") == fcc_id:
                candidates.append(profile)

        return candidates

    def merge_profiles(
        self,
        source_id: str,
        target_id: str,
    ) -> Optional[CompanyProfile]:
        """
        Merge source company into target company.
        Source's fields update target (higher confidence wins).
        Source node is archived, not deleted.
        """
        source = self.get_company(source_id)
        target = self.get_company(target_id)

        if not source or not target:
            return None

        # Merge fields: target keeps higher-confidence values
        for field_name, field in source.fields.items():
            if field.current_value:
                existing = target.fields.get(field_name)
                if not existing or not existing.current_value:
                    # Target doesn't have this field — take source's
                    target.fields[field_name] = field
                elif field.current_confidence > existing.current_confidence:
                    # Source has higher confidence — update target
                    target.upsert_field(
                        canonical_name=field_name,
                        value=field.current_value,
                        confidence=field.current_confidence,
                        source_document=field.current_source or "merged",
                        extraction_method="entity_merge",
                        change_reason=f"merged_from_{source_id}",
                    )

        # Merge linked documents
        for doc_id in source.linked_documents:
            if doc_id not in target.linked_documents:
                target.linked_documents.append(doc_id)

        # Save merged target
        self.upsert_company(target)

        return target

    # ── Neo4j Implementation ─────────────────────────────────

    def _upsert_company_neo4j(self, profile: CompanyProfile) -> CompanyProfile:
        """Upsert company node in Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            flat = profile.to_flat_dict()
            flat["company_id"] = profile.company_id
            flat["updated_at"] = datetime.utcnow().isoformat()
            flat["is_verified"] = profile.is_verified

            session.run(
                """
                MERGE (c:Company {company_id: $company_id})
                SET c += $properties
                """,
                company_id=profile.company_id,
                properties=flat,
            )

            # Store full profile JSON for versioned data
            profile_json = profile.model_dump_json()
            session.run(
                """
                MERGE (c:Company {company_id: $company_id})
                SET c.profile_json = $profile_json
                """,
                company_id=profile.company_id,
                profile_json=profile_json,
            )

        return profile

    def _get_company_neo4j(self, company_id: str) -> Optional[CompanyProfile]:
        """Retrieve company from Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (c:Company {company_id: $company_id}) RETURN c.profile_json AS pj",
                company_id=company_id,
            )
            record = result.single()
            if record and record["pj"]:
                return CompanyProfile.model_validate_json(record["pj"])
        return None

    def _search_companies_neo4j(self, query: str, limit: int) -> List[CompanyProfile]:
        """Full-text search companies in Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(
                """
                MATCH (c:Company)
                WHERE c.company_name CONTAINS $query
                   OR c.ein CONTAINS $query
                   OR c.fcc_499_id CONTAINS $query
                   OR c.company_id CONTAINS $query
                RETURN c.profile_json AS pj
                LIMIT $limit
                """,
                query=query,
                limit=limit,
            )
            profiles = []
            for record in result:
                if record["pj"]:
                    profiles.append(CompanyProfile.model_validate_json(record["pj"]))
            return profiles

    def _list_companies_neo4j(self, limit: int) -> List[str]:
        """List company IDs from Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (c:Company) RETURN c.company_id AS cid LIMIT $limit",
                limit=limit,
            )
            return [record["cid"] for record in result]

    def _add_relationship_neo4j(self, rel: CompanyRelationship) -> None:
        """Add relationship edge in Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            session.run(
                f"""
                MATCH (a:Company {{company_id: $source}})
                MATCH (b:Company {{company_id: $target}})
                MERGE (a)-[r:{rel.relationship_type.upper()}]->(b)
                SET r.source_document = $source_doc,
                    r.confidence = $confidence,
                    r.created_at = $created_at
                """,
                source=rel.source_company_id,
                target=rel.target_company_id,
                source_doc=rel.source_document,
                confidence=rel.confidence,
                created_at=rel.created_at.isoformat(),
            )

    def _get_relationships_neo4j(
        self,
        company_id: str,
        relationship_type: Optional[str],
    ) -> List[CompanyRelationship]:
        """Get relationships from Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            if relationship_type:
                query = f"""
                    MATCH (a:Company {{company_id: $cid}})-[r:{relationship_type.upper()}]-(b:Company)
                    RETURN a.company_id AS src, b.company_id AS tgt,
                           type(r) AS rtype, r.confidence AS conf
                """
            else:
                query = """
                    MATCH (a:Company {company_id: $cid})-[r]-(b:Company)
                    RETURN a.company_id AS src, b.company_id AS tgt,
                           type(r) AS rtype, r.confidence AS conf
                """

            result = session.run(query, cid=company_id)
            relationships = []
            for record in result:
                relationships.append(CompanyRelationship(
                    source_company_id=record["src"],
                    target_company_id=record["tgt"],
                    relationship_type=record["rtype"].lower(),
                    confidence=record["conf"] or 0.0,
                ))
            return relationships

    def _link_document_neo4j(
        self,
        company_id: str,
        document_id: str,
        document_type: str,
        filename: str,
    ) -> None:
        """Link document node to company in Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            session.run(
                """
                MERGE (d:Document {document_id: $doc_id})
                SET d.filename = $filename,
                    d.document_type = $doc_type,
                    d.linked_at = $now
                WITH d
                MATCH (c:Company {company_id: $company_id})
                MERGE (c)-[:HAS_DOCUMENT]->(d)
                """,
                doc_id=document_id,
                filename=filename,
                doc_type=document_type,
                now=datetime.utcnow().isoformat(),
                company_id=company_id,
            )

    def _get_company_documents_neo4j(self, company_id: str) -> List[Dict[str, Any]]:
        """Get documents linked to company from Neo4j."""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(
                """
                MATCH (c:Company {company_id: $cid})-[:HAS_DOCUMENT]->(d:Document)
                RETURN d.document_id AS doc_id, d.filename AS fname,
                       d.document_type AS dtype
                """,
                cid=company_id,
            )
            return [
                {
                    "document_id": r["doc_id"],
                    "filename": r["fname"],
                    "document_type": r["dtype"],
                }
                for r in result
            ]

    def _find_duplicates_neo4j(
        self,
        ein: Optional[str],
        company_name: Optional[str],
        fcc_id: Optional[str],
    ) -> List[CompanyProfile]:
        """Find duplicate companies in Neo4j."""
        conditions = []
        params: Dict[str, Any] = {}

        if ein:
            conditions.append("c.ein = $ein")
            params["ein"] = ein
        if company_name:
            conditions.append("toLower(c.company_name) = toLower($name)")
            params["name"] = company_name
        if fcc_id:
            conditions.append("c.fcc_499_id = $fcc_id")
            params["fcc_id"] = fcc_id

        if not conditions:
            return []

        where_clause = " OR ".join(conditions)

        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(
                f"MATCH (c:Company) WHERE {where_clause} RETURN c.profile_json AS pj",
                **params,
            )
            profiles = []
            for record in result:
                if record["pj"]:
                    profiles.append(CompanyProfile.model_validate_json(record["pj"]))
            return profiles

    # ── Fallback JSON Store ──────────────────────────────────

    def _upsert_company_fallback(self, profile: CompanyProfile) -> CompanyProfile:
        """Store company profile in JSON fallback."""
        self._fallback_store[profile.company_id] = profile
        self._save_fallback_store()
        return profile

    def _search_companies_fallback(self, query: str, limit: int) -> List[CompanyProfile]:
        """Search companies in fallback store."""
        query_lower = query.lower()
        results = []
        for profile in self._fallback_store.values():
            if (
                query_lower in profile.company_id.lower()
                or query_lower in (profile.get_field_value("company_name") or "").lower()
                or query_lower in (profile.get_field_value("ein") or "").lower()
                or query_lower in (profile.get_field_value("fcc_499_id") or "").lower()
            ):
                results.append(profile)
            if len(results) >= limit:
                break
        return results

    def _load_fallback_store(self):
        """Load fallback JSON store from disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for cid, profile_data in data.get("companies", {}).items():
                    self._fallback_store[cid] = CompanyProfile.model_validate(profile_data)
                for rel_data in data.get("relationships", []):
                    self._fallback_relationships.append(
                        CompanyRelationship.model_validate(rel_data)
                    )
            except Exception as e:
                print(f"[GRAPH] Failed to load fallback store: {e}")

    def _save_fallback_store(self):
        """Persist fallback store to JSON."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        data = {
            "companies": {
                cid: profile.model_dump(mode="json")
                for cid, profile in self._fallback_store.items()
            },
            "relationships": [
                r.model_dump(mode="json") for r in self._fallback_relationships
            ],
        }
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def close(self):
        """Close graph connections."""
        if self._driver:
            self._driver.close()


# Module-level singleton
_graph_engine: Optional[EntityGraphEngine] = None


def get_graph_engine() -> EntityGraphEngine:
    global _graph_engine
    if _graph_engine is None:
        _graph_engine = EntityGraphEngine()
    return _graph_engine






