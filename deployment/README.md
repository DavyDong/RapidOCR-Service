# RapidOCR 本地运行与 SAP BTP 部署

[项目介绍（中文）](../README-CN.md) · [English overview](../README.md) · [第三方组件与许可](../THIRD_PARTY_NOTICES.md)

本目录在上游 RapidOCR Python 源码之外提供图片 / PDF 上传页面和统一 HTTP API。使用当前仓库 `python/rapidocr`，默认 PP-OCRv6 检测/识别模型、PP-OCRv4 方向分类模型及 ONNX Runtime CPU 后端。PDF 使用 PyMuPDF 解析和渲染，与图片共用一个 OCR 引擎。

## 本地运行（Windows / PowerShell）

在仓库根目录执行：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.\.venv\Scripts\python.exe -m deployment.engine
$tokenInput = Read-Host 'ACCESS_TOKEN' -AsSecureString
$env:ACCESS_TOKEN = [System.Net.NetworkCredential]::new('', $tokenInput).Password
.\scripts\restart-local.ps1
```

访问 <http://127.0.0.1:8765>。再次执行 `restart-local.ps1` 会仅重启由该脚本记录、且路径和启动命令匹配的本项目进程。指定其他端口：`./scripts/restart-local.ps1 -Port 8766`。

服务进程信息和日志位于 `.runtime/`，虚拟环境为 `.venv/`。页面支持图片 / PDF 示例、按页查看、文字复制和 JSON 下载。上传文件不持久保存，multipart 处理可能使用临时文件，请求结束后关闭。一个实例串行处理文件，繁忙时返回 HTTP 429。应用不会自动读取 `.env`；环境变量需要在启动进程前设置。

<a id="local-bash"></a>

## 本地运行（Linux / macOS / Bash）

安装 Python 3.12 和 uv，在仓库根目录执行：

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m deployment.engine
read -r -s -p 'Choose ACCESS_TOKEN: ' ACCESS_TOKEN
export ACCESS_TOKEN
export OCR_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
.venv/bin/python -m uvicorn deployment.app:app --host 127.0.0.1 --port 8765 --workers 1 --limit-concurrency 16
```

本集成已实测 Windows 和 BTP Linux；上述 Bash 命令是等价的手动启动方式，不代表已单独完成 macOS 验证。首次下载依赖与模型需要联网，之后 OCR 使用本地模型。

### PDF 处理策略与限制

- 按文件内容识别类型，不依赖扩展名或客户端 MIME；支持 PNG、JPEG、WebP、BMP、单帧 TIFF、PDF。
- 纯文字 PDF 页面直接提取原生文字；无文字、乱码替代字符、含图片的混合页、含批注或表单控件的页面渲染后 OCR，避免只提取页脚而遗漏扫描正文。`force_ocr=true` 可让全部 PDF 页面使用 OCR，适合异常文字层。复杂布局和阅读顺序需结合实际文档核对。
- 单文件最多 10 MB，图片最多 2400 万像素，PDF 最多 20 页。渲染目标 200 DPI，按比例限制到每页最多 400 万像素、最长边 3000 像素，逐页处理。低清晰度原稿和缩小后的细小文字会影响 OCR。
- PDF 在每页处理前后检查 45 秒预算；单页渲染 / OCR 调用无法中途取消，因此这不是严格的请求超时。超出预算返回 422，不返回不完整结果；请拆分长文件。
- 需要密码的 PDF 返回 422，请先解密；多帧图片返回 422，请拆分或转换为 PDF，避免丢页。空白页保留页号并返回空文字。

