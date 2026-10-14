# Synbot Backend
## Hybrid Semantic, Vector & Structured Retrieval Architecture

**Document Type:** Backend Engineering Specification  
**Status:** Proposed  
**Priority:** High  
**Target:** Synbot / Synbot Health Backend  
**Primary Database:** PostgreSQL  
**Vector Engine:** PostgreSQL `pgvector`  
**Search Strategy:** Hybrid Metadata + Full-Text + Vector Retrieval  
**LLM Layer:** Existing Synbot LLM/agent architecture  
**Implementation Principle:** Retrieve narrowly first; reason second.

---

# 1. Objective

The current Synbot backend should be upgraded from broad database querying toward an intelligent retrieval architecture.

The objective is **not** to replace PostgreSQL's relational querying.

The objective is to prevent every natural-language request from becoming a broad database search.

Synbot should first determine:

1. What the user is asking about.
2. Which business/clinical domain is relevant.
3. Which entity or patient is relevant.
4. Which time range is relevant.
5. Which tables/records are relevant.
6. Whether the request requires:
   - exact SQL retrieval,
   - semantic retrieval,
   - full-text retrieval,
   - or a combination.

The final architecture should support:

```text
Natural Language Query
        │
        ▼
Query Understanding
        │
        ├── Domain
        ├── Entity
        ├── Patient / Customer
        ├── Date Range
        ├── Intent
        └── Retrieval Type
        │
        ▼
Retrieval Planner
        │
        ├── Metadata Filtering
        ├── PostgreSQL Full-Text Search
        ├── pgvector Semantic Search
        └── Exact SQL Query
        │
        ▼
Candidate Results
        │
        ▼
Hybrid Ranking / Reranking
        │
        ▼
Context Builder
        │
        ▼
LLM / Agent
        │
        ▼
Grounded Response
```

---

# 2. Why This Architecture Is Required

The current database is already relationally structured.

The Silver layer contains tables such as:

- `royan_patients`
- `royan_encounters`
- `royan_lab_orders`
- `royan_prescriptions`
- `royan_billing`
- `royan_appointments`

with foreign-key relationships connecting the clinical record graph.

The problem is therefore not primarily database organization.

The problem is **retrieval efficiency and semantic understanding**.

For example:

### Query A

> "How many patients visited the laboratory last month?"

This should use SQL.

There is no reason to perform vector search.

### Query B

> "Show me patients whose notes mention persistent abdominal pain."

This is a semantic retrieval problem.

### Query C

> "What did we prescribe this patient during his previous visits?"

This is primarily relational retrieval:

```text
patient
   ↓
encounters
   ↓
prescriptions
```

### Query D

> "What previous encounters are relevant to this patient's current complaint?"

This is a hybrid semantic + relational problem.

### Query E

> "Find the patient's previous notes relating to hypertension."

This requires:

```text
patient filter
        +
clinical semantic search
        +
date ordering
```

Therefore Synbot needs a **retrieval planner**, not a single search mechanism.

---

# 3. Core Design Principle

## Do not vectorise the entire database blindly.

The system should distinguish between:

### Structured data

Use PostgreSQL SQL/indexes.

Examples:

- Patient ID
- MRN
- Date of birth
- Gender
- Encounter status
- Department
- Billing amount
- Prescription quantity
- Appointment status
- Lab status

### Semi-structured/unstructured data

Use semantic and full-text retrieval.

Examples:

- Chief complaint
- Triage notes
- Diagnosis notes
- Discharge summaries
- Encounter notes
- Progress notes
- Lab findings
- Prescription instructions
- Clinical observations
- HMO notes
- Operational notes

The vector index should primarily represent **meaning-bearing text**, not every database column.

---

# 4. Recommended Technology

## PostgreSQL + pgvector

Do not introduce a separate vector database at this stage.

The existing architecture already uses PostgreSQL, and the database contains a large relational graph.

Adding a separate vector database would introduce:

- another service,
- synchronization problems,
- another backup requirement,
- another authentication boundary,
- duplicated metadata,
- additional deployment complexity.

Instead:

