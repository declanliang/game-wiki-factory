# Game Wiki 站点模板

这是 `game-wiki-factory` 内置的干净 Next.js Wiki 模板。编排器把模板同步到 `Games/<game-slug>/` 根目录；该目录本身就是可推送 GitHub、可部署 Vercel 的网站项目。

## 唯一输入契约

```text
intake/
├─ site-identity.json
├─ site-content.json
├─ site-content.es.json
├─ site-content.de.json
├─ site-content.fr.json
├─ site-content.ja.json
├─ site-content.ko.json
├─ site-plan.json
├─ hero.<ext>
├─ favicon/
└─ articles/
   ├─ en/<category>/*.mdx
   ├─ es/<category>/*.mdx
   ├─ de/<category>/*.mdx
   ├─ fr/<category>/*.mdx
   ├─ ja/<category>/*.mdx
   └─ ko/<category>/*.mdx
```

`site-plan.json` 是语言、分类、顺序和发布状态的唯一事实源。模板不会从 `content/en` 反推分类，也不会用正则修改 TypeScript 配置。六语言固定为 `en/es/de/fr/ja/ko`。

## 生成站点

```powershell
npm ci
npm run launch:site
```

流水线依次执行：

1. 校验 intake、六语言和 published 分类。
2. 应用身份、首页文案和素材。
3. 清空生成的 `content/`，从 intake 幂等导入文章。
4. 将 intake site-plan 复制为 `src/config/site-plan.json`。
5. 从 site-plan 生成导航、分类标题和语言配置。
6. 生成精选文章并运行 TypeScript、配置、生产构建验证。

调试时可跳过最终 build，但仍执行全部导入与契约检查：

```powershell
npm run launch:site -- --skip-build
```

## 常用检查

```powershell
npm run check:intake
npm run validate:articles
npm run check:config
npx tsc --noEmit
npm run build
```

## 设计边界

- 本仓库不调用 LLM、不搜索、不翻译；上游必须提供成品。
- `src/config/site-plan.json` 是生成文件，来源只能是 `intake/site-plan.json`。
- `content/` 是生成投影，每次 ingest 会先清空，防止旧游戏或已删除文章残留。
- site-plan 至少包含 1 个有真实关键词证据、最多 8 个 published 分类；不为数量生成 fallback 分类，每种语言必须交付相同文章树。
- `NEXT_PUBLIC_SITE_URL` 集中规范化：裸域名自动补 HTTPS，非法协议在构建前失败；`verify:deploy` 会检查线上 metadata，而不只检查 HTTP 200。
- 分类标签来自 site-plan 的六语言 `labels`，模板只负责机械使用。
- 具体游戏仓库必须提交 `intake/`；原始调研、cache 和日志位于被 Git 忽略的 `.gamewiki/`。
