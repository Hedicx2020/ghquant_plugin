"""r007 美股逐证券缓存与 merged panel 的语义 schema 定向回归。"""

from __future__ import annotations

import json
import unittest

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.r007_cross_market_return_forecasting.config import DEFAULT_CONFIG
from src.r007_cross_market_return_forecasting.data_pipeline import (
    US_SOURCE_REQUIRED_COLUMNS,
    _assert_semantic_arrow_schema_equal,
    _file_sha256,
)


class ArrowSchemaContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = pa.schema(
            [
                pa.field(
                    "a",
                    pa.int64(),
                    nullable=False,
                    metadata={b"unit": b"count"},
                ),
                pa.field("b", pa.string(), nullable=True),
            ],
            metadata={b"pandas": b"writer-A", b"semantic": b"v1"},
        )

    def assert_schema_rejected(self, actual: pa.Schema) -> None:
        with self.assertRaises(ValueError):
            _assert_semantic_arrow_schema_equal(
                actual,
                self.expected,
                context="定向负例",
            )

    def test_only_pandas_container_metadata_difference_is_ignored(self) -> None:
        actual = pa.schema(
            list(self.expected),
            metadata={b"pandas": b"writer-B", b"semantic": b"v1"},
        )
        _assert_semantic_arrow_schema_equal(
            actual,
            self.expected,
            context="仅 pandas metadata 差异",
        )

    def test_missing_column_is_rejected(self) -> None:
        self.assert_schema_rejected(
            pa.schema([self.expected.field("a")], metadata=self.expected.metadata)
        )

    def test_column_order_change_is_rejected(self) -> None:
        self.assert_schema_rejected(
            pa.schema(
                [self.expected.field("b"), self.expected.field("a")],
                metadata=self.expected.metadata,
            )
        )

    def test_arrow_type_change_is_rejected(self) -> None:
        self.assert_schema_rejected(
            pa.schema(
                [
                    pa.field(
                        "a",
                        pa.int32(),
                        nullable=False,
                        metadata={b"unit": b"count"},
                    ),
                    self.expected.field("b"),
                ],
                metadata=self.expected.metadata,
            )
        )

    def test_nullability_change_is_rejected(self) -> None:
        self.assert_schema_rejected(
            pa.schema(
                [
                    pa.field(
                        "a",
                        pa.int64(),
                        nullable=True,
                        metadata={b"unit": b"count"},
                    ),
                    self.expected.field("b"),
                ],
                metadata=self.expected.metadata,
            )
        )

    def test_field_metadata_change_is_rejected(self) -> None:
        self.assert_schema_rejected(
            pa.schema(
                [
                    pa.field(
                        "a",
                        pa.int64(),
                        nullable=False,
                        metadata={b"unit": b"currency"},
                    ),
                    self.expected.field("b"),
                ],
                metadata=self.expected.metadata,
            )
        )

    def test_real_mmm_cache_and_merged_slice(self) -> None:
        config = DEFAULT_CONFIG.us_yahoo
        manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
        entry = manifest["entries"]["MMM"]
        security_path = config.cache_dir / entry["file"]
        self.assertEqual(_file_sha256(security_path), entry["file_sha256"])
        _assert_semantic_arrow_schema_equal(
            pq.ParquetFile(security_path).schema_arrow,
            pq.ParquetFile(config.merged_panel_path).schema_arrow,
            context="真实 MMM 与 merged panel",
        )
        columns = list(US_SOURCE_REQUIRED_COLUMNS)
        security = (
            pd.read_parquet(security_path, columns=columns)
            .sort_values(["stock_code", "date"])
            .reset_index(drop=True)
        )
        self.assertEqual(len(security), int(entry["rows"]))
        merged = pd.read_parquet(
            config.merged_panel_path,
            columns=columns,
            filters=[("stock_code", "==", "MMM")],
        )
        merged = merged.sort_values(
            ["stock_code", "date"]
        ).reset_index(drop=True)
        pd.testing.assert_frame_equal(
            merged,
            security,
            check_dtype=False,
            check_like=False,
        )


if __name__ == "__main__":
    unittest.main()