```text
PostgreSQL
├── Relational tables
├── B-tree indexes
├── GIN full-text indexes
├── pgvector embeddings
└── Retrieval metadata
```

This keeps structured and semantic retrieval close together.

---

# 5. Vector Extension

Enable:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The Backend Agent must verify whether the deployed PostgreSQL image supports `pgvector` before migration.

---

# 6. Retrieval Schema

Create a dedicated semantic retrieval layer.

Recommended tables:

```text
synbot_documents
synbot_document_chunks
synbot_embedding_models
synbot_search_logs
```

---

# 7. `synbot_documents`

This represents the logical source document or clinical record.

Example:

```sql
CREATE TABLE synbot_documents (
    id BIGSERIAL PRIMARY KEY,

    document_type TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_id BIGINT NOT NULL,

    patient_id BIGINT NULL,
    encounter_id BIGINT NULL,

    department TEXT NULL,

    title TEXT NULL,
    content TEXT NOT NULL,

    document_date TIMESTAMPTZ NULL,

    metadata JSONB DEFAULT '{}'::jsonb,

    content_hash TEXT NOT NULL,

    embedding_status TEXT DEFAULT 'pending',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_table, source_id, document_type)
);
```

Recommended `document_type` examples:

```text
encounter_note
triage_note
diagnosis_note
discharge_summary
lab_order
lab_result
prescription
nursing_note
progress_note
billing_note
patient_summary
```

---

# 8. `synbot_document_chunks`

Long clinical documents should not necessarily be embedded as one large vector.

Create chunks.

```sql
CREATE TABLE synbot_document_chunks (
    id BIGSERIAL PRIMARY KEY,

    document_id BIGINT NOT NULL
        REFERENCES synbot_documents(id)
        ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,

    content TEXT NOT NULL,

    token_count INTEGER,

    embedding VECTOR(<EMBEDDING_DIMENSION>),

    search_vector TSVECTOR,

    metadata JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(document_id, chunk_index)
);
```

The actual vector dimension must match the selected embedding model.

Do not hard-code an arbitrary dimension.

---

# 9. Metadata Is More Important Than the Vector

Every chunk must contain enough metadata to narrow the search before semantic similarity is calculated.

Minimum metadata:

```json
{
  "patient_id": 12345,
  "encounter_id": 98231,
  "department": "OPD",
  "document_type": "encounter_note",
  "source_table": "royan_encounter_notes",
  "source_id": 55221,
  "document_date": "2026-09-12T10:30:00",
  "external_source": "hope"
}
```

Potential additional metadata:

```json
{
  "doctor_id": 45,
  "doctor_name": "Dr. Smith",
  "encounter_type": "outpatient",
  "status": "completed",
  "hmo_id": 12,
  "facility_id": 1
}
```

This enables:

```text
Semantic search
+
patient filter
+
department filter
+
date filter
+
document-type filter
```

rather than:

```text
semantic search across everything
```

---

# 10. Full-Text Search

Vector search should not be the only search mechanism.

PostgreSQL's native full-text search should be used alongside vectors.

Populate:

```sql
search_vector TSVECTOR
```

from:

```text
title
content
selected metadata
```

Create a GIN index:

```sql
CREATE INDEX idx_synbot_chunks_search_vector
ON synbot_document_chunks
USING GIN(search_vector);
```

This is particularly useful for exact clinical terminology.

For example:

```text
"malaria"
"hypertension"
"Rotarix"
"Full Blood Count"
"amoxicillin"
"OPD"
```

A vector model may understand the concept, but exact terminology should remain searchable directly.

---

# 11. Vector Index

Use an HNSW index where supported by the deployed `pgvector` version.

Conceptually:

```sql
CREATE INDEX idx_synbot_chunks_embedding
ON synbot_document_chunks
USING hnsw (embedding vector_cosine_ops);
```

HNSW means **Hierarchical Navigable Small World**.

It provides approximate nearest-neighbour search without comparing the query against every vector individually.

This is the main mechanism that addresses the user's original concern.

---

# 12. Embedding Model

The embedding model must be configurable.

