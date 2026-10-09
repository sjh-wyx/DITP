# 数智实训平台

面向职业教育大数据实训场景的 Web 端智能服务平台。

平台把 AI 副驾直接装进学生的真实 Linux 实训终端：以「一屏三栏」界面把对话区、任务列表与终端集成在同一页面，实时捕获学生的终端输入输出，经特征工程处理后注入 AI 对话上下文。AI 因此能看见学生刚敲了什么命令、报了什么错、卡在第几个子任务，给出贴合当前报错的排查方向，而不是脱离场景的泛泛解答。

## 已实现功能

| 功能 | 说明 |
|------|------|
| AI 实训副驾 | 终端内实时对话辅导（Training Agent），对话自动保存供 Report Agent 使用 |
| AI 课程生成 | Teacher Agent 自动生成实训课程和子任务 |
| Docker 隔离实训 | 每个学生独立容器，工具包宿主机挂载（镜像瘦身至229MB） |
| 多角色管理 | 学生/教师/管理员三端，课程班级子任务全生命周期 |
| 学情分析 | 进度追踪、任务完成率统计 |
| 实训计时 | 全程累计计时，后台 Persist，切换子任务不清零 |
| AI 实训报告生成 | 对话历史+学情分析多维度评估（Report Agent） |
| AI 知识库问答 | 大数据领域知识 RAG 问答（Knowledge Agent） |

## 技术栈

- 后端: Python 3.11 / Flask / Flask-SocketIO / SQLAlchemy
- 数据库: MySQL 8.0 / Redis 7
- AI 引擎: 4 个工作流 Agent + MaaS 兜底
- 容器化: Docker / Docker Compose
- 前端: HTML5 / Tailwind CSS / Iconify / Socket.IO

## Agent 工作流

| Agent | 输入 | 用途 |
|-------|------|------|
| 实训副驾 | 系统提示 + 终端上下文 + 文件预览 + 学生消息 | 终端内实时辅导，对话自动存储 |
| 知识问答 | 系统提示 + 终端上下文 + 学生问题 | 大数据领域知识检索 |
| 课程生成 | 课程主题 + 文件预览 | AI 自动生成实训课程和子任务 |
| 报告生成 | 课程信息 + 完成情况 + 对话摘要 | 自动生成学生个人实训报告 |

四个智能体挂载 **大数据技术知识库、实操诊断知识库、实训任务模板库** 三个学科知识库（共 56 篇文档），通过检索增强生成保障回答的学科专业性与可追溯性。

学科垂类能力以「学科知识库 RAG + 工作流编排 + 提示词工程」构建：检索增强提供专业依据，工作流编排承载四个智能体的协同与主备双通道容错。

## 学生容器环境

学生登录后自动分配独立 Docker 实训环境：

- 容器名: dts-student{ID}
- SSH 端口: 2200+ID
- 账号: learner / 123456
- 课程数据: /home/learner/course-data/ (只读挂载)
- 安装包: /home/learner/packages/ (宿主机 /opt/packages 只读挂载)
- 镜像: 229MB（纯 Ubuntu + SSH + 基本工具，不含 JDK——运行时从挂载拷贝）

> **注意**：应用容器需挂载 `-v /var/run/docker.sock:/var/run/docker.sock` 才能创建学生容器。

10 类大数据组件安装包预置: Hadoop, Spark, Hive, Kafka, Flink, ZooKeeper, HBase, Flume, Sqoop, Storm

## 快速启动

环境要求: Docker & Docker Compose

启动前确认两件事：

- **宿主机 `/opt/packages`** 已放入学生实训所需的组件安装包（Hadoop、Spark、Hive、Kafka、Flink 等 10 类）。学生容器以只读方式挂载该目录；路径不同请改 `docker-compose.yml` 里的 `STUDENT_PACKAGES_DIR`
- 应用容器需要访问宿主机 Docker（compose 已挂载 `/var/run/docker.sock`），否则无法为学生创建实训容器

