import json

import numpy as np
import pandas as pd
import pytest

from shelfguard.train_model import (
    FEATURES,
    TARGET,
    evaluate_model,
    split_data,
    train_model,
    validate_and_preprocess,
)


@pytest.fixture
def valid_data():
    return pd.DataFrame(
        {
            "product_id": ["P1", "P1", "P2", "P3", "P4"],
            "days_until_expiry": [1, 2, 3, 4, 5],
            "base_price": [10.0, 15.0, 20.0, 25.0, 30.0],
            "initial_quantity": [100, 200, 300, 400, 500],
            "daily_demand": [10, 20, 30, 40, 50],
            "discount_pct": [0.1, 0.2, 0.3, 0.4, 0.5],
            "extra_col": ["a", "b", "c", "d", "e"],
        }
    )


def test_required_columns_detected(valid_data):
    df, total, rejected = validate_and_preprocess(valid_data)
    assert total == 5
    assert rejected == 0


def test_missing_columns_fail(valid_data):
    df_invalid = valid_data.drop(columns=["days_until_expiry"])
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_and_preprocess(df_invalid)


def test_remaining_hours_calculated(valid_data):
    df, _, _ = validate_and_preprocess(valid_data)
    assert "remaining_hours" in df.columns
    assert list(df["remaining_hours"]) == [24, 48, 72, 96, 120]


def test_features_and_target():
    assert len(FEATURES) == 4
    assert FEATURES == ["remaining_hours", "base_price", "initial_quantity", "daily_demand"]
    assert "product_id" not in FEATURES
    assert TARGET == "discount_pct"


def test_invalid_data_rejected():
    df = pd.DataFrame(
        {
            "product_id": ["P1", "P2", "P3"],
            "days_until_expiry": [1, 2, "invalid"],
            "base_price": [10.0, 15.0, 20.0],
            "initial_quantity": [100, np.nan, 300],
            "daily_demand": [10, 20, 30],
            "discount_pct": [0.1, 0.2, 0.3],
        }
    )
    processed, total, rejected = validate_and_preprocess(df)
    assert total == 3
    assert rejected == 2
    assert len(processed) == 1


def test_predictions_clipped():
    class DummyModel:
        def predict(self, X):
            # Model predicts out-of-bound fractions (e.g., negative or > 0.70)
            return np.array([-0.10, 0.50, 0.80, 1.00])

    dummy_model = DummyModel()
    X_test = pd.DataFrame()
    y_test = np.array([0.0, 0.50, 0.70, 0.70])

    mae, rmse, preds = evaluate_model(dummy_model, X_test, y_test)
    assert list(preds) == [0.0, 0.50, 0.70, 0.70]


def test_grouped_split(valid_data):
    # valid_data has products P1, P2, P3, P4. P1 has 2 rows.
    # GroupShuffleSplit should ensure no overlap
    train_df, test_df = split_data(valid_data, test_size=0.2, random_state=42)
    train_products = set(train_df["product_id"])
    test_products = set(test_df["product_id"])
    assert len(train_products.intersection(test_products)) == 0


def test_model_artifact_save_load(tmp_path):
    import joblib

    X = pd.DataFrame(
        {
            "remaining_hours": [24, 48],
            "base_price": [10.0, 20.0],
            "initial_quantity": [100, 200],
            "daily_demand": [10, 20],
        }
    )
    y = pd.Series([0.1, 0.2])

    model = train_model(X, y)

    model_path = tmp_path / "model.joblib"
    joblib.dump(model, model_path)

    loaded_model = joblib.load(model_path)
    preds = loaded_model.predict(X)
    assert len(preds) == 2

    feature_names_path = tmp_path / "feature_names.json"
    with open(feature_names_path, "w") as f:
        json.dump(FEATURES, f)

    with open(feature_names_path, "r") as f:
        loaded_features = json.load(f)
    assert loaded_features == FEATURES


def test_pricing_engine_batch_and_overrides():
    from shelfguard.pricing_engine import (
        calculate_dynamic_discount_batch,
        calculate_single_discount,
    )

    class MockModel:
        def predict(self, df):
            return np.array([0.25, 0.40, 0.60])

    mock_model = MockModel()

    items = [
        {
            "remaining_hours": 120.0,
            "base_price": 100.0,
            "stock_quantity": 50,
            "daily_demand": 5,
            "expiry_status": "SAFE",
        },
        {
            "remaining_hours": 0.0,
            "base_price": 100.0,
            "stock_quantity": 50,
            "daily_demand": 5,
            "expiry_status": "EXPIRED",
        },
        {
            "remaining_hours": 3.0,
            "base_price": 100.0,
            "stock_quantity": 50,
            "daily_demand": 5,
            "expiry_status": "DONATION",
        },
    ]

    res = calculate_dynamic_discount_batch(mock_model, items)
    assert len(res) == 3

    # SAFE: uses ML model (0.25 -> 25% discount, final price = 75.0)
    assert res[0]["dynamic_discount_percent"] == 25.0
    assert res[0]["final_price"] == 75.0
    assert not res[0]["is_override"]

    # EXPIRED: overridden to N/A / 0 price
    assert res[1]["is_override"]
    assert res[1]["override_reason"] == "EXPIRED"
    assert res[1]["final_price"] == 0.0

    # DONATION: overridden to NGO Relief (100% discount)
    assert res[2]["is_override"]
    assert res[2]["override_reason"] == "NGO_DONATION"
    assert res[2]["dynamic_discount_percent"] == 100.0
    assert res[2]["final_price"] == 0.0

    # Single discount wrapper check
    s_res = calculate_single_discount(mock_model, 120.0, 100.0, 50, 5, "SAFE")
    assert s_res["dynamic_discount_percent"] == 25.0
    assert s_res["final_price"] == 75.0