Do not hard-code the model into business logic.

Recommended abstraction:

```python
class EmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
```

Potential implementations:

```text
LocalEmbeddingProvider
OpenAIEmbeddingProvider
AzureEmbeddingProvider
HuggingFaceEmbeddingProvider
```

For a healthcare deployment where data may need to remain local, a local embedding model should be supported.

The selected model must be benchmarked against the actual clinical terminology before production adoption.

---

# 13. What Should Be Embedded

Initially embed:

### Patient-related semantic information

- allergies
- clinical notes
- problem lists
- relevant patient summaries

### Encounter information

- chief complaint
- triage notes
- diagnosis notes
- discharge summary
- progress notes
- SOAP notes

### Laboratory information

- test names
- findings
- interpretation
- result summaries

### Medication information

- drug name
- dosage
- frequency
- special instructions

### Operational information

- nursing notes
- care plans
- HMO notes
- administrative notes

Do NOT create embeddings for every numeric/transactional field.

For example:

```text
subtotal = 250000
status = paid
quantity = 15
appointment_status = completed
```

should remain primarily SQL-queryable.

---

# 14. Patient-Centric Retrieval

One of the most important features should be patient-scoped semantic search.

When the user asks:

> "What has happened with this patient before?"

Synbot should first resolve:

```text
Patient → patient_id
```

Then restrict semantic retrieval:

```sql
WHERE patient_id = :patient_id
```

before performing vector similarity.

This is dramatically more efficient than searching the entire clinical corpus.

---

# 15. Example Patient Query

User:

> "Has this patient had similar abdominal pain before?"

Query planner:

```json
{
  "intent": "clinical_history",
  "patient_id": 18291,
  "semantic_query": "previous episodes of abdominal pain",
  "document_types": [
    "encounter_note",
    "diagnosis_note",
    "discharge_summary"
  ],
  "date_range": null,
  "top_k": 10
}
```

Retrieval:

```text
patient_id = 18291
        ↓
document_type filter
        ↓
date/relevance filter
        ↓
vector similarity
        +
full-text score
        ↓
top 10 results
```

---

# 16. Query Classification

Every natural-language request should first pass through a lightweight Query Understanding component.

Output:

```json
{
  "intent": "patient_history",
  "domain": "clinical",
  "entity": "patient",
  "patient_identifier": "RH16-27",
  "date_range": null,
  "requires_semantic_search": true,
  "requires_sql": true,
  "search_terms": [
    "abdominal pain"
  ]
}
```

The planner should classify the request into one of four retrieval modes.

---

# 17. Retrieval Modes

## Mode 1 — Exact SQL

For deterministic structured questions.

Example:

> "How many outpatient visits happened yesterday?"

Use SQL.

---

## Mode 2 — Full-Text

For exact terminology.

Example:

> "Find records containing 'Full Blood Count'."

Use PostgreSQL full-text search.

---

## Mode 3 — Semantic

For conceptual questions.

Example:

> "Find previous records suggesting recurring respiratory problems."

Use vector search.

---

## Mode 4 — Hybrid

For the majority of useful AI queries.

Example:

> "Show me this patient's previous visits where symptoms similar to the current complaint were documented."

Use:

```text
Patient filter
+
date filter
+
document type filter
+
full-text retrieval
+
vector retrieval
+
reranking
```

---

# 18. Hybrid Search Algorithm

Recommended initial implementation:

```text
Query
 │
 ▼
Query Understanding
 │
 ▼
Metadata Filter
 │
 ├── patient_id
 ├── department
 ├── document_type
 ├── date range
 └── facility
 │
 ▼
 ┌──────────────────────┐
 │                      │
 ▼                      ▼
Full-Text Search      Vector Search
 │                      │
 ▼                      ▼
Keyword Candidates    Semantic Candidates
 │                      │
 └──────────┬───────────┘
            ▼
       Candidate Merge
            │
            ▼
          Rerank
            │
            ▼
        Top Results
```

---

# 19. Candidate Retrieval

Do not immediately ask the vector index for only the final number of results.

Instead:

