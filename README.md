# MCP Web Manager

基于mcp-proxy的Web可视化管理系统，实现stdio格式MCP服务自动转换为streamhttp格式，并提供实时监控和配置管理功能。

## 功能特性

- 🚀 **自动转换**: 将stdio格式的MCP服务自动转换为streamhttp格式
- 📊 **实时监控**: Web界面实时监控服务状态和性能
- 🔧 **服务管理**: 图形化界面管理MCP服务（增删改查、启停控制）
- 📋 **配置导出**: 一键生成本地客户端配置文件（Claude Desktop格式）
- 🌐 **Web界面**: 响应式Web管理界面，支持多种设备
- 🔗 **实时通信**: WebSocket支持，服务状态实时推送
- 📈 **监控面板**: 服务统计、性能指标、日志查看

## 技术架构

### 后端技术栈
- **FastAPI**: 高性能异步Web框架
- **SQLAlchemy**: ORM数据库操作
- **SQLite/PostgreSQL**: 数据存储
- **WebSocket**: 实时通信
- **mcp-proxy**: 核心stdio到streamhttp转换逻辑

### 前端技术栈  
- **React 18**: 用户界面框架
- **TypeScript**: 类型安全的JavaScript
- **Ant Design**: UI组件库
- **Vite**: 构建工具
- **Zustand**: 状态管理

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- uv (Python包管理器)

### 后端启动

```bash
cd backend

# 安装依赖
uv pip install -r requirements.txt

# 启动后端服务
python main.py
```

后端将运行在 `http://localhost:8000`

### 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将运行在 `http://localhost:3000`

### API文档

启动后端后访问：
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

## 使用指南

### 1. 添加MCP服务

在Web界面中点击"添加服务"，填写以下信息：
- 服务名称
- 命令路径（如：`uvx mcp-server-fetch`）
- 命令参数
- 环境变量
- 工作目录

### 2. 启动服务

添加服务后，点击"启动"按钮，系统会：
- 自动分配可用端口
- 启动stdio到streamhttp的转换
- 生成SSE和StreamHTTP访问URL

### 3. 监控服务

在仪表板页面可以查看：
- 服务运行状态
- 请求和错误统计
- 实时日志信息
- 性能指标

### 4. 导出配置

点击"导出配置"，可以获得Claude Desktop格式的配置文件：

```json
{
  "mcpServers": {
    "your-service": {
      "command": "mcp-proxy",
      "args": ["http://localhost:8001/sse"],
      "env": {
        "API_KEY": "your-api-key"
      }
    }
  }
}
```

## API接口

### 服务管理
- `GET /api/services/` - 获取所有服务
- `POST /api/services/` - 创建服务
- `PUT /api/services/{id}` - 更新服务
- `DELETE /api/services/{id}` - 删除服务
- `POST /api/services/{id}/action` - 服务操作（启动/停止/重启）

### 配置导出
- `GET /api/config/export` - 导出客户端配置
- `GET /api/config/export/claude-desktop` - Claude Desktop格式
- `GET /api/config/export/service/{id}` - 单个服务配置

### 仪表板
- `GET /api/dashboard/stats` - 统计信息
- `GET /api/dashboard/running-services` - 运行中服务
- `GET /api/dashboard/system-health` - 系统健康状态

### WebSocket
- `ws://localhost:8000/ws` - 实时状态推送

## 项目结构

```
mcp-web-manager/
├── backend/                    # 后端代码
│   ├── api/                    # API路由
│   ├── core/                   # mcp-proxy核心逻辑
│   ├── database/               # 数据库相关
│   ├── models/                 # 数据模型
│   ├── services/               # 业务逻辑
│   ├── websocket/              # WebSocket处理
│   ├── schemas.py              # Pydantic模式
│   └── main.py                 # 应用入口
├── frontend/                   # 前端代码
│   ├── src/
│   │   ├── components/         # 组件
│   │   ├── pages/              # 页面
│   │   ├── services/           # API服务
│   │   └── hooks/              # 自定义Hooks
│   └── package.json
├── shared/                     # 共享类型定义
└── deployment/                 # 部署配置
```

## 开发指南

### 后端开发

```bash
# 安装开发依赖
uv pip install -r requirements-dev.txt

# 运行测试
pytest

# 代码格式化
black backend/
ruff backend/

# 类型检查
mypy backend/
```

### 前端开发

```bash
# 代码检查
npm run lint

# 代码格式化
npm run lint:fix

# 构建生产版本
npm run build
```

## 部署

### Docker部署

```bash
# 构建镜像
docker build -t mcp-web-manager .

# 运行容器
docker run -p 8000:8000 -p 3000:3000 mcp-web-manager
```

### 手动部署

1. 构建前端：`npm run build`
2. 配置Nginx提供静态文件服务
3. 使用gunicorn运行后端：`gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app`

## 贡献指南

1. Fork项目
2. 创建功能分支：`git checkout -b feature-name`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送到分支：`git push origin feature-name`
5. 提交Pull Request

## 许可证

MIT License

## 支持

如有问题，请提交Issue或联系维护团队。