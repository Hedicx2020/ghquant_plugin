import pandas as pd, os

root = os.path.expanduser("~/local_data")
comp = pd.read_parquet(os.path.join(root, "ashare_index_components.parquet"),
                       columns=["index_code", "stock_code", "in_date", "out_date"])

# 候选大盘蓝筹指数（DJIA 对标），测各自成分记录数 + 2016-01-01 时点成分数
cands = {
    "000016.SH": "上证50",
    "000010.SH": "上证180",
    "000903.SH": "中证100",
    "000300.SH": "沪深300(SH后缀)",
    "399300.SZ": "沪深300(已知可用)",
    "000905.SH": "中证500",
}
as_of = pd.Timestamp("2016-01-01")
L = []
for code, name in cands.items():
    sub = comp[comp["index_code"].astype(str) == code]
    n_rows = len(sub)
    if n_rows:
        ind = pd.to_datetime(sub["in_date"], errors="coerce")
        outd = pd.to_datetime(sub["out_date"], errors="coerce")
        n_asof = int(((ind <= as_of) & (outd.isna() | (outd > as_of))).sum())
    else:
        n_asof = 0
    L.append(f"CAND {code} {name}: rows={n_rows} asof2016={n_asof}")

with open("/Users/hedi/report_reproduce/output/r001_signature_transformer_allocation/results/_cands.txt", "w") as f:
    f.write("\n".join(L) + "\n")
print("CANDS_DONE", len(L))
