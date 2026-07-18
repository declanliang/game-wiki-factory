将以下内容从英文翻译为 $language_name。

重要规则：
1. 将所有文本内容自然、流畅地翻译为 $language_name
2. 保持所有 Markdown 格式不变（标题 ##、列表 -、加粗 **、链接 []、表格等）
3. 保持所有 HTML 标签不变
4. 保持所有 URL 不变
5. 保持文章结构和长度一致
6. 表格单元格不要用空格填充对齐 `|` 列——GFM 表格不需要视觉对齐，不要手动补空格
7. category、date 等元数据字段不需要你处理，由系统自动保留，不要在你的输出里提及它们
8. 正文中可能包含 `<Callout type="info">...</Callout>`（或 type="tip"/"warning"/"success"）这样的提示框标签——标签本身、`type="..."` 的值必须保持原样（不翻译、不改动大小写），但标签内部的文字内容（包括加粗的标题和列表项）要正常翻译成 $language_name

目标语言：$language_name ($lang_code)

标题（英文原文，请翻译为 $language_name）：
$title

描述（英文原文，请翻译为 $language_name，SEO 摘要，最长 155 字符）：
$description

正文（英文原文，请翻译为 $language_name）：
$body

## 输出格式

输出恰好三部分，按此顺序，前后不要有任何其他文字：

1. 一行以 `TITLE:` 开头，后面跟翻译后的标题。纯文本——不要加引号，不要用 JS/JSON 语法。
2. 一行以 `DESCRIPTION:` 开头，后面跟翻译后的描述。纯文本——不要加引号。
3. 一行只包含 `BODY:`，然后从下一行开始输出翻译后的正文 Markdown。

不要自己输出 JS/JSON 格式的 metadata 代码块——标题和描述会由系统组装进页面 metadata，不需要你处理这部分语法。不要把任何部分包裹在代码块（```）里。不要使用 YAML frontmatter。不要添加任何解释或说明。