参考 [RapidOCRPDF 源码](https://github.com/RapidAI/RapidOCRPDF/blob/main/rapidocr_pdf/main.py) 的分流思路。该项目当前类名是 `RapidOCRPDF`，没有示例中的 `PDFExtracter(ocr_engine=...)` 接口；它会创建自己的 OCR 引擎，因此本服务直接使用同一 PDF 底层库并复用现有引擎。当前 RapidOCR 返回结果对象，也不是旧版 `res, cost` 元组。

识别接口必须使用环境变量 `ACCESS_TOKEN` 中的令牌。网页在识别前需要手动输入令牌，仅保留在当前页面，不写入浏览器存储，也不会由服务器输出到网页。页面、健康检查和 API 文档公开可访问；未配置服务端令牌时拒绝所有识别请求。

## API

- `GET /health`：模型完成预热后才开放 HTTP 服务。
- `GET /docs`：OpenAPI 交互文档，点击 **Authorize** 并输入令牌值（不加 `Bearer` 前缀）。
- `POST /api/ocr` 或 `POST /ocr/invoice`：同一个处理函数和鉴权要求。必须携带 `Authorization: Bearer <ACCESS_TOKEN>`，multipart 表单字段 `file`，可选字段 `force_ocr`（默认 `false`）。别名不代表发票字段结构化：两者都提取文字与位置，不推断税额、供应商等业务字段。

```powershell
$baseUrl = 'http://127.0.0.1:8765' # 云端使用自己部署后的 URL。
curl.exe -H "Authorization: Bearer $env:ACCESS_TOKEN" -F "file=@deployment/sample.jpg" "$baseUrl/api/ocr"
curl.exe -H "Authorization: Bearer $env:ACCESS_TOKEN" -F "file=@deployment/sample.pdf" "$baseUrl/ocr/invoice"
# 强制 OCR 所有 PDF 页面：额外添加 -F "force_ocr=true"
```

Linux/macOS Bash 使用 `-H "Authorization: Bearer $ACCESS_TOKEN"`；PowerShell 使用上面的 `$env:ACCESS_TOKEN`。BTP 上配置的环境变量不会自动设置到调用方电脑。

响应字段：

| 字段 | 含义 |
| --- | --- |
| `type` / `pages` | `image` 或 `pdf`；实际页数，包含空白页 |
| `text` / `lines` | 全文（页面间两个换行）和全部文字行 |
| `page_results` | 逐页 `page_number`、`method`（`native` / `ocr`）、`text`、`lines`、`width`、`height`、`coordinate_unit`、`elapsed_seconds` |
| 文字行 | `text`、`confidence`（原生文字为 `null`）、四点 `box`、从 1 开始的 `page_number` |
| `elapsed_seconds` | 整个文件的提取耗时，不含上传时间 |
| `width` / `height` | 图片保留原有顶层尺寸；PDF 顶层为 `null`，尺寸在各页中 |

图片坐标单位为像素；PDF 坐标单位为 point（1/72 英寸），原点位于旋转后可见页面左上角。原生文字框与 OCR 框采用同一 PDF 坐标系。旧图片响应的 `text`、`lines`、尺寸和耗时字段保留；不使用参考代码中的 `ocr_result` / `cost_sec` 字段。

接口要求 `Content-Length`（浏览器 FormData、curl 和常规 HTTP 客户端会自动发送）。无文字返回成功和空结果；缺少/错误令牌返回 401，服务未配置令牌返回 503，非法文件返回 400，不支持的图片格式返回 415，文件 / 页数超限返回 413，需要解密 / 拆分的文件返回 422，繁忙返回 429。令牌校验先于上传文件解析和 OCR 推理。

## SAP BTP Cloud Foundry

每位部署者使用自己的 BTP 子账户、Cloud Foundry API、组织和空间；从 BTP Cockpit 的 Cloud Foundry 环境页面获取这些值。需具备应用部署权限，并有足够的内存、磁盘和路由配额。

已验证配置为 Python 3.12、`python_buildpack`、`cflinuxfs5`，1 个实例、2 GB 内存、2 GB 磁盘。可用 stack/buildpack 以目标 CF 环境为准。以下命令使用 CF CLI v8 与 PowerShell。

<a id="btp-first-deployment"></a>

### 首次部署自己的实例

先完成前面的依赖安装和模型预热，再登录自己的环境。尖括号中的内容须替换为自己的实际值：

```powershell
cf login -a '<YOUR_CF_API_ENDPOINT>' --sso
cf target -o '<YOUR_ORG>' -s '<YOUR_SPACE>'
cf target
cf domains
cf stacks
cf buildpacks
Copy-Item manifest.example.yml manifest.local.yml
```

编辑 `manifest.local.yml`：`name` 是自己选择的应用名，默认 `rapidocr`。示例使用 `random-route: true`，由 CF 分配可用路由；如需简洁域名，可删除 `random-route` 并添加属于自己且未被占用的 `routes`。仓库的 `manifest.yml` 是维护者现有实例配置，不应直接复用其中路由。

确认目标空间中没有同名应用后，创建并上传这个新应用，暂不启动：

```powershell
$appName = 'rapidocr' # 必须与 manifest.local.yml 的 name 一致。
cf push -f manifest.local.yml --no-start
```

然后到 BTP Cockpit 中该应用的 **User-Provided Variables / 用户环境变量**，新增 `ACCESS_TOKEN` 并设置自己的随机长令牌。令牌只配置在环境中，不写入清单或 Git。再启动应用：

```powershell
cf start $appName
cf app $appName
```

`cf start` 会为尚未完成 staging 的包安装依赖并启动。`cf app` 显示实例状态与实际路由；用该路由打开网页或 `/docs`。健康检查成功只说明模型就绪，仍需带令牌调用识别接口验证。BTP 中的变量不会自动设置到本地终端。

### 后续部署

已配置令牌的应用使用助手脚本，避免普通 `cf push` 清单差异输出泄露令牌：

```powershell
cf target # 确认仍然是自己的组织和空间。
.\scripts\deploy-btp.ps1 -AppName $appName -Manifest manifest.local.yml
cf app $appName
```

维护者现有实例可继续使用 `./scripts/deploy-btp.ps1` 的默认值。脚本只更新已有应用，并要求已配置 `ACCESS_TOKEN`；它不是首次创建应用的命令。若只修改 BTP 环境中的令牌，执行 `cf restart $appName` 使新值生效。

模型预热下载到 `models/` 的文件随应用上传，云端启动无需再次下载；模型不纳入 Git。`.cfignore` 排除虚拟环境、Git 元数据、日志、测试和本地配置。源码许可见 [LICENSE](../LICENSE)，模型许可见 [python/MODEL_LICENSES.md](../python/MODEL_LICENSES.md)，PDF 依赖的许可见 [第三方组件说明](../THIRD_PARTY_NOTICES.md)。`requirements.txt` 锁定依赖，`Procfile` 使用平台分配的 `PORT`。

配置项：

| 名称 | 用途 |
| --- | --- |
| `ACCESS_TOKEN` | 必填；请求的 Bearer Token 必须匹配，未配置返回 503 |
| `OCR_THREADS` | OCR 引擎线程数，默认 2 |
| `OMP_NUM_THREADS` / `OPENBLAS_NUM_THREADS` | 数值计算线程数，示例设置为 2 |
| `PYTHONUNBUFFERED` | 即时输出日志，示例设置为 1 |
| `PORT` | CF 自动提供；本地使用启动命令中的端口 |

CF 行为依据：[部署清单属性](https://docs.cloudfoundry.org/devguide/deploy-apps/manifest-attributes.html)、[cf start](https://cli.cloudfoundry.org/en-US/v8/start.html)。

<a id="verification"></a>

## 验证

```powershell
uv pip install --python .venv\Scripts\python.exe pytest httpx
.\.venv\Scripts\python.exe -m pytest deployment/tests -q
.\.venv\Scripts\python.exe scripts/smoke-test.py
# 将 YOUR_APP_ROUTE 替换为 cf app 显示的实际路由。
.\.venv\Scripts\python.exe scripts/smoke-test.py https://YOUR_APP_ROUTE
```

测试使用真实 OCR 模型检查图片、原生 PDF、扫描 PDF、同页混合内容、空白页、旋转坐标、强制 OCR、加密/损坏 PDF、渲染/页数/时间限制、异常后的锁释放、Bearer 校验及未配置令牌时的拒绝行为。冒烟测试从当前进程环境变量读取 `ACCESS_TOKEN`，检查两个统一入口并确认公开响应不含令牌，不输出令牌。

在新终端运行冒烟测试前，先用前面的安全输入方式设置本地 `ACCESS_TOKEN`，值须与待测试服务一致。Linux/macOS 将 `.venv\Scripts\python.exe` 替换为 `.venv/bin/python`。