```bash
# 以下命令在项目根目录执行

# 1. 准备配置：填入 SECRET_KEY、讯飞四个 Flow ID、MySQL 密码等
cp backend/.env.example backend/.env
cp backend/.env .env          # docker compose 从项目根目录读取变量替换

# 2. 构建学生实训镜像（应用镜像由 compose 构建）
docker build -t datatutor-student:latest -f Dockerfile_student .

# 3. 启动（首次会构建应用镜像；MySQL 首次就绪约需 20 秒，稍等再执行下一步）
docker compose up -d

# 4. 初始化种子账号（含管理员 admin）
docker compose exec app python init_users.py
```

访问: http://localhost（端口号80）

### 代码改动如何生效

compose 把 `backend/` 与 `frontend/` 挂载进容器（见 `docker-compose.yml` 的 `volumes`）：

- **前端**（HTML/JS）由 Flask 从磁盘读取，改完**即时生效**，无需重启
- **后端**（`.py`）由 Python 进程加载，改完执行 `docker compose restart app` 即可，无需重建镜像

## 默认账号

由 `backend/init_users.py` 创建（`admin` 幂等确保存在；演示教师与学生仅在空库时写入，重复执行不会覆盖已存在账号的密码）：

| 角色 | 账号 | 密码 |
|------|------|------|
| 管理员 | admin | admin123 |
| 演示教师 | tanwei | tanwei |
| 演示学生 | student1 / student2 / stu001 | 123456 |

> ⚠️ `admin123` 为弱口令，**正式部署前务必修改**。其余账号在管理端 / 注册页创建。

## 项目结构

```
数智实训平台/
├── backend/
│   ├── app.py                Flask 应用入口（注册九个 Blueprint）
│   ├── models.py             SQLAlchemy 数据模型
│   ├── database.py           数据库连接与初始化
│   ├── db_doris.py           Doris 分析库访问（可选，未接入时为空操作）
│   ├── docker_api.py         学生容器生命周期（创建 / 回收 / 清理）
│   ├── init_docker.py        容器镜像与挂载准备
│   ├── init_users.py         种子账号初始化（含幂等管理员）
│   ├── redis_client.py       Redis 在线状态与缓存（不可用时降级）
│   ├── captcha.py            图形验证码
│   ├── limiter_config.py     接口限流配置
│   ├── metrics.py            Prometheus 指标
│   ├── validators.py         入参校验
│   ├── celery_app.py         异步任务入口
│   ├── routes/               ai / auth / courses / classes / progress / chat
│   │                         / assessments / reports / analytics
│   ├── terminal_ws/          SSH WebSocket 终端与终端上下文特征工程
│   └── tasks/                报告生成任务
├── frontend/
│   ├── static/
│   │   └── js/
│   │       └── api.js        前端 API 封装层
│   ├── login.html            登录 / 注册
│   ├── hub.html              学生选课
│   ├── main.html             学生实训终端（一屏三栏）
│   ├── teacher.html          教师工作台
│   ├── admin.html            管理端
│   └── profile.html          个人中心
├── Dockerfile                应用镜像
├── Dockerfile_student        学生实训容器镜像
├── docker-compose.yml
└── backend/.env.example
```

## 常见问题

| 现象 | 原因与处理 |
|------|-----------|
| 启动报 `ModuleNotFoundError: No module named 'xxx'` | 运行镜像缺少该依赖。先 `docker compose exec app pip install xxx` 应急，再从 `backend/requirements.txt` 重建镜像 |
| `pip install` 报 `from versions: none` | 该镜像源的对应包文件不完整，换官方 PyPI 或阿里云源重试 |
| 学生登录后没有实训终端 | 应用容器未挂载 `docker.sock`，或宿主机未构建学生实训镜像 |
| 接口返回 `429 Too Many Requests` | 触发接口限流（登录 5 次/分钟、注册 3 次/分钟，按客户端 IP 计数）。同一出口 IP 下多人同时登录也会触发，稍候重试即可 |
| 改完代码没生效 | 前端改完即时生效；后端 `.py` 需 `docker compose restart app`。若部署时未挂载源码目录，则需 `docker compose up -d --build` 重建镜像 |
