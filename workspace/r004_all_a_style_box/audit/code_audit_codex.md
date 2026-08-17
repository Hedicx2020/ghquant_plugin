{
  "checkpoint": "code",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {
      "dimension": "公式逐要素对照",
      "result": "CDX-C-03, CDX-C-04"
    },
    {
      "dimension": "未来函数/前视检查",
      "result": "no_findings"
    },
    {
      "dimension": "数据对齐检查",
      "result": "CDX-C-01"
    },
    {
      "dimension": "config vs B类核对",
      "result": "no_findings"
    },
    {
      "dimension": "作弊模式排查(K1/K5/K6)",
      "result": "CDX-C-01, CDX-C-02"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "major",
      "category": "静默吞错",
      "location": "common/data_loader.py:28",
      "description": "get_data_root在发现.reproduce.json后，若文件不可读或JSON损坏会捕获异常并直接break，随后无告警回退到~/local_data；AllAStyleBoxConfig在模块导入时据此生成正式data_root，因此配置错误可被静默替换为另一套本地数据并继续产出结果，source_catalog只会记录回退后的路径而无法暴露原配置失败。",
      "suggestion": "仅在沿父目录完全找不到配置时允许默认回退；一旦发现配置文件却读取或解析失败，应抛出带配置路径的异常。若允许字段缺失回退，也应在run_log和source_catalog中显式登记fallback原因并要求调用方确认。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-02",
      "severity": "major",
      "category": "静默吞错",
      "location": "src/r004_all_a_style_box/main.py:113",
      "description": "artifact-tool子进程成功返回后，代码会收集warning/warn及missing a required sheetid等警告，但只把它们写入workbook_qa_manifest并继续返回成功；workbook_builder同样无条件声明inspect_key_range_before_export=true。由此，关键工作表inspect或渲染QA告警可以在正式链中未闭环而仍生成并验收XLSX，属于输出QA与实际执行解耦。",
      "suggestion": "把已知QA致命警告（至少缺失sheetId、inspect/render失败或空预览）升级为非零退出；对允许的非致命警告建立白名单。manifest中的QA布尔值应由实际成功记录计算，且主入口在返回工作簿路径前断言每个用户sheet均有非空inspect和preview。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-03",
      "severity": "minor",
      "category": "其他",
      "location": "src/r004_all_a_style_box/reporting.py:177",
      "description": "src内重新实现了最大回撤、绩效汇总、IC/RankIC及缩尾排名等通用统计，而common_signatures已列出common.utils.calculate_max_drawdown/performance_summary、common.backtest.calculate_ic/calculate_rank_ic等接口；这违反本仓禁止在src重复实现common能力的约定，并使相同指标可能与公共口径漂移。",
      "suggestion": "在保持plan冻结语义的前提下，把可直接等价的最大回撤、绩效和逐截面IC计算改为调用common接口；确需定制的分组包装仅保留编排逻辑，并用现有合成回归锁定迁移前后数值一致。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-04",
      "severity": "minor",
      "category": "其他",
      "location": "src/r004_all_a_style_box/reporting.py:945",
      "description": "templates/factor.md要求ic_distribution.png为IC直方图加正态拟合，但当前实现只绘制直方图和均值竖线，没有正态密度拟合曲线，正式图表合同未完整实现。",
      "suggestion": "用同一RankIC样本估计均值和标准差并叠加归一化正态密度曲线；零方差或有效样本不足时显式标注不可拟合，避免静默省略。",
      "confidence": "high"
    }
  ]
}
