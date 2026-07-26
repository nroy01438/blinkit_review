-- AISLE core schema. See aisle/README.md §3 for the data-model rationale.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS sources (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN
                        ('appstore','playstore','reddit','forum','social','marketplace','manual_upload')),
    brand           TEXT NOT NULL DEFAULT 'blinkit',
    config_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_fetched_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS documents (
    id              BIGSERIAL PRIMARY KEY,
    source_id       BIGINT NOT NULL REFERENCES sources(id),
    external_id     TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    lang_detected   TEXT,
    author_hash     TEXT NOT NULL,
    rating          SMALLINT,
    posted_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    url             TEXT,
    meta_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash    TEXT NOT NULL,
    dupe_of_id      BIGINT REFERENCES documents(id),
    simhash         BIGINT,
    UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_simhash ON documents(simhash);
CREATE INDEX IF NOT EXISTS idx_documents_posted_at ON documents(posted_at);
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_text_trgm ON documents USING gin (raw_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_documents_text_fts ON documents USING gin (to_tsvector('english', raw_text));

CREATE TABLE IF NOT EXISTS classifications (
    id                    BIGSERIAL PRIMARY KEY,
    document_id           BIGINT NOT NULL REFERENCES documents(id),
    schema_version         TEXT NOT NULL,
    stage_reached         SMALLINT NOT NULL DEFAULT 0,
    -- Stage 1 gate
    is_junk               BOOLEAN,
    junk_reason           TEXT,
    -- Stage 2 PM utility
    specificity           SMALLINT,
    actionability         SMALLINT,
    evidence_strength     SMALLINT,
    emotional_intensity   SMALLINT,
    pm_utility_score      SMALLINT,
    pm_verdict            TEXT,
    -- Stage 3 relevance
    discovery_relevance   SMALLINT,
    relevance_verdict     TEXT,
    -- Stage 4 extraction
    categories_mentioned  TEXT[] NOT NULL DEFAULT '{}',
    behaviour_codes       TEXT[] NOT NULL DEFAULT '{}',
    barrier_codes         TEXT[] NOT NULL DEFAULT '{}',
    jtbd_statement        TEXT,
    unmet_need            TEXT,
    segment_label         TEXT,
    lifecycle_stage       TEXT,
    sentiment             TEXT,
    severity              SMALLINT,
    supporting_span       TEXT,
    -- meta
    confidence            REAL,
    abstained             BOOLEAN NOT NULL DEFAULT false,
    model_used            TEXT,
    prompt_version        TEXT,
    tokens_in             INT,
    tokens_out            INT,
    latency_ms            INT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, schema_version)
);
CREATE INDEX IF NOT EXISTS idx_classifications_document_id ON classifications(document_id);
CREATE INDEX IF NOT EXISTS idx_classifications_relevance ON classifications(discovery_relevance);
CREATE INDEX IF NOT EXISTS idx_classifications_abstained ON classifications(abstained);

CREATE TABLE IF NOT EXISTS embeddings (
    document_id BIGINT PRIMARY KEY REFERENCES documents(id),
    vector      VECTOR(384) NOT NULL,
    model_name  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings USING hnsw (vector vector_cosine_ops);

CREATE TABLE IF NOT EXISTS runs (
    id                  BIGSERIAL PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    trigger             TEXT NOT NULL CHECK (trigger IN ('cron','manual','upload')),
    stage_stats_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    cost_usd            NUMERIC(10,4) NOT NULL DEFAULT 0,
    config_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running','completed','failed','partial'))
);

CREATE TABLE IF NOT EXISTS themes (
    id                BIGSERIAL PRIMARY KEY,
    run_id            BIGINT NOT NULL REFERENCES runs(id),
    label             TEXT NOT NULL,
    description       TEXT,
    taxonomy_node     TEXT,
    doc_count         INT NOT NULL DEFAULT 0,
    doc_total         INT NOT NULL DEFAULT 0,
    prevalence        REAL,
    ci_low            REAL,
    ci_high           REAL,
    source_spread_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_run    BIGINT REFERENCES runs(id),
    delta_vs_prev_run REAL,
    centroid          VECTOR(384),
    status            TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','growing','stable','decaying')),
    noise_pct         REAL,
    stability_ari     REAL
);
CREATE INDEX IF NOT EXISTS idx_themes_run_id ON themes(run_id);

CREATE TABLE IF NOT EXISTS theme_documents (
    theme_id         BIGINT NOT NULL REFERENCES themes(id),
    document_id      BIGINT NOT NULL REFERENCES documents(id),
    membership_score REAL,
    is_exemplar      BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (theme_id, document_id)
);

CREATE TABLE IF NOT EXISTS insights (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              BIGINT NOT NULL REFERENCES runs(id),
    theme_ids           BIGINT[] NOT NULL DEFAULT '{}',
    title               TEXT NOT NULL,
    statement           TEXT NOT NULL,
    so_what             TEXT NOT NULL,
    opportunity         TEXT NOT NULL,
    affected_segments   TEXT[] NOT NULL DEFAULT '{}',
    affected_categories TEXT[] NOT NULL DEFAULT '{}',
    prevalence          REAL,
    ci_low              REAL,
    ci_high             REAL,
    counter_evidence    TEXT NOT NULL,
    iqs_total           SMALLINT,
    iqs_breakdown_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    grade               TEXT CHECK (grade IN ('A','B','C','D')),
    status              TEXT NOT NULL DEFAULT 'auto'
                            CHECK (status IN ('auto','human_approved','human_rejected')),
    is_negative_control BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_insights_run_id ON insights(run_id);
CREATE INDEX IF NOT EXISTS idx_insights_grade ON insights(grade);

CREATE TABLE IF NOT EXISTS insight_evidence (
    id               BIGSERIAL PRIMARY KEY,
    insight_id       BIGINT NOT NULL REFERENCES insights(id),
    document_id      BIGINT NOT NULL REFERENCES documents(id),
    quote            TEXT NOT NULL,
    quote_char_start INT,
    quote_char_end   INT,
    supports         TEXT NOT NULL CHECK (supports IN ('direct','partial','counter'))
);
CREATE INDEX IF NOT EXISTS idx_insight_evidence_insight_id ON insight_evidence(insight_id);

CREATE TABLE IF NOT EXISTS golden_labels (
    id             BIGSERIAL PRIMARY KEY,
    document_id    BIGINT NOT NULL REFERENCES documents(id),
    human_label_json JSONB NOT NULL,
    annotator_id   TEXT NOT NULL,
    round          INT NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, annotator_id, round)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    content_hash TEXT PRIMARY KEY,
    prompt_version TEXT NOT NULL,
    model        TEXT NOT NULL,
    response_json JSONB NOT NULL,
    tokens_in    INT NOT NULL,
    tokens_out   INT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS needs_human_review (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id),
    stage        TEXT NOT NULL,
    reason       TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved     BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
