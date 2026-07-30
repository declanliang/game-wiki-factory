# Adsterra 共享 Profile 与 Cloudflare Pages 环境变量合同

Game Wiki Factory 为新建的 Cloudflare Pages 站点自动配置统一 Adsterra shared profile。当前 profile 来源为 `animal-hospital-anomalies.wiki`，声明文件位于 `config/ads/animal-hospital-profile.json`；广告 custom domain 及完整 snippet 以该文件为准，页面组件不得硬编码来源域名或 placement ID。

Profile 中的 `adsterraPlacementId` 是 Adsterra 后台显示的数字广告位 ID；`invokeKey` 是 snippet 的 `invoke.js` URL（以及 Native 容器 ID）中的 32 位十六进制代码键。两者不是同一个标识。中央 JSON 尚未记录移动 Native 的数字广告位 ID，因此该项只声明已批准的 `invokeKey`，不会把代码键伪装成 placement ID。

共享 snippet 允许提交到 Factory 仓库，但只能由发布器读取、规范化并转换为服务端环境变量。Cloudflare API token、账户 ID 之外的密钥和部署凭据仍必须来自根 `.env`、CI secret 或其他安全凭据存储，禁止提交、打印或复制到游戏仓库。

## 固定的 8 个变量

| 用途 | 模板格式 | 环境变量 | placement 约束 |
|---|---|---|---|
| Desktop Native | `nativeBanner` | `AD_NATIVE_BANNER_B64` | 独立 placement，后台布局 `4:1` |
| Mobile Native | `nativeBannerMobile` | `AD_NATIVE_BANNER_MOBILE_B64` | 独立 placement，后台布局 `1:1` |
| 728×90 Banner | `banner728x90` | `AD_BANNER_728X90_B64` | 728×90 |
| 300×250 Banner | `banner300x250` | `AD_BANNER_300X250_B64` | 300×250 |
| 468×60 Banner | `banner468x60` | `AD_BANNER_468X60_B64` | 468×60 |
| 160×600 Sidebar | `sidebar160x600` | `AD_SIDEBAR_160X600_B64` | 160×600 |
| 160×300 Sidebar | `sidebar160x300` | `AD_SIDEBAR_160X300_B64` | 160×300 |
| 320×50 Mobile Banner | `mobile320x50` | `AD_MOBILE_320X50_B64` | 320×50 |

不使用 `NEXT_PUBLIC_AD_*` 或不带 `_B64` 的变量。Native 尺寸由 Adsterra 后台 placement 决定，不能通过修改容器或复用同一个 placement 模拟桌面/移动布局。

## Profile 验证与转换

发布器在内存中对每个 placement 执行：

1. 统一换行为 LF 并去除首尾空白；
2. 验证存在完整 `<script>` 和 `invoke.js`；
3. Native 验证 invoke key 与容器 ID 一致；
4. 固定 Banner 验证 snippet 中的宽高与 profile 一致；
5. 按 UTF-8 转为标准、单行 Base64，并做逐字节 round-trip；
6. 确认 profile 恰好覆盖上述 8 个变量。

转换值不写入源码、日志、Job JSON、`.gamewiki` 或发布回执。日志和回执只允许列出变量名与 shared profile 名称。

## Cloudflare Pages provisioning

Factory 创建或续跑 Git-integrated Pages 项目时，在触发 Production Git deployment 前执行 provisioning：

- Preview：写入全部 8 个 `AD_*_B64`；
- Production：写入全部 8 个 `AD_*_B64` 和 `NEXT_PUBLIC_SITE_URL`；
- 广告变量使用 server-only `secret_text`；
- Preview 与 Production 独立配置；
- 环境变量修改后必须触发新的对应环境部署才会生效。

Cloudflare Pages 的项目 PATCH 对 `env_vars` 按变量名更新；只有显式把某个变量名提交为 `null` 才会删除该变量。Factory 的 PATCH 只包含自身管理的 8 个广告变量和 Production `NEXT_PUBLIC_SITE_URL`，不读取、重写或清空其他 Agent/运营者维护的变量。发布器会记录 PATCH 前已有的非受管变量名，随后重新读取项目并验证这些变量仍然存在；若 Cloudflare 返回结果违反该合同，发布事务会明确失败。

