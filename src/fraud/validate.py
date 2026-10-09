"""Validate a BAF-shaped DataFrame before training. Errors never contain data values."""

import logging

import pandas as pd
import pandera.pandas as pa

from fraud.schema import BINARY_COLS, CATEGORICAL_COLS, NUMERIC_COLS, TARGET, TIME_COL

logger = logging.getLogger(__name__)


def build_schema() -> pa.DataFrameSchema:
    columns = {
        col: pa.Column(dtype, pa.Check.isin([0, 1]) if col in BINARY_COLS else None)
        for col, dtype in NUMERIC_COLS.items()
    }
    for col, levels in CATEGORICAL_COLS.items():
        columns[col] = pa.Column(str, pa.Check.isin(levels))
    columns[TARGET] = pa.Column("int64", pa.Check.isin([0, 1]))
    columns[TIME_COL] = pa.Column("int64", pa.Check.ge(0))
    # strict: no extra columns. Columns are non-nullable by default.
    return pa.DataFrameSchema(columns, strict=True)


SCHEMA = build_schema()


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Return df if it matches SCHEMA, else raise ValueError with per-check failure counts."""
    try:
        SCHEMA.validate(df, lazy=True)  # lazy: collect every failure, not just the first
    except pa.errors.SchemaErrors as err:
        # failure_cases holds the offending values: report only column, check and count.
        cases = err.failure_cases.copy()
        # Missing/extra column errors have no column; their "value" is a column name (schema info).
        by_name = cases["check"].isin(["column_in_schema", "column_in_dataframe"])
        cases.loc[by_name, "column"] = cases.loc[by_name, "failure_case"]
        counts = cases.groupby(["column", "check"], dropna=False).size()
        lines = [f"  {col}: {check} ({n} failing)" for (col, check), n in counts.items()]
        # `from None` drops the original exception, whose message includes data values.
        raise ValueError("Data validation failed:\n" + "\n".join(lines)) from None
    logger.info("Validated %d rows x %d columns", *df.shape)
    return df
