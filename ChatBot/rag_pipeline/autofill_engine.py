"""
Enterprise AI Form Autofill Engine
====================================
Independent module for detecting, extracting, and autofilling
structured fields in complex multi-page forms (KYC, compliance,
telecom, FCC, tax, service agreements, etc.).

HARD RULES:
  - NEVER guess data
  - If confidence < 1.00 → return value: null  (100% ONLY)
  - Wrong autofill is worse than empty autofill
  - ONLY use data that exists verbatim in uploaded documents

Separation of concerns: This module does NOT touch the chatbot chain.
"""

import os
import re
import json
import asyncio
import hashlib
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
from rag_pipeline.embeddings import EmbeddingModel
from rag_pipeline.llm_client import get_sync_client, get_async_client, get_model

load_dotenv()

# ================================================================
#  MODEL CONFIGURATION
#  Resolved dynamically via get_model() for provider portability.
# ================================================================
DETECT_MODEL = get_model("detect")   # Better at structured parsing
EXTRACT_MODEL = get_model("extract")  # Better at precise extraction


# ================================================================
#  FIELD ALIAS DICTIONARY
#  Maps canonical field names → common aliases found in forms.
#  Dramatically improves retrieval accuracy.
# ================================================================

FIELD_ALIASES: Dict[str, List[str]] = {
    "company_name": [
        "business name", "legal name", "registered business",
        "entity name", "company name", "registered entity",
        "legal entity name", "organization name", "firm name",
        "dba", "doing business as", "trade name",
        "customer name", "client name", "carrier name",
        "company", "name of company", "name of business",
        "name of entity", "legal business name", "full legal name",
    ],
    "entity_type": [
        "entity type", "business type", "organization type",
        "legal entity type", "company type", "business structure",
        "corporate structure", "type of entity",
        "form of organization", "type of business",
        "legal structure", "business entity type",
        "form of entity", "organizational type",
    ],
    "ein": [
        "ein", "federal tax id", "tax identification number",
        "tax id", "fein", "employer identification number",
        "federal ein", "tin", "taxpayer identification",
        "tax id number", "federal tax identification",
        "irs ein", "irs number", "federal id number",
        "employer id", "federal employer identification number",
    ],
    "fcc_499_id": [
        "fcc 499 id", "fcc 499", "499 filer id",
        "fcc filer id", "fcc registration", "fcc id",
        "499-a", "usf filer id", "499 id",
        "fcc 499-a filer id", "fcc filing id",
        "universal service fund id", "usf id",
    ],
    "frn": [
        "frn", "fcc registration number", "frn number",
        "fcc frn", "fcc registration no",
        "registration number fcc",
    ],
    "address": [
        "address", "business address", "street address",
        "mailing address", "physical address", "office address",
        "principal address", "headquarters address",
        "registered address", "corporate address",
        "company address", "primary address",
        "main address", "principal office address",
        "street", "address line", "address line 1",
    ],
    "city": [
        "city", "city name", "municipality",
    ],
    "state": [
        "state", "state/province", "province",
    ],
    "zip_code": [
        "zip", "zip code", "postal code", "zipcode",
        "zip/postal code",
    ],
    "billing_address": [
        "billing address", "invoice address", "payment address",
        "accounts payable address", "remittance address",
        "billing street address",
    ],
    "phone": [
        "phone", "phone number", "telephone", "contact number",
        "business phone", "office phone", "main phone",
        "primary phone", "tel", "telephone number",
        "company phone", "contact phone", "phone no",
        "direct phone", "main telephone",
    ],
    "fax": [
        "fax", "fax number", "facsimile", "fax no",
        "facsimile number", "fax phone",
    ],
    "email": [
        "email", "email address", "e-mail", "business email",
        "contact email", "corporate email", "company email",
        "primary email", "e-mail address", "email id",
        "electronic mail", "work email",
    ],
    "website": [
        "website", "web address", "url", "web site",
        "company website", "business website",
        "company url", "internet address", "web",
    ],
    "compliance_contact": [
        "compliance contact", "compliance officer",
        "regulatory contact", "compliance email",
        "legal compliance contact", "compliance department",
        "compliance representative", "regulatory officer",
    ],
    "authorized_representative": [
        "authorized representative", "authorized person",
        "authorized signatory", "legal representative",
        "contact person", "primary contact", "authorized agent",
        "authorized officer", "officer name", "signatory name",
        "representative name", "authorized individual",
        "printed name", "name of authorized",
    ],
    "year_incorporated": [
        "year incorporated", "date incorporated",
        "incorporation date", "date of incorporation",
        "year established", "established",
        "date formed", "formation date",
        "year of incorporation", "established date",
        "year formed", "year of formation",
    ],
    "state_of_incorporation": [
        "state of incorporation", "state incorporated",
        "jurisdiction", "state of formation",
        "state organized", "incorporated in",
        "state of organization", "jurisdiction of formation",
        "place of incorporation", "organized in",
    ],
    "traffic_volume": [
        "traffic volume", "monthly traffic", "call volume",
        "minutes of use", "mou", "monthly minutes",
        "estimated traffic", "traffic estimate",
        "estimated monthly volume", "traffic commitment",
    ],
    "ip_addresses": [
        "ip address", "ip addresses", "switch ip",
        "media gateway ip", "sip ip", "signaling ip",
        "originating ip", "terminating ip",
    ],
    "signature": [
        "signature", "authorized signature", "officer signature",
        "signatory", "signed by", "sign here",
    ],
    "date_signed": [
        "date signed", "signature date", "execution date",
        "date executed", "effective date",
        "date of execution", "signing date",
    ],
    "title": [
        "title", "position", "job title", "officer title",
        "designation", "role", "business title",
        "title of signer", "title/position",
    ],
    "trade_references": [
        "trade reference", "trade references", "business reference",
        "vendor reference", "commercial reference",
        "business references",
    ],
    "duns_number": [
        "duns", "duns number", "d-u-n-s", "d&b number",
        "dun and bradstreet", "d-u-n-s number",
        "d&b", "duns no",
    ],
    "state_puc_id": [
        "state puc", "puc id", "public utility commission",
        "state regulatory id", "puc certificate",
        "cpcn", "state commission id", "puc number",
        "state puc id", "certificate of public convenience",
    ],
    "ocn": [
        "ocn", "operating company number", "neca ocn",
        "company code", "ocn number",
    ],
    "country": [
        "country", "country name", "nation", "country of origin",
        "country of incorporation",
    ],
    "contact_name": [
        "contact name", "point of contact", "poc name",
        "contact person name", "primary contact name",
    ],
    "account_number": [
        "account number", "account no", "customer account",
        "acct number", "acct no", "client number",
    ],
    "billing_contact": [
        "billing contact", "billing contact name",
        "accounts payable contact", "billing representative",
    ],
    "technical_contact": [
        "technical contact", "tech contact", "noc contact",
        "technical representative", "noc email",
        "technical contact email",
    ],
}


