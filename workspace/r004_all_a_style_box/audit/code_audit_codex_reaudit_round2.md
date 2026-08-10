{
  "checkpoint": "code",
  "verdict": "pass",
  "dimensions_checked": [
    {
      "dimension": "公式逐要素对照",
      "result": "no_findings；最大回撤口径显式固定调仓前期初净值1.0，common三组反例与独立基线最大误差为0，负首期回归由旧口径0.0纠正为-0.1"
    },
    {
      "dimension": "未来函数/前视检查",
      "result": "no_findings"
    },
    {
      "dimension": "数据对齐检查",
      "result": "no_findings"
    },
    {
      "dimension": "config vs B类核对",
      "result": "no_findings"
    },
    {
      "dimension": "作弊模式排查(K1/K5/K6)",
      "result": "no_findings；CDX-C-05已核销：空columns、空rows、仅类别无有限数值三种声明图表均returncode=1且不生成manifest；正常五工作簿的declared、expected、actual、manifest charts、OOXML expected与OOXML actual均逐本为1，Node及Python warning均为0，篡改actual计数后Python二次断言明确拒绝"
    }
  ],
  "findings": []
}
