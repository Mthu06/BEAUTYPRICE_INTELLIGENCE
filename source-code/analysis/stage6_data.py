"""Shared input validation and source-aware review analysis. Never writes raw CSV."""
from pathlib import Path
import re
import math
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'dataset' / 'raw'
GAP_REASON = 'No verified equivalent product matches are currently available for cross-retailer comparison.'
MATCH_REASON = 'Matching denominator (N_need_matching) has not been formally defined.'
REVIEW_SCOPE = 'Review analysis scope: Hasaki and Guardian; independent of price metrics.'

def missing(s):
    return s.isna() | s.astype(str).str.strip().eq('')

def numeric(s):
    return pd.to_numeric(s, errors='coerce').replace([float('inf'), -float('inf')], float('nan'))

def truth(s):
    return s.fillna('').astype(str).str.strip().str.lower().isin(['true', 'yes', '1'])

def unique_nonblank(s):
    return s.loc[~missing(s)].nunique()

def read_review_source(source):
    paths = sorted(DATA.rglob(f'{source}_reviews.csv'))
    if len(paths) != 1:
        raise ValueError(f'Expected one {source} source, found {paths}')
    frame = pd.read_csv(paths[0], dtype=str, encoding='utf-8-sig', low_memory=False)
    required = ['source', 'source_product_id', 'rating', 'category', 'review_date', 'review_text']
    if any(c not in frame for c in required):
        raise ValueError(f'{source} schema missing required columns')
    if not frame['source'].str.lower().eq(source).all():
        raise ValueError(f'{source} source contains other retailers')
    frame['source'] = frame['source'].str.strip().str.lower()
    frame['reviewed_product_key'] = (frame['source'] + ':' + frame['source_product_id']).where(~missing(frame['source_product_id']))
    frame['category_display'] = frame['category'].fillna('Chưa phân loại').replace('', 'Chưa phân loại')
    # Vietnamese dates: e.g. 22 tháng 4, 2025. Preserve original string separately.
    normalized = frame['review_date'].str.replace(r'^(\d{1,2})\s+tháng\s+(\d{1,2}),?\s+(\d{4})$', r'\3-\2-\1', regex=True)
    frame['review_date_parsed'] = pd.to_datetime(normalized, errors='coerce', format='%Y-%m-%d' if source=='guardian' else '%Y-%m-%d %H:%M:%S')
    observed = numeric(frame['rating'])
    # Observed values 2.5..5 including half stars support a 1–5 scale;
    # fail loudly on contradictory observations rather than silently rescale.
    if observed.dropna().empty or not observed.dropna().between(1, 5).all():
        raise ValueError('Review rating observations do not support the documented 1–5 scale')
    frame['rating_numeric'] = observed.where(observed.between(1, 5))
    return paths[0], frame

def read_guardian():
    """Retain the existing Guardian-only reader for compatibility and regression."""
    return read_review_source('guardian')

def read_reviews():
    sources = [read_review_source(source) for source in ['hasaki', 'guardian']]
    return [path for path, _ in sources], pd.concat([frame for _, frame in sources], ignore_index=True)

def review_metrics(frame):
    rating = frame['rating_numeric'].dropna()
    def rate(col):
        known = ~missing(frame[col])
        return float(truth(frame.loc[known, col]).mean()) if known.any() else None
    unknown = frame['product_id_match'].fillna('').str.strip().str.lower().eq('unknown')
    return dict(total=len(frame), products=unique_nonblank(frame['reviewed_product_key']),
                mean=float(rating.mean()) if len(rating) else None,
                median=float(rating.median()) if len(rating) else None,
                purchased=rate('is_bought'), images=rate('has_images'),
                unknown=int(unknown.sum()), unknown_rate=float(unknown.mean()) if len(frame) else None)

