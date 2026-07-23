# Smart Assistant for Silkworm Diseases

家蚕疾病多模态智能咨询平台。用户问诊已接入服务端四智能体 KG/RAG 证据链路。

## 当前功能

- 邮箱与手机号验证码登录；验证码由已配置的 SMTP/SMS 服务真实发送
- 退出登录，调用后端撤销当前会话
- 文本、图片、视频、文档和语音的多模态多轮问诊
- 上下文改写、风险/路由、HNSW、BM25、KG 和证据融合的实时轨迹
- 回答来源、版本、检索通道和证据摘要展示
- 真实 Neo4j 知识图谱探索、关系检索与节点/证据详情
- 咨询历史、项目、社区、养殖工作台和个人设置
- 长期记忆在本阶段强制关闭；上下文仅使用当前会话摘要、近期消息和结构化现场数据

## 前端技术栈

- Vite
- React
- TypeScript
- lucide-react
- 原生 CSS

## 后端技术约束

后端使用 Python：

- 虚拟环境：`venv`
- 包管理：`uv`
- API 框架建议：FastAPI
- 智能体编排：LangGraph
- 数据库与检索：PostgreSQL、Qdrant HNSW、OpenSearch BM25、Neo4j Aura
- 实时过程：SSE

## 本地运行

```bash
npm install
npm run dev
```

如果后端没有跑在默认地址，可以配置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8010/api/v1
```
