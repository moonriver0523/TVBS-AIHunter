# AI 代理入口

本專案的流程總索引在 [`README.md`](README.md)，子系統全貌見 [`common/12-子系統地圖.md`](common/12-子系統地圖.md)（一條規則不等於一個子系統；同一個動作常橫跨 `reuters/`／`ap/`／`cnn/` 多份文件）。處理任何「自動寫稿(SOT)」「自動寫稿(CTV)」或「自動寫稿(準連)」任務前，除讀取 [`common/06-auto-script-sot.md`](common/06-auto-script-sot.md)／[`cnn/01-auto-script-writing.md`](cnn/01-auto-script-writing.md)／[`common/16-auto-script-junlian.md`](common/16-auto-script-junlian.md) 外，**必須先讀取** [`common/auto-script-learning/INDEX.md`](common/auto-script-learning/INDEX.md)。

⚠️ **稿名結尾是「準」字（例如 `渡輪起火19準`、`挾持巴士15準`）就是準連**，走 [`common/16-auto-script-junlian.md`](common/16-auto-script-junlian.md)，**不要套 SOT 的【主標題】【次標題】結構**。準連以搶時效為核心：**不跑 `validate_sot.py`（也不要土炮替代腳本）、不補 AP 照片**，字數與秒數交由人工把關。

## 自動寫稿的持續校稿機制

使用者會提供「AI 初稿」與「使用者修改稿」進行比對。這不是一次性評論，而是自動寫稿流程的正式回饋來源。代理必須：

1. 保留案例索引與差異摘要。
2. 萃取可重複的好做法，依 `NEW / REPEATED / CONFIRMED / PROMPT / RETIRED` 標示成熟度。
3. 區分「通用規則、風格偏好、單篇判斷」，不可把單篇創意直接寫成鐵則。
4. 只有 `PROMPT` 規則會直接約束自動寫稿；候選規則仍須在適合的稿件中優先評估。
5. 每次更動規則、Prompt 或成熟度，都同步更新學習索引與變更紀錄，讓後續代理可追溯。

不得只在對話中聲稱已學習，卻未留下可供其他代理讀取的專案紀錄。