```text
Vector top_k = 30
Full-text top_k = 30
```

Merge them.

Remove duplicates.

Then rerank the resulting candidates.

Final context:

```text
top_k = 5–10
```

depending on the task.

This gives the reranker more candidates to evaluate.

---

# 20. Reranking

The first version can use a weighted score.

Example:

```text
final_score =
    0.55 * semantic_score
  + 0.25 * keyword_score
  + 0.10 * recency_score
  + 0.10 * metadata_score
```

The exact weights must remain configurable.

For patient-history queries, recency may receive a higher weight.

For historical research queries, semantic similarity may dominate.

---

# 21. Recency Scoring

Clinical information is often time-sensitive.

Example:

```python
recency_score =
    decay(document_date, query_context)
```

A recent encounter should generally rank higher than a very old encounter when the query concerns the current episode.

However:

> Do not automatically discard old records.

A 5-year-old diagnosis can still be clinically relevant.

Recency should influence ranking rather than become an absolute filter unless explicitly requested.

---

# 22. SQL Retrieval Must Remain the Source of Truth

The vector index must never become the authoritative database.

For example:

> "How much has this patient been billed?"

Do not answer from an embedding.

Use:

```sql
SELECT SUM(subtotal)
FROM royan_billing
WHERE patient_id = :patient_id;
```

Similarly:

> "How many prescriptions were issued in August?"

Use SQL.

The vector layer is for **finding relevant meaning**, not calculating authoritative numbers.

---

# 23. Agent Tool Architecture

The Backend Agent should expose retrieval tools separately.

Recommended tools:

```text
search_structured_data()
search_full_text()
search_semantic()
search_hybrid()
get_patient_context()
get_encounter_context()
get_lab_history()
get_prescription_history()
get_billing_history()
```

The LLM should not construct arbitrary database access for every request.

Instead:

```text
LLM
 ↓
Tool selection
 ↓
Retrieval service
 ↓
Database
```

---

# 24. Retrieval Service

Create a dedicated service/module:

```text
backend/
├── retrieval/
│   ├── __init__.py
│   ├── planner.py
│   ├── semantic_search.py
│   ├── fulltext_search.py
│   ├── hybrid_search.py
│   ├── reranker.py
│   ├── filters.py
│   ├── embeddings.py
│   ├── context_builder.py
│   └── schemas.py
```

Do not put retrieval logic directly inside the chatbot endpoint.

---

# 25. Retrieval API

Recommended internal endpoint:

```http
POST /api/v1/retrieval/search
```

Request:

```json
{
  "query": "previous records mentioning recurring abdominal pain",
  "patient_id": 18291,
  "domain": "clinical",
  "document_types": [
    "encounter_note",
    "diagnosis_note",
    "discharge_summary"
  ],
  "date_from": null,
  "date_to": null,
  "top_k": 10,
  "mode": "hybrid"
}
```

Response:

```json
{
  "query": "previous records mentioning recurring abdominal pain",
  "mode": "hybrid",
  "results": [
    {
      "document_id": 12881,
      "source_table": "royan_encounter_notes",
      "source_id": 55221,
      "patient_id": 18291,
      "encounter_id": 98321,
      "document_type": "encounter_note",
      "content": "...",
      "semantic_score": 0.91,
      "keyword_score": 0.73,
      "final_score": 0.86
    }
  ]
}
```

---

# 26. Context Builder

Never send the entire retrieved database record directly to the LLM.

The Context Builder should convert retrieval results into a compact context.

Example:

```text
PATIENT
MRN: RH16-27

RELEVANT HISTORY

1. 2026-09-14
Encounter: OPD
Chief complaint: abdominal pain
Clinical note: ...

2. 2026-06-22
Encounter: OPD
Chief complaint: abdominal discomfort
Clinical note: ...

3. 2025-11-03
Encounter: Emergency
Diagnosis note: ...
```

The LLM receives only the relevant context.

---

# 27. Patient Context Engine

Synbot should eventually maintain a reusable patient context layer.

Example:

