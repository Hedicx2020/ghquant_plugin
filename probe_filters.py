"""探 ST/停牌/上市日 三张过滤表的 schema + 样例，落项目文件。"""
import pyarrow.parquet as pq, os

root = os.path.expanduser("~/local_data")
tables = ["ashare_stock_st", "ashare_stock_suspend", "ashare_stock"]
L = []
for name in tables:
    p = os.path.join(root, f"{name}.parquet")
    pf = pq.ParquetFile(p)
    cols = [f.name for f in pf.schema_arrow]
    L.append(f"=== {name} === rows={pf.metadata.num_rows}")
    L.append("COLS: " + ", ".join(cols))
    batch = next(pf.iter_batches(batch_size=2))
    df = batch.to_pandas()
    for c in df.columns:
        L.append(f"   {c}: {list(df[c].astype(str).values)}")
    L.append("")
open("/Users/hedi/report_reproduce/_filters_schema.txt", "w").write("\n".join(L))
print("PROBE_OK lines", len(L))