# ================================================================
#  REGEX VALIDATORS
#  Used for context filtering AND confidence boosting.
# ================================================================

FIELD_VALIDATORS: Dict[str, re.Pattern] = {
    "ein":               re.compile(r"\b\d{2}[-]?\d{7}\b"),
    "phone":             re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "fax":               re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "email":             re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "fcc_499_id":        re.compile(r"\b\d{6,7}\b"),
    "frn":               re.compile(r"\b\d{10}\b"),
    "ip_addresses":      re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    "website":           re.compile(r"https?://[^\s]+|www\.[^\s]+"),
    "duns_number":       re.compile(r"\b\d{2}[-]?\d{3}[-]?\d{4}\b"),
    "year_incorporated": re.compile(r"\b(19|20)\d{2}\b"),
}


# ================================================================
#  STRUCTURED MEMORY  (Option B — JSON file)
# ================================================================

MEMORY_DIR = "data"
MEMORY_PATH = os.path.join(MEMORY_DIR, "structured_memory.json")


def _load_memory() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_memory(memory: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as fh:
        json.dump(memory, fh, indent=2, ensure_ascii=False)


def get_company_profile(company_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a cached company profile from structured memory."""
    return _load_memory().get(company_id)


def update_company_profile(company_id: str, fields: Dict[str, Any]) -> None:
    """Upsert field values into the company profile."""
    memory = _load_memory()
    if company_id not in memory:
        memory[company_id] = {}
    for key, value in fields.items():
        if value is not None:
            memory[company_id][key] = value
    _save_memory(memory)


# ================================================================
#  FIELD NORMALIZER
# ================================================================

def normalize_field_name(field_name: str) -> Optional[str]:
    """
    Map a detected field name to its canonical alias key.

    Uses a tiered matching strategy:
      Tier 1 — exact match on canonical key
      Tier 2 — exact match on an alias
      Tier 3 — alias is contained in field name (e.g. "business phone number" contains "business phone")
      Tier 4 — field name is contained in an alias (only if field name is ≥ 4 chars to avoid false positives)
      Tier 5 — meaningful word overlap ≥ 70 % (strict fuzzy)

    Returns the best match (earliest tier wins). Within the same tier,
    the first canonical key in FIELD_ALIASES insertion order wins.
    """
    lower = field_name.lower().strip()
    if not lower:
        return None

    # Tier 1: exact canonical
    if lower in FIELD_ALIASES:
        return lower

    # Tier 2: exact alias
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if lower == alias:
                return canonical

    # Tier 3: alias fully contained in the field name
    best_match: Optional[str] = None
    best_len = 0
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in lower and len(alias) > best_len:
                best_match = canonical
                best_len = len(alias)
    if best_match and best_len >= 3:
        return best_match

    # Tier 4: field name fully contained in an alias (min 4 chars)
    if len(lower) >= 4:
        for canonical, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                if lower in alias:
                    return canonical

    # Tier 5: meaningful word overlap (≥ 70 %)
    _NORM_STOP = {
        "a", "an", "the", "of", "for", "and", "or", "in", "to",
        "is", "are", "your", "our", "its", "no", "name",
    }
    field_words = set(re.findall(r"[a-z]{2,}", lower)) - _NORM_STOP
    if field_words:
        for canonical, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                alias_words = set(re.findall(r"[a-z]{2,}", alias)) - _NORM_STOP
                if not alias_words:
                    continue
                overlap = field_words & alias_words
                shorter = min(len(field_words), len(alias_words))
                if shorter > 0 and len(overlap) / shorter >= 0.70:
                    return canonical

    return None


def get_search_queries(field_name: str, canonical: Optional[str]) -> List[str]:
    """
    Expand a field name into multiple semantic search queries.

    Strategy:
      1. The original field name
      2. Top aliases from the canonical dictionary (up to 6)
      3. Contextual query variants (e.g. "What is the company's EIN?")
    """
    queries: List[str] = [field_name]

    if canonical and canonical in FIELD_ALIASES:
        queries.extend(FIELD_ALIASES[canonical][:6])

    # Add a natural-language question form for better semantic retrieval
    if canonical:
        readable = canonical.replace("_", " ")
        queries.append(f"company {readable}")
        queries.append(f"what is the {readable}")

    # Deduplicate preserving order
    seen: set = set()
    unique: List[str] = []
    for q in queries:
        key = q.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


# ================================================================
#  CONTEXT FILTER
# ================================================================

def filter_chunks_for_field(
    chunks: List[Dict[str, Any]],
    canonical: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Regex-based context filtering.
    Keeps only chunks containing patterns relevant to the field type.
    Falls back to full list if filtering yields nothing.
    """
    if not canonical or canonical not in FIELD_VALIDATORS:
        return chunks
    pattern = FIELD_VALIDATORS[canonical]
    filtered = [c for c in chunks if pattern.search(c.get("text", ""))]
    return filtered if filtered else chunks


# ================================================================
#  CONFIDENCE ENGINE
# ================================================================

def compute_confidence(
    value: Optional[str],
    chunks: List[Dict[str, Any]],
    canonical: Optional[str],
    llm_confidence: float,
    memory_value: Optional[str] = None,
) -> float:
    """
    Multi-signal confidence scoring — calibrated for accuracy.

    Boosts  : exact match in multiple chunks, regex validated,
              appears in official documents, CONFIRMED by structured memory.
    Penalties: value not found verbatim, regex mismatch,
              CONTRADICTS structured memory.
    """
    if not value or not value.strip():
        return 0.0

    conf = llm_confidence
    val_lower = value.lower().strip()

    # --- Signal 1: exact-match count (verbatim presence in chunks) ---
    exact_count = sum(
        1 for c in chunks if val_lower in c.get("text", "").lower()
    )
    if exact_count >= 3:
        conf = min(conf + 0.15, 1.0)
    elif exact_count >= 2:
        conf = min(conf + 0.10, 1.0)
    elif exact_count == 1:
        conf = min(conf + 0.05, 1.0)
    else:
        # Partial / token match — check if at least some words appear
        val_tokens = set(re.findall(r"[a-z0-9]+", val_lower))
        if len(val_tokens) >= 2:
            token_hits = 0
            for c in chunks:
                chunk_lower = c.get("text", "").lower()
                if sum(1 for t in val_tokens if t in chunk_lower) >= len(val_tokens) * 0.6:
                    token_hits += 1
            if token_hits >= 1:
                conf = max(conf - 0.05, 0.0)  # Mild penalty — tokens exist
            else:
                conf = max(conf - 0.15, 0.0)  # Moderate penalty
        else:
            conf = max(conf - 0.15, 0.0)

    # --- Signal 2: regex validation ---
    if canonical and canonical in FIELD_VALIDATORS:
        pat = FIELD_VALIDATORS[canonical]
        if pat.fullmatch(value.strip()):
            conf = min(conf + 0.12, 1.0)
        elif pat.search(value.strip()):
            conf = min(conf + 0.06, 1.0)
        else:
            # Only penalize for format-strict fields (numbers, IDs)
            format_strict = {
                "ein", "phone", "fax", "email", "fcc_499_id",
                "frn", "ip_addresses", "duns_number", "year_incorporated",
            }
            if canonical in format_strict:
                conf = max(conf - 0.12, 0.0)
            else:
                conf = max(conf - 0.05, 0.0)

    # --- Signal 3: multi-source appearance ---
    sources = {
        c.get("source", "unknown")
        for c in chunks
        if val_lower in c.get("text", "").lower()
    }
    if len(sources) >= 2:
        conf = min(conf + 0.10, 1.0)
    elif len(sources) == 1:
        conf = min(conf + 0.03, 1.0)

    # --- Signal 4: official-document boost ---
    official_kw = [
        "agreement", "contract", "kyc", "form",
        "tax", "fcc", "compliance", "addendum",
        "signed", "registration", "certificate",
    ]
    for src in sources:
        if any(kw in (src or "").lower() for kw in official_kw):
            conf = min(conf + 0.05, 1.0)
            break

    # --- Signal 5: STRUCTURED MEMORY cross-validation ---
    if memory_value is not None:
        mem_lower = memory_value.lower().strip()
        if val_lower == mem_lower:
            conf = min(conf + 0.15, 1.0)
        elif mem_lower in val_lower or val_lower in mem_lower:
            conf = min(conf + 0.08, 1.0)
        else:
            # Soft contradiction penalty — memory may be stale
            conf = max(conf - 0.08, 0.0)

    # --- Signal 6: value length plausibility ---
    # Very short values (1-2 chars) for non-boolean fields are suspicious
    if len(val_lower) <= 2 and canonical not in (
        "state", "country", "entity_type",
    ):
        conf = max(conf - 0.10, 0.0)

    return round(conf, 2)


# ================================================================
#  AUTOFILL ENGINE  (main class)
# ================================================================

class AutofillEngine:
    """
    Enterprise AI Form Autofill Engine.

    Completely independent from the chatbot chain.
    Reuses the same Weaviate collection and embedding model.
    """

    def __init__(self, weaviate_client):
        self.weaviate_client = weaviate_client
        self.collection_name = "KnowledgeBase"
        self.collection = weaviate_client.collections.get(self.collection_name)
        self.embedder = EmbeddingModel()
        self.groq_sync = get_sync_client()
        self.groq_async = get_async_client()

    # ---------------------------------------------------------
    #  STEP 1 — Detect All Fields From Form
    # ---------------------------------------------------------
    def detect_fields(self, form_text: str) -> List[Dict[str, str]]:
        """
        Use the LLM as a Document Structure Parser to extract
        ALL fillable fields from the uploaded form.

        Processes the form in page-sized chunks if it exceeds context
        limits, then merges and deduplicates.
        """
        MAX_CHUNK = 20000  # chars per LLM call

        if len(form_text) <= MAX_CHUNK:
            return self._detect_fields_single(form_text)

        # Multi-pass: split into overlapping chunks
        all_fields: List[Dict[str, str]] = []
        step = MAX_CHUNK - 2000  # 2 k overlap for context continuity
        for start in range(0, len(form_text), step):
            chunk = form_text[start:start + MAX_CHUNK]
            fields = self._detect_fields_single(chunk)
            all_fields.extend(fields)

        return self._deduplicate_fields(all_fields)

    def _detect_fields_single(self, text_chunk: str) -> List[Dict[str, str]]:
        """Detect fields from a single chunk of form text."""
        print(f"[AUTOFILL] Detecting fields... ({len(text_chunk)} chars, model={DETECT_MODEL})")
        prompt = (
            "You are a Document Structure Parser for enterprise compliance forms "
            "(KYC, telecom, FCC, tax, service agreements, addenda, etc.).\n\n"
            "TASK: Analyze this form text and extract ALL fillable/blank fields "
            "that a human would need to fill in.\n\n"
            "RULES:\n"
            "1. Extract EVERY field — business data, addresses, contacts, IDs, "
            "references, signatures, dates, checkboxes, options, table rows.\n"
            "2. Use the EXACT label text from the form for each field name.\n"
            "3. If a field label contains a colon, include text BEFORE the colon.\n"
            "4. For checkbox groups (e.g. ☐ Corp  ☐ LLC  ☐ Other), create ONE field "
            "for the group (e.g. name: 'Entity Type', type: 'string').\n"
            "5. Include blank lines, underscores, and empty table cells as fields.\n"
            "6. Do NOT include fields that already have permanent values "
            "(e.g. company letterhead, form titles, instructions).\n"
            "7. Return STRICT JSON only — NO markdown, NO extra text, NO explanation.\n"
            "8. Each field needs:\n"
            "   - \"name\": human-readable label (e.g. 'Company Name', 'Federal Tax ID (EIN)')\n"
            "   - \"type\": one of: string | number | email | phone | date | address | boolean\n\n"
            "EXAMPLES of expected output:\n"
            '{"fields": [\n'
            '  {"name": "Company Name", "type": "string"},\n'
            '  {"name": "Federal Tax ID (EIN)", "type": "number"},\n'
            '  {"name": "Business Address", "type": "address"},\n'
            '  {"name": "Phone Number", "type": "phone"},\n'
            '  {"name": "Email Address", "type": "email"},\n'
            '  {"name": "Entity Type", "type": "string"},\n'
            '  {"name": "Authorized Signature", "type": "string"},\n'
            '  {"name": "Date Signed", "type": "date"}\n'
            ']}\n\n'
            f"FORM TEXT:\n{text_chunk}\n\n"
            "Return ONLY the JSON (no markdown fences):"
        )

        import time as _time
        _t0 = _time.time()
        response = self.groq_sync.chat.completions.create(
            model=DETECT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.05,
            max_tokens=4096,
        )
        print(f"[AUTOFILL] Field detection complete ({_time.time() - _t0:.1f}s)")

        raw = response.choices[0].message.content.strip()

        try:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                parsed = json.loads(match.group())
                fields = parsed.get("fields", [])
                return [
                    f for f in fields
                    if isinstance(f, dict) and "name" in f
                ]
        except json.JSONDecodeError:
            pass

        return []

    @staticmethod
    def _deduplicate_fields(fields: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Remove duplicate fields detected across chunks.
        Keeps the first occurrence. Matches on lowered + stripped name.
        """
        seen: set = set()
        unique: List[Dict[str, str]] = []
        for f in fields:
            key = f.get("name", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    # ---------------------------------------------------------
    #  STEP 2 — Normalize Field Names
    # ---------------------------------------------------------
    @staticmethod
    def normalize_fields(
        fields: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Attach canonical names and expanded search queries."""
        enriched: List[Dict[str, Any]] = []
        for f in fields:
            name = f.get("name", "")
            ftype = f.get("type", "string")
            canonical = normalize_field_name(name)
            queries = get_search_queries(name, canonical)
            enriched.append({
                "name": name,
                "type": ftype,
                "canonical": canonical,
                "search_queries": queries,
            })
        return enriched

    # ---------------------------------------------------------
    #  STEP 3 — Smart Vector Retrieval
    # ---------------------------------------------------------
    def retrieve_for_field(
        self,
        queries: List[str],
        top_k: int = 8,
        company_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with query expansion.
        Retrieves top_k results per query, deduplicates by content hash.
        Returns up to ~top_k * len(queries) unique chunks.
        """
        all_chunks: List[Dict[str, Any]] = []
        seen: set = set()

        for query in queries:
            query_vector = self.embedder.embed_query(query)

            try:
                if company_id:
                    from weaviate.classes.query import Filter
                    results = self.collection.query.near_vector(
                        near_vector=query_vector,
                        limit=top_k,
                        filters=Filter.by_property("company_id").equal(company_id),
                    )
                else:
                    results = self.collection.query.near_vector(
                        near_vector=query_vector,
                        limit=top_k,
                    )
            except Exception:
                # Fallback without filter (e.g. property does not exist)
                results = self.collection.query.near_vector(
                    near_vector=query_vector,
                    limit=top_k,
                )

            for obj in results.objects:
                text = obj.properties.get("text", "")
                h = hashlib.md5(text[:300].encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    all_chunks.append({
                        "text": text,
                        "source": obj.properties.get("source"),
                        "page": obj.properties.get("page"),
                        "chunk_id": obj.properties.get("chunk_id"),
                    })

        return all_chunks

    # ---------------------------------------------------------
    #  STEPS 4 + 5 — Context Filter → Financial-Grade Extraction
    # ---------------------------------------------------------
    async def _extract_single_field(
        self,
        field_name: str,
        field_type: str,
        canonical: Optional[str],
        chunks: List[Dict[str, Any]],
        memory_value: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic extraction for one field.
        Temperature 0.0 — compliance-grade, fully deterministic.
        Accepts memory_value for cross-validation in confidence engine.
        """
        print(f"[AUTOFILL]   Extracting: {field_name} ({field_type})...")
        # Step 4: context filtering
        filtered = filter_chunks_for_field(chunks, canonical)

        if not filtered:
            return {
                "field": field_name,
                "value": None,
                "confidence": 0.0,
                "source_document": None,
                "canonical": canonical,
            }

        context_text = "\n\n---\n\n".join(
            f"[Source: {c.get('source', 'Unknown')}]\n{c['text']}"
            for c in filtered[:12]
        )

        # Build format hint based on canonical type
        format_hint = self._get_format_hint(canonical, field_type)

        # Memory reference (NOT ground truth)
        memory_hint = ""
        if memory_value:
            memory_hint = (
                f"\nREFERENCE (previously extracted — verify against context): "
                f"\"{memory_value}\"\n"
                "Use this ONLY if you can confirm it matches information in the context.\n"
            )

        prompt = (
            "You are a compliance-grade data extraction engine for enterprise forms.\n\n"
            "YOUR TASK: Extract the EXACT value for the specified field from the "
            "provided context documents.\n\n"
            "STRICT RULES:\n"
            "1. Use ONLY information that appears VERBATIM in the context below.\n"
            "2. Do NOT infer, guess, assume, or hallucinate ANY values.\n"
            "3. If the value is NOT clearly and explicitly present → return null.\n"
            "4. Copy the value EXACTLY as it appears in the context — verbatim only.\n"
            "5. Do NOT combine information from different places to create a new value.\n"
            "6. Do NOT add data that is not written word-for-word in the documents.\n"
            "7. For addresses: only include parts explicitly written in the context.\n"
            "8. For phone/fax: only extract if the complete number is in the context.\n"
            "9. For IDs (EIN, FCC 499 ID, FRN): extract the exact number only if present.\n"
            "10. Return ONLY valid JSON — no markdown fences, no explanation.\n"
            "11. Set confidence to 0.95 ONLY if value is found verbatim word-for-word, "
            "0.70 if partially present, 0.0 if not found.\n\n"
            f"FIELD TO EXTRACT:\n"
            f"  Name: {field_name}\n"
            f"  Expected type: {field_type}\n"
            f"{format_hint}"
            f"{memory_hint}\n"
            f"CONTEXT DOCUMENTS:\n{context_text}\n\n"
            "Return ONLY this JSON (no other text):\n"
            '{"value": "<extracted value or null>", '
            '"confidence": <float 0.0 to 1.0>, '
            '"source_document": "<source filename or null>"}'
        )

        try:
            response = await self.groq_async.chat.completions.create(
                model=EXTRACT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=512,
            )
            raw = response.choices[0].message.content.strip()

            match = re.search(r"\{[\s\S]*?\}", raw)
            if match:
                result = json.loads(match.group())
                value = result.get("value")
                # Treat the string "null" / "None" / "N/A" as actual None
                if value is None or (
                    isinstance(value, str) and
                    value.strip().lower() in ("null", "none", "n/a", "")
                ):
                    value = None

                # Clean up extracted value
                if value:
                    value = self._clean_extracted_value(value, canonical)

                llm_conf = float(result.get("confidence", 0.0))
                source = result.get("source_document")
                if isinstance(source, str) and source.strip().lower() in ("null", "none"):
                    source = None

                # Step 6: confidence engine (with memory cross-validation)
                final_conf = compute_confidence(
                    value, filtered, canonical, llm_conf,
                    memory_value=memory_value,
                )

                # HARD RULE: ONLY return values with 100% confidence
                if final_conf < 1.0:
                    return {
                        "field": field_name,
                        "value": None,
                        "confidence": round(final_conf, 2),
                        "source_document": None,
                        "canonical": canonical,
                    }

                return {
                    "field": field_name,
                    "value": value,
                    "confidence": round(final_conf, 2),
                    "source_document": source,
                    "canonical": canonical,
                }

        except Exception as exc:
            print(f"[AUTOFILL ERROR] Field '{field_name}': {str(exc)[:150]}")

        return {
            "field": field_name,
            "value": None,
            "confidence": 0.0,
            "source_document": None,
            "canonical": canonical,
        }

    @staticmethod
    def _get_format_hint(canonical: Optional[str], field_type: str) -> str:
        """Provide format guidance to the LLM based on field type."""
        hints: Dict[str, str] = {
            "ein": "  Format hint: EIN is a 9-digit number, often formatted as XX-XXXXXXX\n",
            "phone": "  Format hint: US phone like (XXX) XXX-XXXX or +1 XXX XXX XXXX\n",
            "fax": "  Format hint: Fax number, same format as phone\n",
            "email": "  Format hint: email@domain.com\n",
            "fcc_499_id": "  Format hint: 6-7 digit FCC filer ID number\n",
            "frn": "  Format hint: 10-digit FCC Registration Number\n",
            "website": "  Format hint: URL like http://www.example.com\n",
            "year_incorporated": "  Format hint: 4-digit year, e.g. 2015\n",
            "duns_number": "  Format hint: 9-digit D-U-N-S number, e.g. XX-XXX-XXXX\n",
            "ip_addresses": "  Format hint: IPv4 address like 192.168.1.1\n",
            "address": "  Format hint: Full address — street, city, state, ZIP code\n",
            "billing_address": "  Format hint: Full address — street, city, state, ZIP code\n",
        }
        if canonical and canonical in hints:
            return hints[canonical]
        if field_type == "address":
            return "  Format hint: Full address — street, city, state, ZIP code\n"
        if field_type == "phone":
            return "  Format hint: Complete phone number with area code\n"
        if field_type == "email":
            return "  Format hint: email@domain.com\n"
        return ""

    @staticmethod
    def _clean_extracted_value(value: str, canonical: Optional[str]) -> str:
        """
        Post-process extracted values to clean up common LLM artifacts.
        """
        # Strip surrounding quotes
        value = value.strip().strip('"').strip("'").strip()

        # Remove "Field: " prefix if LLM echoed the field name
        if ":" in value:
            parts = value.split(":", 1)
            # Only strip if the prefix looks like a label (short, no digits for ID fields)
            if len(parts[0]) < 30 and canonical not in ("address", "billing_address"):
                candidate = parts[1].strip()
                # Heuristic: if the part after ":" is a valid-looking value, use it
                # But don't strip for addresses or compound values
                if canonical in ("ein", "phone", "fax", "email", "fcc_499_id", "frn",
                                 "website", "duns_number"):
                    if candidate:
                        value = candidate

        # Remove trailing periods (LLM artifact)
        if value.endswith(".") and canonical not in ("website",):
            value = value.rstrip(".")

        return value.strip()

    # ---------------------------------------------------------
    #  STEP 7 — Combined Memory + Vector Retrieval
    # ---------------------------------------------------------
    async def _process_field(
        self,
        enriched_field: Dict[str, Any],
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        COMBINED STRATEGY — always queries BOTH sources:
          1. Structured Memory  (instant, cached)
          2. Weaviate Vector DB (semantic, deep)
        Then merges for the strongest possible answer.
        """
        name = enriched_field["name"]
        ftype = enriched_field["type"]
        canonical = enriched_field["canonical"]
        queries = enriched_field["search_queries"]

        # ---- Source 1: Structured Memory (instant) ----
        memory_value: Optional[str] = None
        if canonical and company_id:
            profile = get_company_profile(company_id)
            if profile and canonical in profile:
                memory_value = profile[canonical]

        # ---- Source 2: Weaviate Vector Retrieval (deep) ----
        chunks = await asyncio.to_thread(
            self.retrieve_for_field, queries, 8, company_id,
        )

        # ---- Merge Results ----
        return await self._merge_results(
            name, ftype, canonical, chunks, memory_value,
        )

    # ---------------------------------------------------------
    #  Merge: Cross-validate Memory + Vector DB
    # ---------------------------------------------------------
    async def _merge_results(
        self,
        field_name: str,
        field_type: str,
        canonical: Optional[str],
        chunks: List[Dict[str, Any]],
        memory_value: Optional[str],
    ) -> Dict[str, Any]:
        """
        Cross-validate structured memory against vector retrieval.

        CASES:
          A. Memory HIT + Vector HIT → both agree → max confidence
          B. Memory HIT + Vector HIT → disagree → prefer vector (fresher), flag conflict
          C. Memory HIT + Vector MISS → use memory with moderate confidence
          D. Memory MISS + Vector HIT → normal extraction
          E. Both MISS → return null
        """
        # Always run LLM extraction against vector chunks (unless no chunks)
        vector_result = await self._extract_single_field(
            field_name, field_type, canonical, chunks,
            memory_value=memory_value,
        )
        vector_val = vector_result.get("value")
        vector_conf = vector_result.get("confidence", 0.0)

        # --- CASE E: Both sources empty ---
        if not memory_value and not vector_val:
            return vector_result  # null result

        # --- CASE D: Memory MISS, Vector HIT ---
        if not memory_value and vector_val:
            return vector_result

        # --- CASE C: Memory HIT, Vector MISS ---
        if memory_value and not vector_val:
            # Memory has data but vector extraction couldn't confirm it.
            # STRICT RULE: Only use data that exists verbatim in documents.
            # Check if value appears VERBATIM in retrieved chunks.
            mem_lower = memory_value.lower().strip()
            chunk_hits = sum(
                1 for c in chunks if mem_lower in c.get("text", "").lower()
            )
            if chunk_hits == 0:
                # Value NOT found in any document chunk → reject
                return {
                    "field": field_name,
                    "value": None,
                    "confidence": 0.0,
                    "source_document": None,
                    "canonical": canonical,
                }
            # Value exists in document chunks — compute confidence
            mem_conf = 0.90 if chunk_hits == 1 else 0.95
            # Regex validation bonus
            if canonical and canonical in FIELD_VALIDATORS:
                if FIELD_VALIDATORS[canonical].search(memory_value.strip()):
                    mem_conf = min(mem_conf + 0.05, 1.0)
            # Multi-source bonus
            sources = {
                c.get("source", "unknown")
                for c in chunks
                if mem_lower in c.get("text", "").lower()
            }
            if len(sources) >= 2:
                mem_conf = min(mem_conf + 0.05, 1.0)
            # HARD RULE: Only 100% confidence fills the form
            if mem_conf < 1.0:
                return {
                    "field": field_name,
                    "value": None,
                    "confidence": round(mem_conf, 2),
                    "source_document": None,
                    "canonical": canonical,
                }
            return {
                "field": field_name,
                "value": memory_value,
                "confidence": round(mem_conf, 2),
                "source_document": "structured_memory (verified in docs)",
                "canonical": canonical,
            }

        # --- CASES A & B: Memory HIT + Vector HIT ---
        mem_lower = memory_value.lower().strip()
        vec_lower = (vector_val or "").lower().strip()

        if mem_lower == vec_lower:
            # CASE A: Perfect agreement → maximum confidence
            boosted_conf = min(max(vector_conf, 0.90) + 0.08, 1.0)
            return {
                "field": field_name,
                "value": vector_val,
                "confidence": round(boosted_conf, 2),
                "source_document": vector_result.get("source_document", "") + " + structured_memory",
                "canonical": canonical,
            }

        if mem_lower in vec_lower or vec_lower in mem_lower:
            # Partial overlap (substring match) → mild boost, prefer longer value
            preferred = vector_val if len(vec_lower) >= len(mem_lower) else memory_value
            boosted_conf = min(vector_conf + 0.05, 1.0)
            return {
                "field": field_name,
                "value": preferred,
                "confidence": round(boosted_conf, 2),
                "source_document": vector_result.get("source_document", "") + " + structured_memory",
                "canonical": canonical,
            }

        # CASE B: Conflict — sources disagree
        # STRICT: Only fill if one source has 100% confidence
        if vector_conf >= 1.0:
            return {
                "field": field_name,
                "value": vector_val,
                "confidence": round(vector_conf, 2),
                "source_document": vector_result.get("source_document", "") + " (overrides memory)",
                "canonical": canonical,
            }
        else:
            # Neither source at 100% → do NOT fill (conflict = uncertainty)
            return {
                "field": field_name,
                "value": None,
                "confidence": round(max(vector_conf, 0.0), 2),
                "source_document": None,
                "canonical": canonical,
            }

    # ==========================================================
    #  RE-EXTRACTION PASS — retry null fields with broader search
    # ==========================================================
    async def _retry_null_field(
        self,
        enriched_field: Dict[str, Any],
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Second-chance extraction for fields that returned null.
        Uses broader queries and higher top_k.
        """
        name = enriched_field["name"]
        ftype = enriched_field["type"]
        canonical = enriched_field["canonical"]

        # Build broader queries: use the field name + all aliases
        broad_queries: List[str] = [name]
        if canonical and canonical in FIELD_ALIASES:
            broad_queries.extend(FIELD_ALIASES[canonical])
        # Add generic document-level queries
        broad_queries.append(f"company information {name}")
        broad_queries.append(f"business details {name}")

        # Deduplicate
        seen: set = set()
        unique: List[str] = []
        for q in broad_queries:
            k = q.lower().strip()
            if k not in seen:
                seen.add(k)
                unique.append(q)

        # Memory
        memory_value: Optional[str] = None
        if canonical and company_id:
            profile = get_company_profile(company_id)
            if profile and canonical in profile:
                memory_value = profile[canonical]

        # Broader retrieval with higher top_k
        chunks = await asyncio.to_thread(
            self.retrieve_for_field, unique, 10, company_id,
        )

        return await self._merge_results(
            name, ftype, canonical, chunks, memory_value,
        )

    # ==========================================================
    #  PUBLIC API — autofill_form_async
    # ==========================================================
    async def autofill_form_async(
        self,
        form_text: str,
        document_name: str = "uploaded_form",
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full autofill pipeline with parallel execution + re-extraction.

        1. Detect fields   (LLM)
        2. Normalize        (alias dictionary)
        3-6. Retrieve + Extract + Validate  (parallel, all fields)
        7.   RE-EXTRACT null fields with broader queries (second pass)
        8.   Assemble + cache to memory
        """
        # Step 1
        print(f"[AUTOFILL] === Starting autofill for '{document_name}' ===")
        raw_fields = await asyncio.to_thread(self.detect_fields, form_text)

        if not raw_fields:
            print("[AUTOFILL] No fillable fields detected.")
            return {
                "document": document_name,
                "fields": [],
                "metadata": {"error": "No fillable fields detected in the form."},
            }

        # Step 2
        enriched = self.normalize_fields(raw_fields)
        print(f"[AUTOFILL] Detected {len(enriched)} fields. Starting extraction...")

        # Steps 3-6 (parallel — first pass)
        tasks = [self._process_field(ef, company_id) for ef in enriched]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        filled = sum(1 for r in results if not isinstance(r, BaseException) and r.get("value"))
        print(f"[AUTOFILL] First pass: {filled}/{len(enriched)} fields extracted")

        # Step 7 — Re-extraction pass for null fields (second chance)
        retry_indices: List[int] = []
        retry_tasks: List = []
        for i, (ef, result) in enumerate(zip(enriched, results)):
            if isinstance(result, BaseException) or not result.get("value"):
                retry_indices.append(i)
                retry_tasks.append(self._retry_null_field(ef, company_id))

        if retry_tasks:
            print(f"[AUTOFILL] Re-extracting {len(retry_tasks)} null fields (2nd pass)...")
            retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
            for idx, retry_result in zip(retry_indices, retry_results):
                if not isinstance(retry_result, BaseException) and retry_result.get("value"):
                    results[idx] = retry_result

        # Step 8 — Assemble
        final_fields: List[Dict[str, Any]] = []
        memory_updates: Dict[str, str] = {}
        memory_hits = 0
        vector_hits = 0
        combined_hits = 0

        for ef, result in zip(enriched, results):
            if isinstance(result, BaseException):
                final_fields.append({
                    "field": ef["name"],
                    "value": None,
                    "confidence": 0.0,
                    "source_document": None,
                    "canonical": ef.get("canonical"),
                })
                continue

            final_fields.append(result)

            # Track source type for stats
            src_doc = result.get("source_document") or ""
            if "structured_memory" in src_doc and "+" in src_doc:
                combined_hits += 1
            elif "structured_memory" in src_doc:
                memory_hits += 1
            elif result.get("value"):
                vector_hits += 1

            # Collect values for memory caching — ONLY 100% confidence
            # (never pollute memory with uncertain data)
            if (
                result.get("value")
                and result.get("confidence", 0) >= 1.0
                and ef.get("canonical")
            ):
                memory_updates[ef["canonical"]] = result["value"]

        # Persist to structured memory (keeps it fresh for next autofill)
        if company_id and memory_updates:
            await asyncio.to_thread(
                update_company_profile, company_id, memory_updates,
            )

        filled = sum(1 for f in final_fields if f.get("value"))
        return {
            "document": document_name,
            "fields": final_fields,
            "metadata": {
                "total_fields": len(final_fields),
                "filled_fields": filled,
                "fill_rate": f"{(filled / len(final_fields) * 100):.1f}%"
                if final_fields else "0%",
                "company_id": company_id,
                "source_breakdown": {
                    "memory_only": memory_hits,
                    "vector_only": vector_hits,
                    "combined_verified": combined_hits,
                },
            },
        }

    # ==========================================================
    #  PUBLIC API — build_company_profile_async
    # ==========================================================
    async def build_company_profile_async(
        self,
        company_id: str,
    ) -> Dict[str, Any]:
        """
        Entity Builder — automatically creates a Master Company Profile
        from all documents already stored in the knowledge base.
        """
        core_fields = [
            {"name": "Registered Business Name", "type": "string"},
            {"name": "Entity Type", "type": "string"},
            {"name": "Federal Tax ID (EIN)", "type": "number"},
            {"name": "FCC 499 ID", "type": "string"},
            {"name": "FRN Number", "type": "string"},
            {"name": "Business Address", "type": "address"},
            {"name": "Billing Address", "type": "address"},
            {"name": "Phone Number", "type": "phone"},
            {"name": "Fax Number", "type": "phone"},
            {"name": "Email Address", "type": "email"},
            {"name": "Website", "type": "string"},
            {"name": "State of Incorporation", "type": "string"},
            {"name": "Year Incorporated", "type": "number"},
            {"name": "Authorized Representative", "type": "string"},
            {"name": "Title / Position", "type": "string"},
            {"name": "Compliance Contact Email", "type": "email"},
            {"name": "Operating Company Number (OCN)", "type": "string"},
            {"name": "DUNS Number", "type": "string"},
            {"name": "Trade References", "type": "string"},
            {"name": "State PUC ID / CPCN", "type": "string"},
            {"name": "Technical Contact", "type": "string"},
            {"name": "Billing Contact", "type": "string"},
            {"name": "Country", "type": "string"},
        ]

        enriched = self.normalize_fields(core_fields)
        tasks = [self._process_field(ef, company_id) for ef in enriched]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        profile: Dict[str, Any] = {}
        memory_updates: Dict[str, str] = {}

        for ef, result in zip(enriched, results):
            if isinstance(result, BaseException):
                continue
            if result.get("value") and result.get("confidence", 0) >= 1.0:
                profile[result["field"]] = {
                    "value": result["value"],
                    "confidence": result["confidence"],
                    "source": result.get("source_document"),
                }
                if ef.get("canonical"):
                    memory_updates[ef["canonical"]] = result["value"]

        # Persist
        if memory_updates:
            await asyncio.to_thread(
                update_company_profile, company_id, memory_updates,
            )

        return {
            "company_id": company_id,
            "profile": profile,
            "fields_extracted": len(profile),
        }

