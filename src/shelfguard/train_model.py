import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupShuffleSplit

REQUIRED_NUMERIC_COLS = [
    "days_until_expiry",
    "base_price",
    "initial_quantity",
    "daily_demand",
    "discount_pct",
]

REQUIRED_COLS = REQUIRED_NUMERIC_COLS + ["product_id"]

FEATURES = ["remaining_hours", "base_price", "initial_quantity", "daily_demand"]
TARGET = "discount_pct"


def validate_and_preprocess(df: pd.DataFrame):
    total_rows = len(df)
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    df = df.copy()

    for col in REQUIRED_NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=REQUIRED_NUMERIC_COLS)

    df["remaining_hours"] = df["days_until_expiry"] * 24

    usable_rows = len(df)
    return df, total_rows, total_rows - usable_rows


def split_data(df, test_size=0.2, random_state=42):
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(gss.split(df, groups=df["product_id"]))

    train_df = df.iloc[train_idx]
    test_df = df.iloc[test_idx]

    return train_df, test_df


def train_model(X, y, random_state=42):
    model = xgb.XGBRegressor(random_state=random_state)
    model.fit(X, y)
    return model


def evaluate_model(model, X_test, y_test):
    preds = model.predict(X_test)
    # Target is represented as a fraction (e.g., 0.25 = 25%).
    # We clip predictions to the requested 0-70% range represented as [0, 0.70].
    recommended_discount = np.clip(preds, 0.0, 0.70)
    mae = mean_absolute_error(y_test, recommended_discount)
    rmse = np.sqrt(mean_squared_error(y_test, recommended_discount))
    return mae, rmse, recommended_discount


def run_pipeline(csv_path="data/perishable_goods_management.csv", model_dir="models"):
    if not os.path.exists(csv_path):
        print(f"Error: Data file not found at {csv_path}")
        sys.exit(1)

    df_raw = pd.read_csv(csv_path)
    try:
        df, total_rows, rejected_rows = validate_and_preprocess(df_raw)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    train_df, test_df = split_data(df)

    train_product_ids = set(train_df["product_id"])
    test_product_ids = set(test_df["product_id"])
    overlap = len(train_product_ids.intersection(test_product_ids))

    X_train, y_train = train_df[FEATURES], train_df[TARGET]
    X_test, y_test = test_df[FEATURES], test_df[TARGET]

    print("--- SPLIT METHODOLOGY ---")
    print("GroupShuffleSplit on product_id")
    print(f"Total source CSV rows: {total_rows}")
    print(f"Usable training rows: {len(df)}")
    print(f"Rejected rows: {rejected_rows}")
    print(f"Training rows: {len(train_df)}")
    print(f"Test rows: {len(test_df)}")
    print(f"Unique training products: {len(train_product_ids)}")
    print(f"Unique test products: {len(test_product_ids)}")
    print(f"Overlapping product IDs: {overlap}")
    assert overlap == 0, "Data leakage detected! Product IDs overlap between train and test."

    print("\n--- MODEL & BASELINE METRICS ---")
    # Baseline
    train_mean = y_train.mean()
    baseline_preds = np.full(len(y_test), train_mean)
    baseline_mae = mean_absolute_error(y_test, baseline_preds)
    baseline_rmse = np.sqrt(mean_squared_error(y_test, baseline_preds))

    print("Training XGBRegressor...")
    model = train_model(X_train, y_train)

    print("Evaluating...")
    mae, rmse, _ = evaluate_model(model, X_test, y_test)

    rel_mae_imp = (baseline_mae - mae) / baseline_mae * 100
    rel_rmse_imp = (baseline_rmse - rmse) / baseline_rmse * 100

    print(f"Baseline MAE: {baseline_mae:.4f}")
    print(f"Baseline RMSE: {baseline_rmse:.4f}")
    print(f"XGBoost MAE: {mae:.4f}")
    print(f"XGBoost RMSE: {rmse:.4f}")
    print(f"Relative MAE improvement: {rel_mae_imp:.2f}%")
    print(f"Relative RMSE improvement: {rel_rmse_imp:.2f}%")

    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "xgboost_pricing_model.joblib")
    joblib.dump(model, model_path)

    feature_names_path = os.path.join(model_dir, "feature_names.json")
    with open(feature_names_path, "w") as f:
        json.dump(FEATURES, f, indent=2)

    print("\n--- ARTIFACTS ---")
    print(f"Model artifact saved to: {model_path}")
    print(f"Feature names saved to: {feature_names_path}")


if __name__ == "__main__":
    run_pipeline()
