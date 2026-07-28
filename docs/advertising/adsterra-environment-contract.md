# Adsterra 原始代码到环境变量转换契约

本文档面向独立广告 Agent。Game Wiki Factory 和 OpenClaw 不执行本流程，不接收原始广告代码，也不修改任何托管平台的广告环境变量。

## 输入与安全边界

每个游戏站点使用自己在 Adsterra 创建的 ad units。广告 Agent 应直接从用户提供的私密文件读取原始 snippet，不把 snippet、Base64 值或完整脚本 URL写入聊天、Git、日志、Job JSON或 `.gamewiki`。

允许缺少任意广告位。只转换实际提供且验证通过的项；不能用其他尺寸代码代替。所有环境变量必须配置在 Production，建议使用 Secret/Sensitive 类型。

## 固定映射

| Adsterra 标题/尺寸 | 环境变量 | 模板格式 | 页面用途 |
|---|---|---|---|
| Native Banner | `AD_NATIVE_BANNER_B64` | `nativeBanner` | Hero 后、卡片流 |
| Banner 728×90 | `AD_BANNER_728X90_B64` | `banner728x90` | 桌面正文/页脚 |
| Banner 300×250 | `AD_BANNER_300X250_B64` | `banner300x250` | 移动端/正文 |
| Banner 468×60 | `AD_BANNER_468X60_B64` | `banner468x60` | 桌面页脚 |
| Banner 160×600 | `AD_SIDEBAR_160X600_B64` | `sidebar160x600` | 宽屏左侧 |
| Banner 160×300 | `AD_SIDEBAR_160X300_B64` | `sidebar160x300` | 宽屏右侧/文章栏 |
| Banner 320×50 | `AD_MOBILE_320X50_B64` | `mobile320x50` | 移动端顶部 |

不要创建 `NEXT_PUBLIC_AD_*`，也不要使用不带 `_B64` 的 `AD_*`。广告代码必须保持 server-only，不能进入静态 JavaScript bundle。

## 转换算法

对每一个广告位独立执行：

1. 保留 Adsterra 返回的完整 snippet，包括 `atOptions`、容器元素和所有 `<script>`；不要只提取 key 或 URL。
2. 把换行统一为 LF（`\n`），去除文件开头/末尾的空白，但不要改写 snippet 内部内容。
3. 按 UTF-8 编码为字节。
4. 使用标准 Base64 编码，不使用 Base64URL，不插入换行。
5. 把编码结果写入上表对应的唯一环境变量。

参考实现：

```python
import base64

normalized = raw_snippet.replace("\r\n", "\n").replace("\r", "\n").strip()
value = base64.b64encode(normalized.encode("utf-8")).decode("ascii")
```

PowerShell 可使用：

```powershell
$normalized = $rawSnippet.Replace("`r`n", "`n").Replace("`r", "`n").Trim()
$value = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($normalized))
```

转换后必须在内存中 Base64 解码并与规范化后的原文逐字节比较；不相等则禁止写入环境变量。

## 写入前验证

- Banner 的 `width` 和 `height` 必须与目标变量尺寸完全一致。
- `atOptions.key` 必须与外部 invoke script URL 中的 key 一致。
- Native Banner 的容器 ID 必须与 invoke script 指定的容器一致。
- 同一输入不能出现重复标题、重复尺寸或同一个 key 被错误分配给不同尺寸。
- snippet 必须属于目标游戏对应的 Adsterra app/domain；不要跨站复用。
- 不接受未知标题、拼写猜测、缺失 `<script>` 的残片或已经 Base64 编码过的输入。

## Cloudflare Pages

把变量写入目标 Pages 项目的 Production 环境。变量更新后创建一次新的 Production deployment；仅修改变量但不重新部署，不能视为完成。

模板在运行时访问：

- `/api/ads/availability`：返回七个广告位的布尔可用性。
- `/api/ads/<format>`：返回隔离广告 HTML；未配置或 Base64 无效时返回 404。

广告 iframe 是同源地址，并带 `sandbox`、`no-store`、CSP、严格 referrer policy 和 `nosniff`。变量不存在时客户端不会挂载 iframe，也不预留广告高度。

## Vercel

若历史站点仍部署在 Vercel，使用完全相同的七个变量名和值，作用域设为 Production，并触发新的 Production deployment。只有目标站点仍保留兼容的 `/api/ads/<format>` 服务端路由时才可配置；不要把 Cloudflare Pages Function 文件本身当作 Vercel Function。

## 完成验收

1. 未配置的格式：`/api/ads/<format>` 返回 404，页面 DOM 中没有对应 `data-ad-format` iframe或空白。
2. 已配置的格式：接口返回 200，`Content-Type` 为 HTML，`Cache-Control` 包含 `no-store`。
3. 接口响应中 `gamewiki-ad-start` 与 `gamewiki-ad-end` 之间的 snippet，经规范化后与原始输入一致。
4. 浏览器中广告脚本只存在于同源沙箱 iframe 内，不出现在主页面 HTML或客户端 bundle。
5. 桌面和移动布局没有因缺失广告产生空白；已配置固定尺寸 Banner 预留正确宽高，避免 CLS。
6. 不以 Adsterra 是否立即填充 creative 作为部署成功条件；新 ad unit 可能存在平台同步延迟。

最终报告只能列出：目标站点、已配置的变量名、部署 ID/URL、各格式 HTTP 状态和代码哈希。不得报告变量值或原始 snippet。