```text
Patient
 │
 ├── Demographics
 ├── Active Problems
 ├── Allergies
 ├── Recent Encounters
 ├── Relevant Historical Encounters
 ├── Medications
 ├── Lab Results
 ├── Procedures
 └── Billing/HMO
```

This is particularly valuable because the database already has the patient at the root of the clinical foreign-key graph.

---

# 28. Patient Summary Embedding

Create an optional derived document:

```text
patient_summary
```

Example:

```text
Patient RH16-27

Recent clinical history:
- Multiple OPD visits
- Previous abdominal pain complaints
- Previous prescriptions...
- Relevant laboratory findings...
```

This summary can be periodically regenerated.

However:

**Never treat the summary as the authoritative record.**

It is an acceleration layer only.

The underlying tables remain authoritative.

---

# 29. Incremental Indexing

The system must not rebuild all embeddings every time the database changes.

Use incremental indexing.

When a relevant record is created or updated:

```text
Database Change
      ↓
Index Event
      ↓
Content Hash
      ↓
Changed?
 ┌────┴────┐
 No       Yes
 │          │
Stop       Re-embed
            │
            ▼
       Update vector
```

Use:

```text
content_hash
```

to prevent unnecessary embedding API/model calls.

---

# 30. Indexing Worker

Recommended background worker:

```text
retrieval/
    indexing_worker.py
```

Responsibilities:

```text
1. Detect new/updated records
2. Build semantic document
3. Calculate content hash
4. Skip unchanged content
5. Generate embedding
6. Store embedding
7. Update search_vector
8. Mark indexing status
9. Record errors
```

---

# 31. Initial Backfill

For the existing database:

```text
Phase 1
    ↓
Extract relevant text
    ↓
Create synbot_documents
    ↓
Chunk documents
    ↓
Generate embeddings
    ↓
Create vector indexes
    ↓
Validate retrieval
```

Do not attempt to embed all 1.28M+ rows blindly.

Start with the high-value semantic tables.

Recommended first wave:

```text
royan_encounter_notes
royan_encounters
royan_lab_results
royan_prescriptions
royan_discharge/diagnostic content
```

As the missing clinical tables become populated, add them to the index.

The current database audit shows that many child clinical tables such as `royan_encounter_notes`, `royan_vitals`, `royan_lab_results`, allergies and problem lists are currently empty because the Hope source did not provide that data.

Therefore the indexing architecture must be designed for **future live data**, not just today's imported dataset.

---

# 32. Data Quality Guardrails

Semantic search must not hide poor source data.

For example, the current lab dataset contains approximately 203,521 records whose test name is the placeholder:

```text
Imported lab order
```

while the underlying `test_code` is populated.

The indexing worker should therefore avoid treating placeholder values as meaningful semantic content.

Example:

```python
if content == "Imported lab order":
    semantic_index = False
```

Instead, wait until the real laboratory catalog is joined.

---

# 33. Searchable Clinical Quality Flags

Each document should optionally carry:

```json
{
  "data_quality": {
    "is_placeholder": false,
    "completeness_score": 0.92,
    "source_confidence": 0.95
  }
}
```

This allows ranking to penalize poor-quality records.

Example:

```text
semantic_score = 0.91
quality_score = 0.40

final_score = 0.91 * 0.40
```

This prevents poor-quality imported data from dominating retrieval.

---

# 34. Security

Patient semantic indexes contain sensitive clinical information.

Therefore:

### Never expose raw vector tables directly to clients.

All access must go through backend authorization.

Apply:

```text
User
 ↓
Role
 ↓
Facility
 ↓
Department
 ↓
Patient access policy
 ↓
Retrieval
```

The retrieval service must inherit the same authorization rules as normal database queries.

---

# 35. Audit Logging

Every semantic retrieval should be auditable.

Create:

