# MCP Web Manager

基于 [mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) 项目的Web可视化管理系统，为MCP服务提供直观的图形化管理界面。

## 项目简介

本项目参考了 [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) 的核心理念，在其基础上开发了完整的Web管理界面，让用户可以通过浏览器轻松管理MCP服务，无需手动编辑配置文件或使用命令行工具。

## 主要功能

- 🌐 **Web界面管理**: 通过浏览器管理所有MCP服务
- 📊 **实时监控**: 查看服务状态、运行统计和性能指标
- 🔧 **一键操作**: 启动、停止、重启服务，支持批量导入
- 📋 **配置导出**: 自动生成Claude Desktop等客户端配置
- 🚀 **协议转换**: 将stdio格式转换为SSE和StreamHTTP格式
- 📈 **状态跟踪**: 实时显示服务运行状态和工具数量

## 快速开始

### 方式一：Python脚本启动

```bash
# 直接运行启动脚本
python start_backend.py
```

服务将运行在 `http://localhost:8765`


访问 `http://localhost:8765` 即可使用Web管理界面。


### 方式二：Docker 部署

- 使用已发布镜像（推荐）

```bash
docker run -d --name mcp-web-manager \
  -p 8765:8765 \
  -e DATABASE_URL=sqlite:////data/mcp_web_manager.db \
  -v mcpwm-data:/data \
  --restart unless-stopped \
  9963kk/mcp-web-manager:latest
```

- 或使用 docker compose（仓库自带 docker-compose.yml）

```bash
docker compose up -d
```

服务将运行在 http://localhost:8765

可选环境变量：
- PUBLIC_HOST：用于复制链接时展示的外网主机名（例如 your.domain.com）
- DATABASE_URL：数据库连接串，默认 sqlite:////data/mcp_web_manager.db（已映射到容器内 /data）

数据持久化：
- 通过卷 mcpwm-data 将 SQLite 数据库持久化到宿主机

从源码本地构建镜像：

```bash
docker build -t mcp-web-manager:local .
docker run -d --name mcpwm -p 8765:8765 -v mcpwm-data:/data mcp-web-manager:local
```

注意（性能说明）：
- Docker 部署下，获取 MCP 工具数量统计会较慢，无法与服务启动同步显示；通常需等待一段时间（取决于容器内依赖冷启动与网络环境）后逐步补齐。
- 若希望更快的体验，当前最推荐的依然是“方式一：Python 脚本启动”。

## 使用说明

1. **添加服务**: 点击"从JSON添加"按钮，支持导入Claude Desktop配置格式
2. **管理服务**: 使用开关控制服务启停，点击服务名称查看详细配置
3. **获取配置**: 展开服务详情可复制SSE、StreamHTTP和Claude Desktop配置
4. **监控状态**: 实时查看服务运行状态和工具数量统计

## API文档

启动后访问 `http://localhost:8765/api/docs` 查看完整API文档。

## 项目结构

```
mcp-web-manager/
├── backend/                    # 后端代码
│   ├── api/                    # API路由
│   ├── core/                   # MCP代理核心逻辑
│   ├── database/               # 数据库操作
│   ├── models/                 # 数据模型
│   ├── services/               # 业务逻辑
│   ├── websocket/              # WebSocket处理
│   └── main.py                 # 应用入口
├── frontend/                   # 前端代码
│   └── public/                 # 静态文件
│       └── index.html          # Web界面
└── start_backend.py           # 启动脚本
```

## 许可证

MIT License

## 致谢

感谢 [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) 项目提供的基础实现和设计灵感。