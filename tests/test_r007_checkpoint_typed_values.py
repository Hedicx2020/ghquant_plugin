"""r007 checkpoint 混合审计值的可逆 typed JSON 回归。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.r007_cross_market_return_forecasting.config import DEFAULT_M5_CONFIG
from src.r007_cross_market_return_forecasting.data_pipeline import (
    CN_PRICE_REQUIRED_COLUMNS,
    CN_TRADE_REQUIRED_COLUMNS,
    CN_UNIT_CONTRACT,
    US_SOURCE_REQUIRED_COLUMNS,
    US_UNIT_CONTRACT,
    audit_loaded_market_panel,
    build_dual_market_universes,
    load_dual_market_sources,
)
from src.r007_cross_market_return_forecasting.main import (
    _CHECKPOINT_TYPED_VALUE_METADATA_KEY,
    CheckpointStore,
    _encode_checkpoint_typed_value,
)


def _actual_loaded_panel_audit() -> pd.DataFrame:
    config = DEFAULT_M5_CONFIG.m4.m3.pipeline
    us_universe, cn_universe = build_dual_market_universes(config)
    sources = load_dual_market_sources(
        us_universe["stock_code"].astype(str).tolist(),
        cn_universe["stock_code"].astype(str).tolist(),
        config=config,
    )
    return pd.concat(
        [
            audit_loaded_market_panel(
                sources.us_quotes,
                dataset_name="US_loaded_source_panel",
                key_columns=("stock_code", "date"),
                required_columns=US_SOURCE_REQUIRED_COLUMNS,
                unit_contract=US_UNIT_CONTRACT,
                expected_calendar=sources.us_calendar,
            ),
            audit_loaded_market_panel(
                sources.cn_quotes,
                dataset_name="CN_loaded_source_panel",
                key_columns=("stock_code", "date"),
                required_columns=tuple(
                    dict.fromkeys(
                        (*CN_PRICE_REQUIRED_COLUMNS, *CN_TRADE_REQUIRED_COLUMNS)
                    )
                ),
                unit_contract=CN_UNIT_CONTRACT,
                expected_calendar=sources.cn_calendar,
            ),
        ],
        ignore_index=True,
    )


class UnsupportedAuditValue:
    pass


class CheckpointTypedValuesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.actual_audit = _actual_loaded_panel_audit()

    def test_actual_75x7_loaded_panel_audit_round_trip(self) -> None:
        original = self.actual_audit
        self.assertEqual(original.shape, (75, 7))
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            path = store.write_frame("m1_loaded_panel_audit", original)
            reloaded = store.read_frame("m1_loaded_panel_audit")
            metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
            protocol = json.loads(
                metadata[_CHECKPOINT_TYPED_VALUE_METADATA_KEY].decode("utf-8")
            )

        self.assertEqual(reloaded.shape, (75, 7))
        self.assertEqual(
            [entry["name"] for entry in protocol["columns"]],
            ["actual", "expected"],
        )
        pd.testing.assert_frame_equal(
            reloaded[["dataset", "audit_type", "item", "status"]],
            original[["dataset", "audit_type", "item", "status"]],
        )
        for column in ("actual", "expected"):
            self.assertEqual(
                reloaded[column].map(_encode_checkpoint_typed_value).tolist(),
                original[column].map(_encode_checkpoint_typed_value).tolist(),
            )
        bool_row = next(
            index
            for index, value in original["actual"].items()
            if type(value) is bool
        )
        zero_float_row = next(
            index
            for index, value in original["actual"].items()
            if type(value) is float and value == 0.0
        )
        self.assertIs(type(reloaded.loc[bool_row, "actual"]), bool)
        self.assertIs(type(reloaded.loc[zero_float_row, "actual"]), float)
        self.assertIs(reloaded.loc[bool_row, "actual"], True)
        self.assertEqual(reloaded.loc[zero_float_row, "actual"], 0.0)

    def test_supported_scalar_nested_and_missing_types_round_trip(self) -> None:
        values = pd.Series(
            [
                True,
                7,
                1.25,
                "文本",
                pd.Timestamp("2021-05-05 09:30:00"),
                None,
                np.nan,
                pd.NA,
                [1, "x", None],
                {"b": 2, "a": [True, None]},
            ],
            dtype=object,
        )
        frame = pd.DataFrame({"mixed": values})
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            store.write_frame("supported", frame)
            reloaded = store.read_frame("supported")

        self.assertIs(type(reloaded.loc[0, "mixed"]), bool)
        self.assertIs(type(reloaded.loc[1, "mixed"]), int)
        self.assertIs(type(reloaded.loc[2, "mixed"]), float)
        self.assertIs(type(reloaded.loc[3, "mixed"]), str)
        self.assertIs(type(reloaded.loc[4, "mixed"]), pd.Timestamp)
        self.assertIsNone(reloaded.loc[5, "mixed"])
        self.assertTrue(np.isnan(reloaded.loc[6, "mixed"]))
        self.assertIs(reloaded.loc[7, "mixed"], pd.NA)
        self.assertEqual(reloaded.loc[8, "mixed"], [1, "x", None])
        self.assertEqual(
            reloaded.loc[9, "mixed"],
            {"a": [True, None], "b": 2},
        )

    def test_unknown_python_type_fails_before_checkpoint_replace(self) -> None:
        frame = pd.DataFrame(
            {
                "mixed": pd.Series(
                    [UnsupportedAuditValue(), "known"],
                    dtype=object,
                )
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            with self.assertRaises(TypeError):
                store.write_frame("unknown", frame)
            self.assertFalse(store.frame_path("unknown").exists())
            self.assertFalse(
                store.frame_path("unknown")
                .with_name("unknown.parquet.part")
                .exists()
            )

    def test_corrupted_typed_cell_fails_fast_on_read(self) -> None:
        frame = pd.DataFrame(
            {"mixed": pd.Series([True, 0.0], dtype=object)}
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            path = store.write_frame("corrupted_cell", frame)
            table = pq.read_table(path)
            column_index = table.schema.get_field_index("mixed")
            corrupted = table.set_column(
                column_index,
                table.schema.field(column_index),
                pa.array(
                    ["{broken", table["mixed"][1].as_py()],
                    type=table.schema.field(column_index).type,
                ),
            )
            pq.write_table(corrupted, path)
            with self.assertRaises(ValueError):
                store.read_frame("corrupted_cell")

    def test_corrupted_or_unknown_metadata_version_fails_fast(self) -> None:
        frame = pd.DataFrame(
            {"mixed": pd.Series([True, 0.0], dtype=object)}
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            path = store.write_frame("corrupted_metadata", frame)
            table = pq.read_table(path)
            metadata = dict(table.schema.metadata or {})
            payload = json.loads(
                metadata[_CHECKPOINT_TYPED_VALUE_METADATA_KEY].decode("utf-8")
            )
            payload["version"] = 999
            metadata[_CHECKPOINT_TYPED_VALUE_METADATA_KEY] = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            pq.write_table(table.replace_schema_metadata(metadata), path)
            with self.assertRaises(ValueError):
                store.read_frame("corrupted_metadata")

    def test_legacy_non_encoded_parquet_remains_readable(self) -> None:
        legacy = pd.DataFrame(
            {
                "label": pd.Series(["a", "b"], dtype=object),
                "value": [1.0, 2.0],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            legacy.to_parquet(store.frame_path("legacy"), index=False)
            reloaded = store.read_frame("legacy")
        pd.testing.assert_frame_equal(reloaded, legacy, check_dtype=False)

    def test_ordinary_numeric_frame_is_not_encoded_or_changed(self) -> None:
        frame = pd.DataFrame(
            {
                "integer": pd.Series([1, 2], dtype="int64"),
                "floating": pd.Series([1.5, 2.5], dtype="float64"),
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = CheckpointStore(Path(temporary))
            path = store.write_frame("numeric", frame)
            metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
            reloaded = store.read_frame("numeric")
        self.assertNotIn(_CHECKPOINT_TYPED_VALUE_METADATA_KEY, metadata)
        pd.testing.assert_frame_equal(reloaded, frame)


if __name__ == "__main__":
    unittest.main()