```sql
CREATE TABLE synbot_search_logs (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NULL,

    query TEXT NOT NULL,

    search_mode TEXT,

    patient_id BIGINT NULL,

    filters JSONB,

    result_count INTEGER,

    latency_ms INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Do not necessarily store sensitive full result content in the search log.

Store identifiers and metadata needed for audit/debugging.

---

# 36. Performance Targets

Initial target:

```text
Query understanding: <300 ms
Metadata filtering: <100 ms
Vector/full-text retrieval: <300 ms
Reranking: <500 ms
Context construction: <100 ms
```

Target retrieval layer:

```text
<1 second
```

before the LLM generation time.

The system should measure:

```text
retrieval_latency_ms
embedding_latency_ms
reranking_latency_ms
sql_latency_ms
llm_latency_ms
total_latency_ms
```

This will allow us to identify whether future latency comes from:

```text
database
retrieval
network
LLM
```

rather than guessing.

---

# 37. Query Routing Examples

## Example 1

User:

> "How many patients came to OPD yesterday?"

Router:

```text
intent = aggregation
mode = SQL
```

No vector search.

---

## Example 2

User:

> "Find patients with notes related to recurring headaches."

Router:

```text
intent = semantic_lookup
mode = hybrid
domain = clinical
document_type = notes
```

---

## Example 3

User:

> "What drugs was this patient prescribed during his last three visits?"

Router:

```text
intent = patient_medication_history
mode = SQL
patient_id = resolved
limit = 3 encounters
```

No vector search required.

---

## Example 4

User:

> "Does this patient's current complaint resemble anything documented previously?"

Router:

```text
intent = clinical_similarity
mode = hybrid
patient_id = resolved
semantic_query = current complaint
```

---

## Example 5

User:

> "Show me all lab results related to anemia."

Router:

```text
intent = clinical_semantic_search
mode = hybrid
document_type = lab_result
```

---

# 38. Retrieval Scope Hierarchy

The retrieval planner should progressively narrow the search.

Recommended hierarchy:

```text
LEVEL 0
Entire database

        ↓

LEVEL 1
Tenant / Facility

        ↓

LEVEL 2
Business domain

        ↓

LEVEL 3
Entity type

        ↓

LEVEL 4
Patient / customer / account

        ↓

LEVEL 5
Date range

        ↓

LEVEL 6
Document type

        ↓

LEVEL 7
Full-text + vector search

        ↓

LEVEL 8
Reranking

        ↓

LEVEL 9
LLM context
```

The system should reach the deepest practical level before performing semantic retrieval.

This is the central performance principle.

---

# 39. Future Multi-Company Support

The architecture must not be hard-coded to RoyanHealth.

Synbot is intended to become a reusable platform across healthcare, finance, insurance, ERP and other client systems.

Therefore add:

```text
tenant_id
organization_id
facility_id
```

where appropriate.

Example:

```json
{
  "tenant_id": "royan",
  "facility_id": "royan_main",
  "domain": "clinical"
}
```

The same retrieval architecture can later support:

```text
Placeware
Atiat
SynbotHealth
Finance
ERP
Insurance
```

without rebuilding the retrieval engine.

---

# 40. Domain-Specific Indexes

Do not create one giant universal semantic corpus.

Use logical domains:

```text
clinical
finance
inventory
sales
insurance
hr
operations
documents
```

For healthcare:

```text
clinical/
    patients
    encounters
    notes
    laboratory
    prescriptions
    billing
```

For ERP:

```text
finance/
    ledger
    invoices
    customers
    vendors
    inventory
```

The query planner chooses the relevant domain.

---

# 41. Semantic Index Registry

Create a configuration table or registry:

```text
synbot_index_registry
```

Example:

```json
{
  "source_table": "royan_encounter_notes",
  "document_type": "encounter_note",
  "enabled": true,
  "embedding_enabled": true,
  "fulltext_enabled": true,
  "chunk_size": 500,
  "chunk_overlap": 75
}
```

This allows new data sources to be indexed without changing core retrieval code.

---

# 42. Do Not Over-Chunk

Clinical notes are usually relatively short.

Use adaptive chunking.

Recommended initial defaults:

```text
target chunk: 400–700 tokens
overlap: 50–100 tokens
```

But:

```text
short note < 700 tokens
```

should remain one chunk.

Do not split every database row unnecessarily.

---

# 43. Source Provenance

Every semantic result must retain its source.

Example:

```json
{
  "source": {
    "table": "royan_encounter_notes",
    "record_id": 55221,
    "patient_id": 18291,
    "encounter_id": 98321
  }
}
```

This enables:

- auditability,
- UI navigation,
- citations,
- debugging,
- source verification.

The LLM must be able to say where its information came from.

---

# 44. Grounded Answering

The LLM should receive:

```text
Retrieved evidence
+
source metadata
+
user question
```

and must answer only from the retrieved evidence when the question requires database grounding.

For example:

```text
User:
"Has this patient had abdominal pain before?"

