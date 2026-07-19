# Schema 说明

- `game-homepage-package.schema.json` 是设计阶段的统一审计包概念 Schema。
- 最终运行时使用 `../src/gamewiki_automation/schemas.py` 中的三套严格 Schema：
  - `RESEARCH_SCHEMA`
  - `HOMEPAGE_SCHEMA`
  - `MODULES_SCHEMA`
- `00首页信息.json` 与 `00首页模块.json` 为兼容原始网站模板的直接消费文件；不要拿统一审计包 Schema 单独验证这两个文件。
- 每次运行已经自动执行运行时 Schema，结果写入 `validation-report.json`。