def review_source_quality(frame):
    """Audit source records without removing rows or asserting a price-product link."""
    import json
    rows = []
    for source, group in frame.groupby('source'):
        valid = numeric(group['rating']).between(1, 5)
        ratings = numeric(group.loc[valid, 'rating'])
        flags = group['product_id_match'].where(~missing(group['product_id_match']), 'MISSING').value_counts().to_dict()
        rows.append(dict(
            source=source, total_reviews=len(group), unique_source_products=unique_nonblank(group['reviewed_product_key']),
            valid_rating_n=int(valid.sum()), missing_rating_n=int(missing(group['rating']).sum()),
            invalid_rating_n=int((~missing(group['rating']) & ~valid).sum()),
            min_rating=ratings.min(), max_rating=ratings.max(), mean_rating=ratings.mean(), median_rating=ratings.median(),
            missing_review_text_n=int(missing(group['review_text']).sum()),
            missing_review_date_n=int(missing(group['review_date']).sum()),
            invalid_review_date_n=int((~missing(group['review_date']) & group['review_date_parsed'].isna()).sum()),
            duplicate_review_n=int(group.duplicated(['source','source_product_id','review_id']).sum()),
            is_bought_known_n=int((~missing(group['is_bought'])).sum()), is_bought_true_n=int(truth(group['is_bought']).sum()),
            has_images_known_n=int((~missing(group['has_images'])).sum()), has_images_true_n=int(truth(group['has_images']).sum()),
            product_id_match_counts=json.dumps({str(k):int(v) for k,v in flags.items()},ensure_ascii=False,sort_keys=True),
            sample_share=len(group)/len(frame)))
    return pd.DataFrame(rows)

def verified_rows(matching):
    return matching.loc[matching['match_status'].fillna('').str.lower().eq('matched') & truth(matching['verified_by_human'])].copy()

def cross_source_gaps(snapshots, matching):
    """Same verified match_group_id, same local date, latest snapshot per retailer.

    Human verification must establish variant/size/package equivalence. Candidate
    confidence or normalized names alone never qualify a group.
    """
    verified = verified_rows(matching)
    cols = ['match_group_id', 'observation_date', 'retailer_n', 'min_price_vnd', 'max_price_vnd', 'price_gap_vnd']
    if verified.empty:
        return pd.DataFrame(columns=cols)
    verified = verified.loc[~missing(verified['match_group_id']), ['match_group_id', 'product_id', 'retailer_id']].drop_duplicates()
    # Reject ambiguous assignments instead of multiplying observations through a join.
    if verified.groupby(['product_id','retailer_id'])['match_group_id'].nunique().gt(1).any():
        raise ValueError('A verified product belongs to multiple equivalent groups')
    joined = snapshots.merge(verified, on=['product_id','retailer_id'], how='inner', validate='many_to_one')
    joined['price'] = numeric(joined['current_price_vnd'])
    joined['time'] = pd.to_datetime(joined['collected_at'], errors='coerce', utc=True)
    joined = joined.loc[joined['price'].gt(0) & joined['time'].notna()].copy()
    joined['observation_date'] = joined['time'].dt.tz_convert('Asia/Ho_Chi_Minh').dt.strftime('%Y-%m-%d')
    latest = joined.sort_values(['time','snapshot_id']).drop_duplicates(['match_group_id','observation_date','retailer_id'], keep='last')
    result = latest.groupby(['match_group_id','observation_date']).agg(retailer_n=('retailer_id','nunique'), min_price_vnd=('price','min'), max_price_vnd=('price','max')).reset_index()
    result = result.loc[result['retailer_n'].ge(2)].copy()
    result['price_gap_vnd'] = result['max_price_vnd'] - result['min_price_vnd']
    return result[cols]

def numeric_description(variable, source, series, valid, unit, conditions, outlier=False):
    miss = missing(series)
    values = numeric(series)
    clean = values.loc[valid]
    q1, q3 = clean.quantile(.25), clean.quantile(.75)
    iqr = q3-q1
    low, high = q1-1.5*iqr, q3+1.5*iqr
    count = int(((clean < low) | (clean > high)).sum())
    result = dict(variable=variable, source=source, total_n=len(series), valid_n=int(valid.sum()),
                  missing_n=int(miss.sum()), invalid_n=int((~miss & ~valid).sum()),
                  missing_invalid_rate_pct=float((~valid).mean()*100), min=clean.min(), q1=q1,
                  mean=clean.mean(), median=clean.median(), q3=q3, max=clean.max(), std=clean.std(), iqr=iqr,
                  lower_bound=low if outlier else None, upper_bound=high if outlier else None,
                  outlier_candidate_n=count if outlier else None,
                  outlier_candidate_rate_pct=count/len(clean)*100 if outlier and len(clean) else None,
                  unit=unit, filter_conditions=conditions)
    return result

def categorical_description(frame, columns, source):
    rows = []
    for col in columns:
        if col not in frame: continue
        values = frame[col].where(~missing(frame[col]), 'MISSING')
        unique = unique_nonblank(frame[col])
        for value, count in values.value_counts(dropna=False).items():
            rows.append(dict(source=source, variable=col, value=str(value), count=int(count),
                             percentage=count/len(frame)*100, unique_count=unique, denominator_n=len(frame)))
    return rows