新项目设置 `preview_deployment_setting: "none"` 是有意行为。Factory 的发布输入只使用已批准的 Private GitHub `main`，不会自动创建或推送临时分支，因此默认不为任意非 main commit 消耗 Preview 构建。首次上线验收使用本次 Production deployment 自身唯一的 `*.pages.dev` deployment URL；它在绑定自定义域名前即可访问，并用于首页、metadata、sitemap、robots 和广告 API 检查。Preview 环境仍预先配置完整 8 个变量，供维护者将项目设置改为 `all`/自定义分支并推送非 main 分支时使用；该人工 Preview 流程不属于普通 Factory Job。

模板运行时提供：

- `/api/ads/availability`：返回 8 个格式的真实可用状态；缺失、无效 Base64 或空 HTML 均为 `false`；
- `/api/ads/<format>`：只接受白名单格式，解码后返回独立 HTML；不可用时返回 404。

接口响应保持 `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、严格 `Referrer-Policy` 和 CSP，不输出异常堆栈或变量内容。

## iframe 与响应式 Native

广告继续由主页面通过同源 iframe 请求 `/api/ads/<format>`。iframe 隔离第三方 DOM、CSS、全局变量和 hydration，但不设置 `sandbox`：线上验证表明 Adsterra 在 sandbox 中可能请求成功却不渲染。

Desktop/Mobile Native 必须先在客户端解析现有 `900px` 断点，再创建唯一 iframe：

- viewport 未确定：不创建任何 Native iframe，也不预留空白；
- desktop：只创建 `nativeBanner`，使用 `4:1` 容器；
- mobile：只创建 `nativeBannerMobile`，使用约 300×300 的 `1:1` 容器。

不得先加载桌面 Native 后用 CSS 隐藏，也不得产生两个 Native 请求。

## v1_0730 展示预算与区块隔离

环境变量和 shared profile 不变，页面只按以下预算消费它们：

- 顶部固定广告使用 `mobile320x50`，广告与导航均保持固定且背景不透明，二者不得重叠；
- 首页中段广告只能作为两个完整 section 之间的同级区块，不能插入 Featured 卡片网格；
- 分类页不显示首尾横幅；至少 4 张卡片时只在第 2 张卡片后显示一个响应式 Native；
- 文章桌面侧栏广告固定在左侧，不与右侧滚动条竞争空间；
- 文章内文广告只检查正文容器的直属段落，不进入 Callout、表格或其他嵌套结构；最后 4 个直属段落及最后 25% 正文区域禁止插入；
- 8–13 个直属段落最多 1 个内文广告，14–22 个最多 2 个，23 个及以上最多 3 个；
- 页面末尾不再叠加文章专属或分类专属广告组；全局 Footer 前只选择一个广告，桌面优先 728×90、回退 468×60，移动端使用 300×250。

模板未获得对应变量时继续零渲染、零占位。调整展示预算不需要修改 Cloudflare Pages 中的变量名或重新转换 snippet。

## 验收

1. 8 个格式的 availability 与 API 状态一致；未配置格式不创建 iframe或占位。
2. API 返回 HTML、`no-store`、`nosniff`，且 snippet 只存在于 iframe 文档。
3. 广告 iframe 不含任何 `sandbox` 属性。
4. 桌面只请求 4:1 Native，移动只请求 1:1 Native；首屏没有重复或 `(canceled)` Native 请求。
5. 固定 Banner/Sidebar 使用合同尺寸，不因父容器裁切。
6. 页面主 HTML和客户端 bundle 不含 Base64 值或 raw snippet。
7. 环境变量变更后完成新部署；不以 Adsterra 是否立即填充 creative 作为部署成功条件。
8. 首页 Featured、文章 Callout/表格和其他声明的排除区内没有广告 iframe；Footer 广告区最多一个 iframe。

历史站点不由本 Factory PR 修改。PR 合并后使用新模板和同一 provisioning 机制单独迁移，不提供缺少 Mobile Native 时复用 Desktop Native 的旧合同回退。
