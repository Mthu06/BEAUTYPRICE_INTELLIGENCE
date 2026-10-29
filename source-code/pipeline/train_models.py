"""Huấn luyện các mô hình học máy từ CSDL và ghi kết quả vào CSDL để website hiển thị.

    1. Hồi quy (học giám sát)     : dự đoán giá bán hiện tại.
    2. Phân loại (học giám sát)   : phân khúc giá Thấp / Trung bình / Cao.
    3. Phân cụm (không giám sát)  : K-Means, chọn k theo silhouette.
    4. Phát hiện bất thường       : Isolation Forest.

Chạy:  pip install -r requirements-ml.txt  rồi  python train_models.py
Đầu ra: các bảng ml_* trong dataset/beautyprice.db và mô hình .joblib trong dataset/models/.
"""
import json
import os
import sqlite3
import sys
import warnings
from datetime import datetime
from pathlib import Path

# joblib dò số nhân CPU qua wmic (không còn trên Windows 11) -> in traceback vô hại; khai báo sẵn để tránh.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.cluster import KMeans
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, IsolationForest, RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, r2_score, recall_score, silhouette_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore", category=UserWarning)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("BEAUTY_DB", ROOT / "dataset" / "beautyprice.db"))
MODEL_DIR = Path(os.environ.get("BEAUTY_MODEL_DIR", ROOT / "dataset" / "models"))
SEED = 42
SEGMENTS = ["Thấp", "Trung bình", "Cao"]
NOW = datetime.now().isoformat(timespec="seconds")

CATEGORICAL = ["brand", "category", "product_type", "retailer_id"]
NUMERIC = ["category_count", "rating", "review_count_log", "volume_ml_log", "weight_g_log", "pack_count", "is_combo"]


def load_data(conn):
    df = pd.read_sql_query("""
        SELECT v.product_id, v.retailer_id, v.brand, COALESCE(v.category, 'Không rõ') AS category, v.product_type,
               v.current_price_vnd AS price, v.listed_price_vnd AS listed, v.discount_percent AS discount,
               v.rating, v.review_count, v.volume_ml, v.weight_g, v.pack_count, v.is_combo,
               (SELECT COUNT(*) FROM product_categories pc WHERE pc.product_id = v.product_id) AS category_count
        FROM v_products v WHERE v.current_price_vnd > 0""", conn)
    df["brand"] = df["brand"].str.casefold()
    df["review_count_log"] = np.log1p(df["review_count"])
    df["volume_ml_log"] = np.log1p(df["volume_ml"])
    df["weight_g_log"] = np.log1p(df["weight_g"])
    df["price_log"] = np.log(df["price"])
    return df


def preprocessor(categorical, numeric, min_frequency=5):
    return ColumnTransformer([
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=min_frequency,
                                                   sparse_output=False))]), categorical),
        ("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler())]), numeric),
    ])


def importance_by_feature(pipeline, categorical, numeric):
    """Gộp độ quan trọng của các cột one-hot về tên thuộc tính gốc."""
    model = pipeline.named_steps["model"]
    if not hasattr(model, "feature_importances_"):
        return {}
    names = pipeline.named_steps["prep"].get_feature_names_out()
    result = {}
    for name, value in zip(names, model.feature_importances_):
        raw = name.split("__", 1)[1]
        base = next((c for c in categorical if raw.startswith(c + "_")), None) or raw.replace("missingindicator_", "")
        result[base] = result.get(base, 0.0) + float(value)
    return dict(sorted(result.items(), key=lambda kv: -kv[1]))


def save_run(conn, task, name, selected, params, metrics):
    conn.execute("INSERT INTO ml_runs(task, model_name, is_selected, params_json, metrics_json, trained_at) VALUES (?,?,?,?,?,?)",
                 (task, name, int(selected), json.dumps(params, ensure_ascii=False), json.dumps(metrics, ensure_ascii=False), NOW))


def regression_metrics(y_true, y_pred):
    return {"mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "r2": float(r2_score(y_true, y_pred)),
            "mape": float(np.mean(np.abs(y_pred - y_true) / y_true) * 100)}


# ---------------------------------------------------------------- 1 + 2. học giám sát