Context:
[Encounter 2026-09-14]
[Encounter 2026-06-22]

LLM:
"Yes. A previous outpatient encounter on 22 June 2026 also documented abdominal discomfort."
```

The system should not infer additional clinical facts that are absent from the retrieved evidence.

---

# 45. Confidence

Every retrieval response should contain an internal confidence score.

Example:

```json
{
  "retrieval_confidence": 0.87,
  "evidence_count": 4,
  "source_quality": 0.94
}
```

Potential response behaviour:

```text
High confidence
→ answer normally

Medium confidence
→ answer with qualification

Low confidence
→ ask for clarification or state insufficient evidence
```

---

# 46. Search Cache

Frequently repeated semantic queries should be cacheable.

Recommended:

```text
Redis / local cache
```

Key:

```text
tenant + user_scope + normalized_query + filters + embedding_model_version
```

However, cache only retrieval results that are safe under the user's authorization scope.

Do not share patient-specific cached results across users without authorization validation.

---

# 47. Embedding Versioning

Embedding models will change.

Store:

```text
embedding_model
embedding_version
embedding_dimension
```

with each embedding.

Example:

```json
{
  "model": "local-model-name",
  "version": "1.0",
  "dimension": 384
}
```

When the model changes:

```text
old embeddings
       ↓
re-index queue
       ↓
new embeddings
       ↓
validation
       ↓
switch active version
```

Do not silently mix incompatible embedding spaces.

---

# 48. Retrieval Metrics

The Backend Agent must instrument retrieval quality.

Track:

```text
query
retrieval_mode
top_k
latency
candidate_count
final_result_count
semantic_score
keyword_score
final_score
user_feedback
```

Later we can evaluate:

```text
Precision@K
Recall@K
Mean Reciprocal Rank
```

These metrics will allow Synbot's retrieval layer to improve empirically rather than through guesswork.

---

# 49. Implementation Phases

## Phase 1 — Foundation

Implement:

```text
pgvector
synbot_documents
synbot_document_chunks
embedding provider
embedding worker
HNSW index
GIN full-text index
```

---

## Phase 2 — Clinical Index

Index:

```text
encounters
encounter notes
diagnosis notes
discharge summaries
prescriptions
lab results
```

Do not wait for every clinical module to be complete.

The current database has many future-facing clinical tables already defined even though several are currently empty.

---

## Phase 3 — Retrieval Planner

Implement:

```text
query classification
domain routing
patient resolution
metadata filtering
search mode selection
```

---

## Phase 4 — Hybrid Search

Implement:

```text
vector search
+
full-text search
+
candidate merging
+
reranking
```

---

## Phase 5 — Agent Integration

Expose retrieval tools to the Backend Agent:

```text
search_hybrid()
search_semantic()
search_fulltext()
query_structured()
get_patient_context()
```

---

## Phase 6 — Performance

Benchmark:

```text
10K records
100K records
1M records
5M records
```

Measure:

```text
p50 latency
p95 latency
p99 latency
```

---

## Phase 7 — Quality

Create a retrieval evaluation dataset.

Example:

```text
100 real user questions
        ↓
expected relevant records
        ↓
automated retrieval test
        ↓
precision/recall measurement
```

Do not declare semantic retrieval production-ready based solely on "it seems to work."

---

# 50. Important Backend Rule

The Backend Agent must NOT implement this architecture as:

```python
SELECT * FROM database
→ send everything to LLM
```

Nor:

```python
SELECT * FROM every table
→ create embeddings
→ search everything
```

Instead:

```text
UNDERSTAND
    ↓
