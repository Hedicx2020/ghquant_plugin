# init（初始化）

`flow init <pdf> --slug <短名>` 一条命令做完：分配编号、建目录、PDF 转文本、算内容哈希、体检数据目录、过门禁。不派子 agent。

## G-IN-1

状态文件不合法。多半是手工改过 `state.json`。不要再手改：用 `flow status <id>` 看报错，必要时删掉这个刚建的案例目录重新 `flow init`。

## G-IN-2

目录骨架不全（`workspace/<id>/{spec,audit,iterations}`、`src/<id>`、`output/<id>/results`）。重新执行 `flow init`。

## G-IN-3、G-IN-4、G-IN-5、G-IN-6

PDF 没有转出文本，或页数对不上。常见原因：扫描件没有文字层、PDF 加密、文件损坏。内核记一条 `pdf_unparseable` 事件，`flow next` 返回 `init_incomplete`。交给人：换一份带文字层的 PDF（或先做 OCR）后重新 `flow init`。不要让提取者直接读图硬抄。

## pdf_duplicate

同一份 PDF（内容哈希相同）已经有案例。停在检查点由人选：`continue` 仍然新建，`abort` 终止这个新案例、改去续跑已有的。
