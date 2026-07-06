# Smart Assistant for Silkworm Diseases

家蚕疾病多模态智能咨询平台。当前阶段先实现用户端页面原型，并已接入邮箱验证码登录接口。

## 当前原型范围

- 邮箱验证码登录，当前支持 QQ 邮箱和网易邮箱
- 退出登录，调用后端撤销当前会话
- 手机号验证码登录入口，后续接入
- 文本多轮问诊页面
- 视频上传咨询页面
- 咨询历史记录页面
- 长期记忆管理页面
- 用户个人中心页面

## 前端技术栈

- Vite
- React
- TypeScript
- lucide-react
- 原生 CSS

## 后端技术约束

后端后续使用 Python：

- 虚拟环境：`venv`
- 包管理：`uv`
- API 框架建议：FastAPI
- 智能体编排建议：LangGraph
- 检索集成建议：LangChain
- 数据库建议：PostgreSQL、Redis、Qdrant、Neo4j、OpenSearch、MinIO

## 本地运行

```bash
npm install
npm run dev
```

如果后端没有跑在默认地址，可以配置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8010/api/v1
```
