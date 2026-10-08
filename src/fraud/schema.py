"""Column schema of the BAF Base dataset (names, dtypes, category levels only; no data values)."""

TARGET = "fraud_bool"
TIME_COL = "month"

# Numeric feature columns -> dtype, as read by pd.read_csv from Base.csv.
NUMERIC_COLS = {
    "income": "float64",
    "name_email_similarity": "float64",
    "prev_address_months_count": "int64",
    "current_address_months_count": "int64",
    "customer_age": "int64",
    "days_since_request": "float64",
    "intended_balcon_amount": "float64",
    "zip_count_4w": "int64",
    "velocity_6h": "float64",
    "velocity_24h": "float64",
    "velocity_4w": "float64",
    "bank_branch_count_8w": "int64",
    "date_of_birth_distinct_emails_4w": "int64",
    "credit_risk_score": "int64",
    "email_is_free": "int64",
    "phone_home_valid": "int64",
    "phone_mobile_valid": "int64",
    "bank_months_count": "int64",
    "has_other_cards": "int64",
    "proposed_credit_limit": "float64",
    "foreign_request": "int64",
    "session_length_in_minutes": "float64",
    "keep_alive_session": "int64",
    "device_distinct_emails_8w": "int64",
    "device_fraud_count": "int64",
}

# Categorical feature columns -> allowed levels (string dtype in pandas).
CATEGORICAL_COLS = {
    "payment_type": ["AA", "AB", "AC", "AD", "AE"],
    "employment_status": ["CA", "CB", "CC", "CD", "CE", "CF", "CG"],
    "housing_status": ["BA", "BB", "BC", "BD", "BE", "BF", "BG"],
    "source": ["INTERNET", "TELEAPP"],
    "device_os": ["linux", "macintosh", "other", "windows", "x11"],
}

# Full column order of Base.csv.
COLUMNS = [
    "fraud_bool",
    "income",
    "name_email_similarity",
    "prev_address_months_count",
    "current_address_months_count",
    "customer_age",
    "days_since_request",
    "intended_balcon_amount",
    "payment_type",
    "zip_count_4w",
    "velocity_6h",
    "velocity_24h",
    "velocity_4w",
    "bank_branch_count_8w",
    "date_of_birth_distinct_emails_4w",
    "employment_status",
    "credit_risk_score",
    "email_is_free",
    "housing_status",
    "phone_home_valid",
    "phone_mobile_valid",
    "bank_months_count",
    "has_other_cards",
    "proposed_credit_limit",
    "foreign_request",
    "source",
    "session_length_in_minutes",
    "device_os",
    "keep_alive_session",
    "device_distinct_emails_8w",
    "device_fraud_count",
    "month",
]