SCOPE
    ↓
FILTER
    ↓
RETRIEVE
    ↓
RERANK
    ↓
CONTEXT
    ↓
REASON
```

---

# 51. Final Target Architecture

```text
                    SYNBOT
                       │
                       ▼
              ┌─────────────────┐
              │ Query Understand │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Retrieval Planner│
              └────────┬────────┘
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          SQL       Full Text   Vector
             │         │         │
             └─────────┼─────────┘
                       ▼
                Candidate Merge
                       │
                       ▼
                    Reranker
                       │
                       ▼
               Context Builder
                       │
                       ▼
                    LLM/Agent
                       │
                       ▼
                 Grounded Answer


                 POSTGRESQL
 ┌─────────────────────────────────────────┐
 │                                         │
 │ Operational Tables                      │
 │      ↓                                  │
 │ Metadata / B-tree indexes               │
 │      ↓                                  │
 │ Full-text / GIN                        │
 │      ↓                                  │
 │ pgvector / HNSW                        │
 │      ↓                                  │
 │ Semantic Retrieval Layer                │
 │                                         │
 └─────────────────────────────────────────┘
```

---

# 52. Acceptance Criteria

The implementation is considered complete when:

### Database

- [ ] `pgvector` enabled.
- [ ] Semantic document tables created.
- [ ] Full-text indexes created.
- [ ] HNSW vector indexes created.
- [ ] Metadata indexes created.
- [ ] Tenant/facility scope supported.

### Indexing

- [ ] Existing relevant clinical records indexed.
- [ ] New records indexed automatically.
- [ ] Updated records re-indexed.
- [ ] Unchanged records skipped.
- [ ] Embedding versions tracked.
- [ ] Failed indexing jobs recoverable.

### Retrieval

- [ ] SQL retrieval supported.
- [ ] Full-text retrieval supported.
- [ ] Semantic retrieval supported.
- [ ] Hybrid retrieval supported.
- [ ] Patient-scoped retrieval supported.
- [ ] Date filtering supported.
- [ ] Department filtering supported.
- [ ] Document-type filtering supported.
- [ ] Candidate reranking implemented.

### Agent

- [ ] Backend Agent can choose retrieval mode.
- [ ] Agent cannot bypass authorization.
- [ ] Agent receives only relevant context.
- [ ] Source provenance retained.
- [ ] Low-confidence results handled safely.

### Performance

- [ ] Retrieval latency measured.
- [ ] p50/p95/p99 recorded.
- [ ] 1M+ record benchmark completed.
- [ ] Retrieval does not require full-table scanning.

### Quality

- [ ] Evaluation query set created.
- [ ] Precision/recall measured.
- [ ] Placeholder/poor-quality records excluded or penalized.
- [ ] Retrieval results manually validated.

---

# 53. Strategic Direction

This retrieval architecture should become a **core Synbot platform capability**, not a RoyanHealth-specific feature.

The same engine can eventually power:

```text
Synbot Health
      │
      ├── Clinical Retrieval
      ├── Patient Context
      └── Medical Knowledge

Synbot Finance
      │
      ├── Ledger Retrieval
      ├── Invoice Retrieval
      └── Financial Documents

Synbot ERP
      │
      ├── Inventory
      ├── Procurement
      ├── Customers
      └── Suppliers

Synbot Insurance
      │
      ├── Policies
      ├── Claims
      └── Customer Records
```

The database remains authoritative.

The retrieval layer becomes Synbot's **intelligence access layer**.

The long-term architecture should therefore be:

```text
                SYNBOT CORE
                    │
          ┌─────────┴─────────┐
          │ Retrieval Engine  │
          └─────────┬─────────┘
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
    SQL Engine   Full Text    Vector Engine
       │            │            │
       └────────────┼────────────┘
                    ▼
               Reranker
                    │
                    ▼
              Context Engine
                    │
                    ▼
             Agent / LLM Layer
```

This gives Synbot a reusable retrieval architecture capable of scaling from the current RoyanHealth dataset into the broader multi-client Synbot platform.