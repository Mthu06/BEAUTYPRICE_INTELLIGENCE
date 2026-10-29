-- =====================================================================
-- BeautyPrice Intelligence - lược đồ CSDL (SQLite 3)
-- Tạo bởi build_database.py; có thể mở bằng DB Browser for SQLite.
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- danh mục
CREATE TABLE IF NOT EXISTS retailers (
    retailer_id     TEXT PRIMARY KEY,
    retailer_name   TEXT NOT NULL,
    country         TEXT,
    currency        TEXT NOT NULL DEFAULT 'VND',
    website_url     TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS categories (
    category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name   TEXT NOT NULL UNIQUE
);

-- ---------------------------------------------------------------- sản phẩm
-- Mỗi dòng là một sản phẩm đang bán tại một nhà bán lẻ (listing).
CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    retailer_id         TEXT NOT NULL REFERENCES retailers(retailer_id) ON UPDATE CASCADE,
    product_name        TEXT NOT NULL CHECK (length(product_name) BETWEEN 1 AND 300),
    brand               TEXT NOT NULL CHECK (length(brand) BETWEEN 1 AND 120),
    category_id         INTEGER REFERENCES categories(category_id),
    product_type        TEXT NOT NULL DEFAULT 'unknown' CHECK (product_type IN ('single', 'bundle', 'multi_pack', 'unknown')),
    product_url         TEXT CHECK (product_url IS NULL OR product_url LIKE 'http%'),
    review_key          TEXT,                       -- khóa nối review theo ID nguồn
    -- thuộc tính trích từ tên sản phẩm (feature engineering)
    volume_ml           REAL CHECK (volume_ml IS NULL OR volume_ml > 0),
    weight_g            REAL CHECK (weight_g IS NULL OR weight_g > 0),
    pack_count          INTEGER CHECK (pack_count IS NULL OR pack_count > 0),
    is_combo            INTEGER NOT NULL DEFAULT 0 CHECK (is_combo IN (0, 1)),
    data_origin         TEXT NOT NULL DEFAULT 'scraped' CHECK (data_origin IN ('scraped', 'manual')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_products_retailer ON products(retailer_id);
CREATE INDEX IF NOT EXISTS idx_products_brand    ON products(brand COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_review   ON products(review_key);

-- Một sản phẩm có thể thuộc nhiều danh mục (quan hệ N-N).
CREATE TABLE IF NOT EXISTS product_categories (
    product_id      TEXT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id),
    PRIMARY KEY (product_id, category_id)
);

-- ---------------------------------------------------------------- lịch sử giá
-- Mỗi lần thu thập (hoặc admin sửa giá) sinh một snapshot mới -> giữ lịch sử biến động giá.
CREATE TABLE IF NOT EXISTS price_snapshots (
    snapshot_id         TEXT PRIMARY KEY,
    product_id          TEXT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    current_price_vnd   REAL NOT NULL CHECK (current_price_vnd > 0),
    listed_price_vnd    REAL CHECK (listed_price_vnd IS NULL OR listed_price_vnd >= current_price_vnd),
    discount_percent    REAL CHECK (discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100),
    discount_source     REAL,                       -- giá trị giảm giá gốc trên website (truy vết)
    rating              REAL CHECK (rating IS NULL OR rating BETWEEN 0 AND 5),
    review_count        INTEGER CHECK (review_count IS NULL OR review_count >= 0),
    collected_at        TEXT NOT NULL,
    source_file         TEXT,
    data_origin         TEXT NOT NULL DEFAULT 'scraped' CHECK (data_origin IN ('scraped', 'manual'))
);
CREATE INDEX IF NOT EXISTS idx_snapshots_product ON price_snapshots(product_id, collected_at);

-- ---------------------------------------------------------------- review
CREATE TABLE IF NOT EXISTS reviews (
    review_pk           INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL REFERENCES retailers(retailer_id),
    source_product_id   TEXT NOT NULL,
    review_id           TEXT NOT NULL,
    product_id          TEXT REFERENCES products(product_id) ON DELETE SET NULL,
    review_key          TEXT,
    product_name        TEXT,
    category            TEXT,
    rating              REAL NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text         TEXT,
    review_date         TEXT,                       -- ISO 8601 sau chuẩn hóa
    review_date_raw     TEXT,                       -- giá trị gốc
    is_bought           INTEGER CHECK (is_bought IS NULL OR is_bought IN (0, 1)),
    has_images          INTEGER CHECK (has_images IS NULL OR has_images IN (0, 1)),
    source_url          TEXT,
    UNIQUE (source, source_product_id, review_id)
);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_key     ON reviews(review_key);

-- ---------------------------------------------------------------- thu thập & đối chiếu
CREATE TABLE IF NOT EXISTS collection_logs (
    run_id              TEXT PRIMARY KEY,
    retailer_id         TEXT REFERENCES retailers(retailer_id),
    script_name         TEXT,
    started_at          TEXT,
    finished_at         TEXT,
    pages_attempted     INTEGER,
    records_found       INTEGER,
    records_saved       INTEGER,
    records_failed      INTEGER,
    status              TEXT,
    error_message       TEXT,
    run_type            TEXT
);

CREATE TABLE IF NOT EXISTS product_matching (
    match_id            TEXT PRIMARY KEY,
    match_group_id      TEXT,
    product_id          TEXT REFERENCES products(product_id) ON DELETE CASCADE,
    retailer_id         TEXT,
    match_method        TEXT,
    match_confidence    REAL,
    match_status        TEXT,
    verified_by_human   INTEGER CHECK (verified_by_human IN (0, 1))
);

-- ---------------------------------------------------------------- người dùng
CREATE TABLE IF NOT EXISTS users (
    username        TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('Admin', 'User')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);

-- ---------------------------------------------------------------- nhật ký làm sạch dữ liệu
CREATE TABLE IF NOT EXISTS etl_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT NOT NULL,
    step            TEXT NOT NULL,
    table_name      TEXT,
    rows_in         INTEGER,
    rows_out        INTEGER,
    rows_affected   INTEGER,
    note            TEXT
);

-- ---------------------------------------------------------------- kết quả học máy (train_models.py ghi)
CREATE TABLE IF NOT EXISTS ml_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task            TEXT NOT NULL CHECK (task IN ('regression', 'classification', 'clustering', 'anomaly')),
    model_name      TEXT NOT NULL,
    is_selected     INTEGER NOT NULL DEFAULT 0,
    params_json     TEXT,
    metrics_json    TEXT,
    trained_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ml_price_predictions (
    product_id          TEXT PRIMARY KEY REFERENCES products(product_id) ON DELETE CASCADE,
    split               TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
    actual_price_vnd    REAL NOT NULL,
    predicted_price_vnd REAL NOT NULL,
    actual_segment      TEXT,
    predicted_segment   TEXT                        -- từ mô hình phân loại
);

CREATE TABLE IF NOT EXISTS ml_clusters (
    product_id      TEXT PRIMARY KEY REFERENCES products(product_id) ON DELETE CASCADE,
    cluster         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ml_anomalies (
    product_id      TEXT PRIMARY KEY REFERENCES products(product_id) ON DELETE CASCADE,
    anomaly_score   REAL NOT NULL,                  -- càng thấp càng bất thường
    is_anomaly      INTEGER NOT NULL CHECK (is_anomaly IN (0, 1)),
    reason          TEXT
);

CREATE TABLE IF NOT EXISTS ml_feature_importance (
    task            TEXT NOT NULL,
    feature         TEXT NOT NULL,
    importance      REAL NOT NULL,
    PRIMARY KEY (task, feature)
);

-- ---------------------------------------------------------------- view tiện dụng
-- Giá hiện tại = snapshot mới nhất của từng sản phẩm.
CREATE VIEW IF NOT EXISTS v_latest_snapshot AS
SELECT * FROM (
    SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.product_id ORDER BY s.collected_at DESC, s.rowid DESC) AS rn
    FROM price_snapshots s
) WHERE rn = 1;

CREATE VIEW IF NOT EXISTS v_products AS
SELECT p.product_id, p.retailer_id, r.retailer_name AS source, p.product_name, p.brand,
       c.category_name AS category, p.product_type, p.product_url, p.review_key,
       p.volume_ml, p.weight_g, p.pack_count, p.is_combo, p.data_origin,
       s.snapshot_id, s.current_price_vnd, s.listed_price_vnd, s.discount_percent,
       s.rating, s.review_count, s.collected_at
FROM products p
JOIN retailers r ON r.retailer_id = p.retailer_id
LEFT JOIN categories c ON c.category_id = p.category_id
LEFT JOIN v_latest_snapshot s ON s.product_id = p.product_id;