def supervised(conn, df):
    features = CATEGORICAL + NUMERIC
    idx_train, idx_test = train_test_split(df.index, test_size=0.2, random_state=SEED)
    idx_train, idx_val = train_test_split(idx_train, test_size=0.25, random_state=SEED)  # 60/20/20
    split = pd.Series("train", index=df.index)
    split[idx_val], split[idx_test] = "validation", "test"
    X, y = df[features], df["price"]
    print(f"  Chia dữ liệu: train={len(idx_train)}, validation={len(idx_val)}, test={len(idx_test)}")

    # ---- hồi quy giá (học trên log giá, đánh giá bằng VND)
    candidates = {
        "Dummy (trung vị)": DummyRegressor(strategy="median"),
        "Ridge Regression": Ridge(alpha=1.0),
        "Random Forest Regressor": RandomForestRegressor(n_estimators=200, min_samples_leaf=2, n_jobs=-1, random_state=SEED),
        "Extra Trees Regressor": ExtraTreesRegressor(n_estimators=200, min_samples_leaf=2, n_jobs=-1, random_state=SEED),
    }
    scores = {}
    for name, model in candidates.items():
        pipe = Pipeline([("prep", preprocessor(CATEGORICAL, NUMERIC)), ("model", model)])
        pipe.fit(X.loc[idx_train], np.log(y.loc[idx_train]))
        scores[name] = regression_metrics(y.loc[idx_val].values, np.exp(pipe.predict(X.loc[idx_val])))
        print(f"  [hồi quy] {name:<26} validation MAE={scores[name]['mae']:>10,.0f}  R²={scores[name]['r2']:.3f}")
    best = min((n for n in scores if not n.startswith("Dummy")), key=lambda n: scores[n]["mae"])
    regressor = Pipeline([("prep", preprocessor(CATEGORICAL, NUMERIC)), ("model", candidates[best])])
    fit_idx = idx_train.union(idx_val)
    regressor.fit(X.loc[fit_idx], np.log(y.loc[fit_idx]))
    test_metrics = regression_metrics(y.loc[idx_test].values, np.exp(regressor.predict(X.loc[idx_test])))
    print(f"  => Chọn {best}: test MAE={test_metrics['mae']:,.0f} VND, RMSE={test_metrics['rmse']:,.0f}, R²={test_metrics['r2']:.3f}, MAPE={test_metrics['mape']:.1f}%")
    for name, metrics in scores.items():
        save_run(conn, "regression", name, name == best, {"target": "log(current_price_vnd)", "features": features},
                 {"validation": metrics, **({"test": test_metrics} if name == best else {})})
    df["predicted_price"] = np.exp(regressor.predict(X))
    joblib.dump(regressor, MODEL_DIR / "price_regressor.joblib", compress=3)
    for feature, value in importance_by_feature(regressor, CATEGORICAL, NUMERIC).items():
        conn.execute("INSERT INTO ml_feature_importance VALUES ('regression', ?, ?)", (feature, value))

    # ---- phân loại phân khúc giá (ngưỡng = phân vị 1/3, 2/3 của tập train)
    q1, q2 = np.quantile(y.loc[idx_train], [1 / 3, 2 / 3])
    segment = pd.cut(y, [-np.inf, q1, q2, np.inf], labels=SEGMENTS).astype(str)
    classifiers = {
        "Dummy (lớp phổ biến)": DummyClassifier(strategy="most_frequent"),
        "Logistic Regression": LogisticRegression(max_iter=2000),
        "Random Forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=2, n_jobs=-1, random_state=SEED),
        "Extra Trees": ExtraTreesClassifier(n_estimators=200, min_samples_leaf=2, n_jobs=-1, random_state=SEED),
    }

    def clf_metrics(y_true, y_pred):
        return {"accuracy": float(accuracy_score(y_true, y_pred)),
                "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
                "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0))}

    clf_scores = {}
    for name, model in classifiers.items():
        pipe = Pipeline([("prep", preprocessor(CATEGORICAL, NUMERIC)), ("model", model)])
        pipe.fit(X.loc[idx_train], segment.loc[idx_train])
        clf_scores[name] = clf_metrics(segment.loc[idx_val], pipe.predict(X.loc[idx_val]))
        print(f"  [phân loại] {name:<24} validation F1-macro={clf_scores[name]['f1_macro']:.3f}")
    best_clf = max((n for n in clf_scores if not n.startswith("Dummy")), key=lambda n: clf_scores[n]["f1_macro"])
    classifier = Pipeline([("prep", preprocessor(CATEGORICAL, NUMERIC)), ("model", classifiers[best_clf])])
    classifier.fit(X.loc[fit_idx], segment.loc[fit_idx])
    test_pred = classifier.predict(X.loc[idx_test])
    clf_test = clf_metrics(segment.loc[idx_test], test_pred)
    clf_test["confusion_matrix"] = {"labels": SEGMENTS,
                                    "matrix": confusion_matrix(segment.loc[idx_test], test_pred, labels=SEGMENTS).tolist()}
    print(f"  => Chọn {best_clf}: test accuracy={clf_test['accuracy']:.3f}, F1-macro={clf_test['f1_macro']:.3f}")
    for name, metrics in clf_scores.items():
        save_run(conn, "classification", name, name == best_clf,
                 {"target": "price_segment", "thresholds_vnd": {"q1": float(q1), "q2": float(q2)}, "features": features},
                 {"validation": metrics, **({"test": clf_test} if name == best_clf else {})})
    df["predicted_segment"] = classifier.predict(X)
    joblib.dump(classifier, MODEL_DIR / "price_segment_classifier.joblib", compress=3)
    for feature, value in importance_by_feature(classifier, CATEGORICAL, NUMERIC).items():
        conn.execute("INSERT INTO ml_feature_importance VALUES ('classification', ?, ?)", (feature, value))

    conn.executemany("INSERT INTO ml_price_predictions VALUES (?,?,?,?,?,?)",
                     [(r.product_id, split[i], r.price, float(r.predicted_price), segment[i], r.predicted_segment)
                      for i, r in df.iterrows()])


# ---------------------------------------------------------------- 3. phân cụm

def clustering(conn, df):
    categorical, numeric = ["category", "product_type", "retailer_id"], ["price_log", "discount", "rating", "review_count_log", "category_count"]
    prep = preprocessor(categorical, numeric, min_frequency=20)
    X = prep.fit_transform(df[categorical + numeric])
    sample = np.random.RandomState(SEED).choice(len(X), size=min(3000, len(X)), replace=False)
    results = []
    for k in range(2, 11):
        model = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
        sil = float(silhouette_score(X[sample], model.labels_[sample]))
        results.append({"k": k, "inertia": float(model.inertia_), "silhouette": sil})
        print(f"  [K-Means] k={k:<2} silhouette={sil:.3f}")
    best = max(results, key=lambda r: r["silhouette"])
    model = KMeans(n_clusters=best["k"], n_init=10, random_state=SEED).fit(X)
    print(f"  => Chọn k={best['k']} (silhouette cao nhất {best['silhouette']:.3f})")
    save_run(conn, "clustering", "K-Means", True, {"k": best["k"], "categorical": categorical, "numeric": numeric},
             {"silhouette": best["silhouette"], "inertia": best["inertia"], "model_selection": results})
    conn.executemany("INSERT INTO ml_clusters VALUES (?,?)", zip(df["product_id"], model.labels_.astype(int).tolist()))
    joblib.dump({"preprocessor": prep, "model": model}, MODEL_DIR / "kmeans.joblib", compress=3)


# ---------------------------------------------------------------- 4. bất thường

def anomalies(conn, df, contamination=0.05):
    data = df.copy()
    # Giá so với trung vị cùng danh mục: phát hiện sản phẩm đắt/rẻ bất thường trong nhóm của nó.
    data["price_vs_category"] = data["price_log"] - data.groupby("category")["price_log"].transform("median")
    data["listed_ratio"] = np.log(data["listed"] / data["price"])
    numeric = ["price_log", "price_vs_category", "discount", "listed_ratio", "rating", "review_count_log"]
    prep = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    X = prep.fit_transform(data[numeric])
    model = IsolationForest(n_estimators=300, contamination=contamination, random_state=SEED).fit(X)
    score, flag = model.decision_function(X), (model.predict(X) == -1).astype(int)

    labels = {"price_log": ("Giá rất cao", "Giá rất thấp"), "price_vs_category": ("Đắt bất thường so với danh mục", "Rẻ bất thường so với danh mục"),
              "discount": ("Giảm giá rất sâu", "Giảm giá rất ít"), "listed_ratio": ("Giá niêm yết cao bất thường", "Giá niêm yết sát giá bán"),
              "rating": ("Rating cao", "Rating thấp bất thường"), "review_count_log": ("Lượt đánh giá rất nhiều", "Lượt đánh giá rất ít")}

    def reason(row):
        top = np.argsort(-np.abs(row))[:2]
        return "; ".join(labels[numeric[i]][0 if row[i] > 0 else 1] for i in top if abs(row[i]) >= 1.5) or "Kết hợp nhiều yếu tố"

    reasons = [reason(row) if f else None for row, f in zip(X, flag)]
    conn.executemany("INSERT INTO ml_anomalies VALUES (?,?,?,?)", zip(df["product_id"], score.astype(float).tolist(), flag.tolist(), reasons))
    sensitivity = [{"contamination": c, "flagged": int((IsolationForest(n_estimators=300, contamination=c, random_state=SEED).fit(X).predict(X) == -1).sum())}
                   for c in (0.02, 0.05, 0.08)]
    save_run(conn, "anomaly", "Isolation Forest", True, {"contamination": contamination, "features": numeric},
             {"flagged": int(flag.sum()), "flagged_percent": float(flag.mean() * 100), "sensitivity": sensitivity})
    print(f"  [Isolation Forest] đánh dấu {flag.sum()} sản phẩm ({flag.mean() * 100:.1f}%)")
    joblib.dump({"preprocessor": prep, "model": model, "features": numeric}, MODEL_DIR / "isolation_forest.joblib", compress=3)


def main():
    if not DB_PATH.exists():
        sys.exit(f"Chưa có CSDL {DB_PATH}. Hãy chạy: python build_database.py")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    df = load_data(conn)
    print(f"Dữ liệu huấn luyện: {len(df)} sản phẩm (giá mới nhất của mỗi sản phẩm)")
    with conn:
        for table in ("ml_runs", "ml_price_predictions", "ml_clusters", "ml_anomalies", "ml_feature_importance"):
            conn.execute(f"DELETE FROM {table}")
        print("1-2. Học giám sát (hồi quy + phân loại)")
        supervised(conn, df)
        print("3. Phân cụm K-Means")
        clustering(conn, df)
        print("4. Phát hiện bất thường")
        anomalies(conn, df)
    conn.close()
    print(f"Xong. Kết quả đã ghi vào {DB_PATH.name}, mô hình lưu ở {MODEL_DIR}")


if __name__ == "__main__":
    main()
