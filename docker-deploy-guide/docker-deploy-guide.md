# Docker + Shell 部署知识库（Java 服务）

> 面向 Java 开发者的 Dockerfile + Shell 脚本部署详细教程  
> 适用于 Spring Boot / JAR 包服务部署场景  
> 所有内容自包含，无需运行环境即可学习参考

---

**目录**

- [第一章：Docker 核心概念](#第一章docker-核心概念)
- [第二章：Dockerfile 详解（Java 服务专用）](#第二章dockerfile-详解java-服务专用)
- [第三章：部署 Shell 脚本详解](#第三章部署-shell-脚本详解)
- [第四章：Dockerfile + 脚本配合模式](#第四章dockerfile--脚本配合模式)
- [第五章：Docker Compose 编排 Java 服务](#第五章docker-compose-编排-java-服务)
- [第六章：生产环境实战模式](#第六章生产环境实战模式)
- [第七章：故障排查手册](#第七章故障排查手册)
- [附录：速查手册](#附录速查手册)

---

# 第一章：Docker 核心概念

## 1.1 核心概念

### 1.1.1 镜像（Image）

**类比理解：镜像之于容器，如同 class 文件之于对象实例。**

Java 中，`.class` 文件是类的只读模板，JVM 根据它创建对象实例；Docker 中，镜像是容器的只读模板，Docker 引擎根据它创建运行中的容器。

```text
┌─────────────────────────────────────────────────┐
│                  Docker Image                    │
│  ┌─────────────────────────────────────────────┐ │
│  │  Layer 4 (顶层): 应用 JAR 包 + 启动脚本     │ │
│  ├─────────────────────────────────────────────┤ │
│  │  Layer 3: JDK 17 运行时                     │ │
│  ├─────────────────────────────────────────────┤ │
│  │  Layer 2: Debian 基础系统库                  │ │
│  ├─────────────────────────────────────────────┤ │
│  │  Layer 1 (底层): Linux 内核头文件            │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**分层存储原理（Union File System / 联合文件系统）：**

Docker 镜像并非一个单一的大文件，而是由多个只读层（Layer）堆叠而成。每一层对应 Dockerfile 中的一条指令：

```dockerfile
# 每条指令生成一个只读层
FROM debian:11-slim              # Layer 0: 基础操作系统层
RUN apt-get update && apt-get install -y curl  # Layer 1: 安装系统依赖
COPY target/app.jar /app/app.jar # Layer 2: 复制应用 JAR
EXPOSE 8080                      # Layer 3: 声明端口（仅元数据，不占空间）
ENTRYPOINT ["java", "-jar", "/app/app.jar"]  # Layer 4: 启动命令（仅元数据）
```

**分层存储的核心优势：**

1. **层共享**：如果你有 10 个 Java 服务都基于 `openjdk:17-slim`，那么基础 JDK 层只在磁盘上存储一份，10 个镜像共享这一层：

```text
镜像 A (user-service)     镜像 B (order-service)    镜像 C (pay-service)
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ user.jar (4MB)   │      │ order.jar (5MB)  │      │ pay.jar (3MB)    │  ← 各自独有
├──────────────────┤      ├──────────────────┤      ├──────────────────┤
│                  │      │                  │      │                  │
│  JDK 17 (200MB)  │      │  JDK 17 (200MB)  │      │  JDK 17 (200MB)  │  ← 磁盘只存一份
│                  │      │                  │      │                  │
├──────────────────┤      ├──────────────────┤      ├──────────────────┤
│ Debian (80MB)    │      │ Debian (80MB)    │      │ Debian (80MB)    │  ← 磁盘只存一份
└──────────────────┘      └──────────────────┘      └──────────────────┘

总磁盘占用 ≈ 80 + 200 + 4 + 5 + 3 = 292MB
而非 10 × (80 + 200 + ~4) = 2840MB
```

2. **增量传输**：`docker pull` 时只下载本地缺失的层。如果本地已有 `openjdk:17-slim`，拉取新镜像时只需下载上层的 JAR 包层。

3. **构建缓存**：`docker build` 时，如果某层指令和上下文未变，Docker 直接复用缓存层，不重新执行：

```bash
# 第一次构建：所有层都执行
$ docker build -t myapp:v1 .
Sending build context to Docker daemon  45.2MB
Step 1/5 : FROM openjdk:17-slim
 ---> 2a1d7c4c5e8f
Step 2/5 : RUN apt-get update && apt-get install -y curl
 ---> Running in 3b4c5d6e7f8a
 ---> 4c5d6e7f8a9b       # 执行了 15 秒
Step 3/5 : COPY target/app.jar /app/app.jar
 ---> 5d6e7f8a9b0c

# 第二次构建（只改了 JAR 包，Dockerfile 前 2 步不变）：
$ docker build -t myapp:v2 .
Step 1/5 : FROM openjdk:17-slim
 ---> Using cache           # ← 命中缓存，秒过
Step 2/5 : RUN apt-get update && apt-get install -y curl
 ---> Using cache           # ← 命中缓存，秒过
Step 3/5 : COPY target/app.jar /app/app.jar
 ---> 6e7f8a9b0c1d       # ← JAR 变了，重新构建这一层
```

**查看镜像分层信息：**

```bash
# docker history 显示每一层的大小和创建命令
$ docker history openjdk:17-slim
IMAGE          CREATED       CREATED BY                                      SIZE
2a1d7c4c5e8f   2 weeks ago   /bin/sh -c #(nop)  CMD ["jshell"]              0B
7f3d5e6a7b8c   2 weeks ago   /bin/sh -c #(nop)  ENTRYPOINT ["java" "-…      0B
9e4c5d6a7b8f   2 weeks ago   /bin/sh -c set -eux;   dpkgArch="$(dpkg -…    200MB    # JDK 层
1a2b3c4d5e6f   3 weeks ago   /bin/sh -c apt-get update && apt-get ins…      25MB     # 系统依赖层
3b4c5d6e7f8a   3 weeks ago   /bin/sh -c #(nop) ADD file:abc123... in /      80MB     # Debian 基础层
```

---

### 1.1.2 容器（Container）

**类比理解：容器之于镜像，如同对象实例之于 class 文件。**

```java
// Java 类比
Class<UserService> clazz = UserService.class;   // clazz = 镜像（只读模板）
UserService instance = clazz.newInstance();       // instance = 容器（运行实例）

// 可以从同一个 class 创建多个独立对象
UserService instance1 = clazz.newInstance();      // 容器1：独立状态
UserService instance2 = clazz.newInstance();      // 容器2：独立状态
// instance1 和 instance2 互不影响
```

```bash
# Docker：从同一个镜像启动多个独立容器
$ docker run -d --name user-svc-1 -p 8081:8080 myapp:latest   # 容器1
$ docker run -d --name user-svc-2 -p 8082:8080 myapp:latest   # 容器2
# 两个容器各自拥有独立的文件系统、进程空间、网络栈
```

**容器的读写层原理：**

容器在镜像的只读层之上，添加了一个可读写的容器层（Container Layer）。所有对容器的修改（写文件、安装软件、修改配置）都发生在这一层：

```text
┌──────────────────────────────────────────────┐
│         Container Layer (可读写)              │  ← 容器运行时的修改都在这里
│  /tmp/app.log  /app/config-override.yml      │
├──────────────────────────────────────────────┤
│  Layer 3 (只读): COPY app.jar                │
├──────────────────────────────────────────────┤
│  Layer 2 (只读): JDK 17                      │
├──────────────────────────────────────────────┤
│  Layer 1 (只读): Debian                      │
└──────────────────────────────────────────────┘

当容器删除时 → 读写层一起删除 → 所有修改丢失
这正是数据卷（Volume）存在的意义：将重要数据挂载到读写层之外
```

**Copy-on-Write（写时复制）机制：**

当容器需要修改镜像层中的某个文件时，Docker 不会直接修改只读层，而是将该文件复制到容器层再修改：

```bash
# 镜像层有一个 /etc/nginx/nginx.conf（只读）
# 容器内修改它：
$ docker exec my-nginx sh -c 'echo "worker_processes 4;" >> /etc/nginx/nginx.conf'

# Docker 的实际操作：
# 1. 检测到 /etc/nginx/nginx.conf 在镜像只读层
# 2. 将该文件从只读层复制到容器读写层
# 3. 在容器读写层中修改该文件
# 4. 后续读取该文件时，容器读写层的版本会"遮盖"镜像层的原始版本
```

**容器的生命周期状态机：**

```text
                    docker create
                         │
                         ▼
    ┌──────────┐   ┌──────────┐
    │  Created │───│  Running  │◄──── docker start / docker restart
    └──────────┘   └────┬─────┘
                        │
              ┌─────────┼──────────┐
              │         │          │
        docker stop   OOM Kill  进程退出
              │         │          │
              ▼         ▼          ▼
        ┌──────────┐ ┌────────┐ ┌────────┐
        │ Stopped  │ │  Dead  │ │Exited(│
        └────┬─────┘ └────────┘ │ 137)  │
             │                  └────────┘
        docker start                │
             │                      │
             ▼                      ▼
        ┌──────────┐          ┌──────────┐
        │ Running  │          │ Removed  │  ← docker rm
        └──────────┘          └──────────┘
```

```bash
# 查看容器完整状态信息
$ docker inspect --format='{{.State.Status}}' my-container
running

# 查看所有状态的容器
$ docker ps -a
CONTAINER ID   STATUS          NAMES
a1b2c3d4e5f6   Up 2 hours      user-service     # Running
g7h8i9j0k1l2   Exited (0) 5m   db-init          # Exited 正常退出
m3n4o5p6q7r8   Exited (1) 3m   order-service    # Exited 异常退出
s9t0u1v2w3x4   Created 10m     payment-service  # Created 未启动
```

---

### 1.1.3 仓库（Registry）

**类比理解：Docker 仓库之于镜像，如同 Maven 仓库之于 JAR 包。**

```text
Maven 世界:                           Docker 世界:
┌────────────────────┐               ┌────────────────────┐
│  Maven Central     │               │  Docker Hub         │
│  (公共中央仓库)     │    ←类比→     │  (公共中央仓库)      │
│  junit:junit:4.13  │               │  openjdk:17-slim    │
└────────────────────┘               └────────────────────┘
┌────────────────────┐               ┌────────────────────┐
│  Nexus / Artifactory│              │  Harbor / 私有Registry│
│  (私有仓库)         │    ←类比→     │  (私有仓库)          │
│  com.myco:auth:1.0 │               │  harbor.myco.com/project/auth:1.0│
└────────────────────┘               └────────────────────┘
```

**镜像全限定名格式解析：**

```text
完整格式：[registry-host[:port]/][namespace/]repository[:tag]

示例1：openjdk:17-slim
  registry-host: (默认) docker.io  ← 省略时默认 Docker Hub
  namespace:     library           ← Docker Hub 官方镜像省略 namespace
  repository:    openjdk
  tag:           17-slim           ← 省略时默认 latest

示例2：docker.io/library/openjdk:17-slim
  ↑ 等价于上面，完整写法

示例3：harbor.company.com/dev/user-service:v2.3.1
  registry-host: harbor.company.com  ← 私有仓库地址
  namespace:     dev                 ← Harbor 中的项目名
  repository:    user-service
  tag:           v2.3.1

示例4：registry.cn-hangzhou.aliyuncs.com/my-namespace/order-service:latest
  registry-host: registry.cn-hangzhou.aliyuncs.com  ← 阿里云镜像仓库
  namespace:     my-namespace
  repository:    order-service
  tag:           latest
```

**常见仓库类型：**

| 仓库类型 | 代表产品 | 适用场景 | URL 示例 |
|---------|---------|---------|---------|
| 公共官方 | Docker Hub | 开源镜像、公共基础镜像 | `docker.io/library/nginx:1.25` |
| 云厂商 | ACR(阿里云)、ECR(AWS) | 生产环境私有镜像 | `registry.cn-hangzhou.aliyuncs.com/...` |
| 自建私有 | Harbor | 企业内部 CI/CD | `harbor.internal.com/project/app:v1` |
| 最简私有 | `registry:2` 镜像 | 小团队、测试 | `localhost:5000/myapp:latest` |

**最简私有仓库一键启动：**

```bash
# 启动一个最基本的私有 Registry（无 UI、无认证，仅用于本地测试）
$ docker run -d \
  --name registry \
  -p 5000:5000 \
  -v /data/registry:/var/lib/registry \
  registry:2

# 推送镜像到本地 Registry
$ docker tag myapp:latest localhost:5000/myapp:latest
$ docker push localhost:5000/myapp:latest

# 查看本地 Registry 中的镜像列表
$ curl -s http://localhost:5000/v2/_catalog | python3 -m json.tool
{
  "repositories": [
    "myapp"
  ]
}

# 查看某镜像的所有 tag
$ curl -s http://localhost:5000/v2/myapp/tags/list | python3 -m json.tool
{
  "name": "myapp",
  "tags": [
    "latest",
    "v1.0"
  ]
}
```

---

### 1.1.4 网络（Network）

Docker 网络决定了容器之间、容器与宿主机之间如何通信。

**四种内置网络驱动详解：**

#### 1. Bridge（桥接模式）—— 默认模式

```text
宿主机 (Host)
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ Container A │    │ Container B │    │ Container C │  │
│  │ 172.17.0.2  │    │ 172.17.0.3  │    │ 172.17.0.4  │  │
│  │   eth0      │    │   eth0      │    │   eth0      │  │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘  │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            │                             │
│                    ┌───────┴───────┐                     │
│                    │   docker0     │                     │
│                    │  172.17.0.1   │  ← 虚拟网桥         │
│                    │  (veth pair)  │                     │
│                    └───────┬───────┘                     │
│                            │                             │
│                    ┌───────┴───────┐                     │
│                    │   vethXXXX    │                     │
│                    │  (NAT 规则)    │                     │
│                    └───────┬───────┘                     │
│                            │                             │
│                     宿主机 eth0                          │
│                    192.168.1.100                        │
└──────────────────────────────────────────────────────────┘

外部访问容器：192.168.1.100:8080 → iptables NAT → 172.17.0.2:8080
容器访问外部：172.17.0.2 → docker0 → iptables MASQUERADE → eth0 → 外部
```

```bash
# 默认 bridge 网络下，容器间通过 IP 通信（不推荐，IP 会变）
$ docker run -d --name svc-a openjdk:17-slim java -jar app.jar
$ docker run -d --name svc-b openjdk:17-slim java -jar app.jar

# svc-b 通过 IP 访问 svc-a（注意：默认 bridge 不支持容器名解析！）
$ docker exec svc-b curl http://172.17.0.2:8080/api/users  # 可以
$ docker exec svc-b curl http://svc-a:8080/api/users        # 失败！DNS 解析不了

# 自定义 bridge 网络（推荐：支持容器名自动 DNS 解析）
$ docker network create --driver bridge app-network
$ docker run -d --name user-svc --network app-network -p 8081:8080 myapp:latest
$ docker run -d --name order-svc --network app-network -p 8082:8080 myapp:latest

# 自定义 bridge 中，容器名即主机名，自动 DNS 解析
$ docker exec order-svc curl http://user-svc:8080/api/users   # 成功！

# Spring Boot 应用中使用容器名作为服务地址
# application.yml
# spring:
#   datasource:
#     url: jdbc:mysql://mysql-svc:3306/mydb    # mysql-svc 是容器名
#   redis:
#     host: redis-svc                          # redis-svc 是容器名
```

#### 2. Host（主机模式）—— 容器直接使用宿主机网络栈

```text
宿主机 (Host)
┌──────────────────────────────────────────────┐
│                                              │
│  宿主机网络栈 (eth0: 192.168.1.100)          │
│       │                                      │
│       ├── 宿主机进程 (PID 1000: sshd)        │
│       ├── 宿主机进程 (PID 2000: nginx)       │
│       └── 容器进程 (PID 3000: java -jar app) │ ← 直接共享宿主机网络
│                                              │
│  容器内看到的网络 = 宿主机的网络              │
│  容器绑定 8080 端口 = 宿主机 8080 端口       │
│  无需 -p 端口映射！                          │
└──────────────────────────────────────────────┘
```

```bash
# Host 模式：容器直接使用宿主机网络，无需端口映射
$ docker run -d --network host --name my-app myapp:latest

# 容器内监听的 8080 端口直接绑定在宿主机的 8080 上
# 等价于在宿主机上直接运行 java -jar app.jar

# 适用场景：
# 1. 网络性能要求高（避免 NAT 转发开销）
# 2. 需要访问宿主机本地服务（如宿主机上的数据库 127.0.0.1:3306）
# 3. Kubernetes 中某些 DaemonSet（如 node-exporter、calico）

# 注意事项：
# - 端口冲突：多个容器不能绑定宿主机同一端口
# - 安全性降低：容器能访问宿主机所有网络接口
# - --network host 和 -p 参数互斥，同时使用会报错
```

#### 3. None（无网络模式）—— 完全隔离

```bash
# None 模式：容器只有 lo 回环接口，无外部网络
$ docker run -d --network none --name isolated-app myapp:latest

$ docker exec isolated-app ip addr
1: lo: <LOOPBACK,UP> mtu 65536
    inet 127.0.0.1/8 scope host lo    # 只有回环地址

# 适用场景：
# 1. 安全敏感的批处理任务（不需要网络）
# 2. 离线计算任务
# 3. 密码生成、密钥处理等安全操作
```

#### 4. Overlay（覆盖网络）—— 跨主机容器通信

```text
主机 A (192.168.1.100)              主机 B (192.168.1.101)
┌─────────────────────────┐         ┌─────────────────────────┐
│  ┌───────────────────┐  │         │  ┌───────────────────┐  │
│  │ Container A       │  │         │  │ Container B       │  │
│  │ 10.0.0.2          │◄─┼──VXLAN──┼─►│ 10.0.0.3          │  │
│  │ (overlay 网络)     │  │  隧道   │  │ (overlay 网络)     │  │
│  └───────────────────┘  │         │  └───────────────────┘  │
│          │              │         │          │              │
│     docker_gwbridge     │         │     docker_gwbridge     │
│          │              │         │          │              │
│        eth0             │         │        eth0             │
└─────────────────────────┘         └─────────────────────────┘

Container A (10.0.0.2) 可以直接 ping Container B (10.0.0.3)
物理网络上传输的是 VXLAN 封装的数据包
```

```bash
# Overlay 网络通常由 Docker Swarm 或 Kubernetes 自动创建和管理
# 手动创建示例（需要先初始化 Swarm）：

$ docker swarm init
$ docker network create --driver overlay --attachable my-overlay-net

# 在两台主机上分别启动容器，加入同一个 overlay 网络
# 主机 A：
$ docker run -d --name svc-a --network my-overlay-net myapp:latest

# 主机 B：
$ docker run -d --name svc-b --network my-overlay-net myapp:latest

# svc-a 和 svc-b 可以通过容器名互相通信，即使在不同物理主机上
$ docker exec svc-a curl http://svc-b:8080/api/data  # 跨主机通信成功
```

**网络模式对比总结：**

| 模式 | 通信范围 | 性能 | 容器间DNS | 端口映射 | 典型场景 |
|------|---------|------|----------|---------|---------|
| bridge（默认） | 同一宿主机 | 中等（NAT） | 仅自定义bridge | 需要 -p | 单机多容器 |
| bridge（自定义） | 同一宿主机 | 中等（NAT） | 支持 | 需要 -p | 单机微服务 |
| host | 宿主机网络 | 最高（无NAT） | N/A | 不需要 | 高性能、访问宿主机服务 |
| none | 仅回环 | N/A | N/A | N/A | 安全隔离、离线任务 |
| overlay | 跨宿主机 | 较低（VXLAN封装） | 支持 | 不需要 | Swarm/K8s 跨主机通信 |

---

### 1.1.5 数据卷（Volume）

容器删除后，容器读写层中的数据会一起消失。数据卷提供了**绕过容器层**的数据持久化机制。

#### Bind Mount（绑定挂载）

将宿主机的指定目录直接挂载到容器中，宿主机和容器看到的是**同一份文件**：

```bash
# 语法：-v /宿主机路径:/容器路径[:ro]
# :ro 表示 read-only，容器内只能读取不能写入

# 场景1：挂载 Spring Boot 配置文件
$ docker run -d \
  --name user-service \
  -p 8080:8080 \
  -v /opt/apps/user-service/application.yml:/app/config/application.yml:ro \
  myapp:latest

# 容器内 /app/config/application.yml 就是宿主机 /opt/apps/user-service/application.yml
# 修改宿主机文件 → 容器内立刻生效（注意：Spring Boot 默认不会自动刷新配置）

# 场景2：挂载日志目录到宿主机
$ docker run -d \
  --name order-service \
  -p 8081:8080 \
  -v /var/log/order-service:/app/logs \
  myapp:latest

# 容器内应用写 /app/logs/app.log → 宿主机 /var/log/order-service/app.log 同步更新
# 宿主机可以用 logstash/filebeat 直接采集日志，无需 docker cp

# 场景3：开发环境挂载源码目录（代码修改即时生效）
$ docker run -d \
  --name dev-app \
  -p 8080:8080 \
  -v /home/dev/myproject/src:/app/src \
  -v /home/dev/myproject/pom.xml:/app/pom.xml \
  maven:3.8-openjdk-17
```

**Bind Mount 的注意事项：**

```bash
# 1. 宿主机路径必须存在，否则 Docker 会自动创建一个空目录（常见坑！）
$ docker run -v /opt/missing-dir:/app/data myapp:latest
# 如果 /opt/missing-dir 不存在 → Docker 自动创建该目录（空目录） → 容器内 /app/data 是空的！
# 原本镜像里 /app/data 的内容被"遮盖"了

# 2. 文件权限问题
# 容器内进程通常以 root 运行，但宿主机文件可能属于普通用户
$ ls -la /opt/apps/config.yml
-rw-r--r-- 1 deploy deploy 1024 Jan 1 config.yml

# 容器内以 root 写入 → 宿主机上文件 owner 变成 root → deploy 用户无法读取
# 解决：指定容器内用户
$ docker run -u 1000:1000 -v /opt/apps/config.yml:/app/config.yml myapp:latest

# 3. 绝对路径 vs 相对路径
$ docker run -v ./config:/app/config myapp:latest     # 正确：相对路径
$ docker run -v config:/app/config myapp:latest        # 这是 Volume！不是 Bind Mount！
# 关键区别：以 / 或 ./ 开头 → Bind Mount；不以 / 开头且不是 ./ → Volume
```

#### Volume（命名卷）

Docker 管理的数据卷，存储在 Docker 的专用目录中（`/var/lib/docker/volumes/`），与宿主机路径解耦：

```bash
# 语法：-v 卷名:/容器路径  或  --mount type=volume,src=卷名,dst=/容器路径

# 场景1：MySQL 数据持久化（最经典的 Volume 用例）
$ docker run -d \
  --name mysql \
  -e MYSQL_ROOT_PASSWORD=secret \
  -v mysql-data:/var/lib/mysql \
  mysql:8.0

# Docker 自动创建名为 mysql-data 的卷
# MySQL 数据写入 /var/lib/mysql → 实际存储在 Docker 管理的卷中
# 删除容器后，卷中的数据仍在 → 下次用同一个卷名即可恢复

# 查看卷信息
$ docker volume inspect mysql-data
[
    {
        "CreatedAt": "2024-01-15T10:30:00Z",
        "Driver": "local",
        "Mountpoint": "/var/lib/docker/volumes/mysql-data/_data",  # 实际存储路径
        "Name": "mysql-data",
        "Options": {},
        "Scope": "local"
    }
]

# 场景2：多个容器共享数据卷
$ docker volume create shared-logs

# 容器A 写日志
$ docker run -d --name producer \
  -v shared-logs:/app/logs \
  myapp:latest

# 容器B 读日志
$ docker run -d --name consumer \
  -v shared-logs:/app/logs:ro \
  log-processor:latest
```

#### Bind Mount vs Volume 对比

| 特性 | Bind Mount | Volume |
|------|-----------|--------|
| 存储位置 | 宿主机任意指定路径 | `/var/lib/docker/volumes/<name>/_data` |
| 创建方式 | `-v /host/path:/container/path` | `-v volume_name:/container/path` |
| 生命周期管理 | 手动管理，Docker 不管 | `docker volume` 命令管理 |
| 删除容器时 | 宿主机文件不受影响 | 卷不受影响，需手动 `docker volume rm` |
| 可移植性 | 差（依赖宿主机路径） | 好（Docker 抽象管理） |
| 备份 | 直接操作宿主机文件 | `docker run --rm -v vol:/data -v $(pwd):/backup alpine tar czf /backup/vol.tar.gz /data` |
| 典型场景 | 配置文件、日志、开发挂载 | 数据库数据、共享存储 |
| Docker Compose 兼容 | 需确保路径存在 | Docker 自动创建 |

**tmpfs Mount（内存文件系统）—— 补充：**

```bash
# tmpfs：数据只存在内存中，容器停止即消失，适合敏感临时数据
$ docker run -d \
  --name myapp \
  --tmpfs /app/temp:rw,noexec,nosuid,size=100m \
  myapp:latest

# 场景：存放临时加密密钥、session 文件等
# 优点：速度快（内存级别）、安全（不落盘）
# 缺点：容器重启数据丢失、受内存大小限制
```

---

## 1.2 常用命令速查

### 1.2.1 镜像管理

#### `docker pull` —— 拉取镜像

```bash
# 语法
docker pull [OPTIONS] NAME[:TAG|@DIGEST]

# 拉取 OpenJDK 17 精简版（Java 应用基础镜像首选）
$ docker pull openjdk:17-slim
17-slim: Pulling from library/openjdk
a2abf6c4d29d: Pull complete    # ← 每一层的下载进度
716b0e4a5020: Pull complete
301a4524e155: Pull complete
Digest: sha256:abc123def456...  # ← 镜像的 SHA256 摘要，用于验证完整性
Status: Downloaded newer image for openjdk:17-slim

# 拉取指定平台的镜像（Apple M1/M2 上构建 x86 镜像时需要）
$ docker pull --platform linux/amd64 openjdk:17-slim

# 使用 digest 拉取（精确到特定构建版本，比 tag 更精确）
$ docker pull openjdk@sha256:abc123def456...
# tag 可能被覆盖（如 latest 指向不同版本），digest 永远不变
```

#### `docker images` —— 列出本地镜像

```bash
# 语法
docker images [OPTIONS] [REPOSITORY[:TAG]]

# 列出所有本地镜像
$ docker images
REPOSITORY    TAG        IMAGE ID       CREATED        SIZE
openjdk       17-slim    2a1d7c4c5e8f   2 weeks ago    405MB
myapp         latest     5b6c7d8e9f0a   3 days ago     410MB
nginx         1.25       a3b4c5d6e7f8   1 month ago    142MB

# 只显示镜像 ID（用于批量删除）
$ docker images -q
2a1d7c4c5e8f
5b6c7d8e9f0a
a3b4c5d6e7f8

# 过滤显示：只看仓库名包含 myapp 的镜像
$ docker images myapp
REPOSITORY    TAG        IMAGE ID       CREATED        SIZE
myapp         latest     5b6c7d8e9f0a   3 days ago     410MB
myapp         v1.0       3c4d5e6f7a8b   1 week ago     408MB

# 显示悬空镜像（<none> 标签的镜像，通常是构建过程中产生的中间层）
$ docker images -f "dangling=true"
REPOSITORY    TAG        IMAGE ID       CREATED        SIZE
<none>        <none>     9e0f1a2b3c4d   2 hours ago    410MB
# 清理悬空镜像：docker image prune
```

#### `docker rmi` —— 删除镜像

```bash
# 语法
docker rmi [OPTIONS] IMAGE [IMAGE...]

# 删除指定镜像
$ docker rmi myapp:v1.0
Untagged: myapp:v1.0
Deleted: sha256:3c4d5e6f7a8b...

# 强制删除（即使有容器在使用该镜像）
$ docker rmi -f myapp:latest

# 删除所有悬空镜像（最常用的清理方式）
$ docker image prune
WARNING! This will remove all dangling images.
Are you sure you want to continue? [y/N] y
Deleted Images:
untagged: ...
deleted: sha256:9e0f1a2b3c4d...
Total reclaimed space: 150MB

# 批量删除所有未被容器使用的镜像
$ docker image prune -a
# 注意：-a 会删除所有没有运行中容器的镜像，下次启动需要重新 pull
```

#### `docker tag` —— 给镜像打标签

```bash
# 语法
docker tag SOURCE_IMAGE[:TAG] TARGET_IMAGE[:TAG]

# 场景：构建完成后打版本标签和 latest 标签
$ docker tag myapp:latest harbor.company.com/dev/myapp:v2.3.1
$ docker tag myapp:latest harbor.company.com/dev/myapp:latest

# 打完标签后，同一个镜像有两个名字（IMAGE ID 相同）
$ docker images | grep myapp
harbor.company.com/dev/myapp   v2.3.1    5b6c7d8e9f0a   3 days ago   410MB
harbor.company.com/dev/myapp   latest    5b6c7d8e9f0a   3 days ago   410MB
myapp                          latest    5b6c7d8e9f0a   3 days ago   410MB
# ↑ 三行 IMAGE ID 相同，说明是同一个镜像，只是标签不同
```

#### `docker save` / `docker load` —— 镜像导出与导入

```bash
# docker save：将镜像导出为 tar 文件
# 语法
docker save [OPTIONS] IMAGE [IMAGE...]

# 导出单个镜像
$ docker save -o myapp-v2.3.1.tar myapp:v2.3.1
# -o 指定输出文件名

# 导出多个镜像到一个 tar 文件
$ docker save -o all-images.tar openjdk:17-slim myapp:v2.3.1 nginx:1.25

# 压缩导出（节省传输带宽）
$ docker save myapp:v2.3.1 | gzip > myapp-v2.3.1.tar.gz

# docker load：从 tar 文件导入镜像
$ docker load -i myapp-v2.3.1.tar
Loaded image: myapp:v2.3.1

$ docker load < myapp-v2.3.1.tar.gz   # 也可以用 stdin
Loaded image: myapp:v2.3.1

# 典型场景：内网环境部署（无法访问 Docker Hub / 私有仓库）
# 步骤1（外网机器）：docker save -o app.tar myapp:v1.0
# 步骤2：scp app.tar deploy@192.168.1.50:/tmp/
# 步骤3（内网机器）：docker load -i /tmp/app.tar
```

#### `docker build` —— 构建镜像

```bash
# 语法
docker build [OPTIONS] PATH | URL | -

# 基本构建
$ docker build -t myapp:v1.0 .
# -t 指定镜像名和标签
# . 表示 Dockerfile 在当前目录，构建上下文为当前目录

# 指定 Dockerfile 位置
$ docker build -t myapp:v1.0 -f docker/Dockerfile .

# 构建时不使用缓存（排查构建问题时使用）
$ docker build --no-cache -t myapp:v1.0 .

# 传入构建参数（ARG）
$ docker build \
  --build-arg JAR_FILE=target/user-service.jar \
  --build-arg APP_VERSION=2.3.1 \
  -t user-service:v2.3.1 .

# 多平台构建（需要 buildx）
$ docker buildx build --platform linux/amd64,linux/arm64 -t myapp:v1.0 .

# 典型 Java 项目的 Dockerfile 和构建命令
# Dockerfile:
#   FROM eclipse-temurin:17-jre-alpine
#   ARG JAR_FILE=app.jar
#   COPY ${JAR_FILE} /app/app.jar
#   EXPOSE 8080
#   ENTRYPOINT ["java", "-jar", "/app/app.jar"]

$ docker build \
  --build-arg JAR_FILE=target/user-service-2.3.1.jar \
  -t user-service:2.3.1 \
  -t user-service:latest \
  .
```

#### `docker history` —— 查看镜像构建历史

```bash
# 语法
docker history [OPTIONS] IMAGE

# 查看镜像的各层构建信息
$ docker history myapp:latest
IMAGE          CREATED       CREATED BY                                      SIZE
5b6c7d8e9f0a   3 days ago    /bin/sh -c #(nop)  ENTRYPOINT ["java" "-j…     0B
<missing>      3 days ago    /bin/sh -c #(nop)  EXPOSE 8080                 0B
<missing>      3 days ago    /bin/sh -c #(nop) COPY file:abc123... in /…    45.2MB
<missing>      2 weeks ago   /bin/sh -c #(nop)  CMD ["jshell"]             0B
<missing>      2 weeks ago   /bin/sh -c set -eux;   ...                     200MB

# 显示完整信息（不截断 CREATED BY 列）
$ docker history --no-trunc myapp:latest

# 排查镜像体积过大的问题：查看哪一层占空间最多
$ docker history --format "{{.Size}}\t{{.CreatedBy}}" myapp:latest | sort -rh
200MB    set -eux;   dpkgArch="$(dpkg ...
45.2MB   COPY file:abc123...
0B       ENTRYPOINT ["java" "-jar" "/app/app.jar"]
# → JDK 层占了 200MB，考虑换用 JRE 或 Alpine 版本
```

---

### 1.2.2 容器生命周期

#### `docker run` —— 创建并启动容器

```bash
# 语法
docker run [OPTIONS] IMAGE [COMMAND] [ARG...]

# 常用参数完整示例：启动一个 Java 微服务
$ docker run -d \                        # -d 后台运行（detached 模式）
  --name user-service \                  # 容器名称
  --restart=unless-stopped \             # 重启策略
  -p 8081:8080 \                         # 端口映射：宿主机:容器
  -e SPRING_PROFILES_ACTIVE=prod \       # 环境变量
  -e JAVA_OPTS="-Xmx512m -Xms256m" \    # JVM 参数
  -v /opt/config/app.yml:/app/config.yml:ro \  # 挂载配置（只读）
  -v app-logs:/app/logs \                # 命名卷挂载日志
  --network app-network \                # 加入指定网络
  --memory=1g \                          # 内存限制
  --cpus=2 \                             # CPU 限制
  --health-cmd="curl -f http://localhost:8080/actuator/health || exit 1" \  # 健康检查
  --health-interval=30s \                # 健康检查间隔
  --health-timeout=10s \                 # 健康检查超时
  --health-retries=3 \                   # 连续失败次数才判定不健康
  myapp:latest                           # 镜像名

# 重启策略详解：
# --restart=no           # 默认值，不自动重启
# --restart=on-failure   # 非零退出码时重启
# --restart=on-failure:5 # 非零退出码时重启，最多5次
# --restart=unless-stopped # 除非手动 stop，否则总是重启（推荐生产使用）
# --restart=always       # 总是重启，包括 Docker 守护进程重启后

# 前台运行（调试时使用，能看到实时日志）
$ docker run --rm -it -p 8080:8080 myapp:latest
# --rm：容器退出后自动删除
# -it：交互模式，分配 TTY
# Ctrl+C 停止容器
```

#### `docker start` / `docker stop` / `docker restart`

```bash
# docker start：启动已停止的容器
$ docker start user-service
user-service

# docker stop：优雅停止容器（发送 SIGTERM，10秒后 SIGKILL）
$ docker stop user-service
user-service

# 设置停止超时时间（Java 应用可能需要更长时间做优雅关闭）
$ docker stop -t 30 user-service
# -t 30：等待30秒让应用完成优雅关闭（Spring Boot 处理中的请求）
# Spring Boot 配合：server.shutdown=graceful

# docker restart：重启容器
$ docker restart user-service
user-service

# 批量操作
$ docker stop $(docker ps -q)           # 停止所有运行中的容器
$ docker restart $(docker ps -q)        # 重启所有运行中的容器
```

#### `docker rm` —— 删除容器

```bash
# 语法
docker rm [OPTIONS] CONTAINER [CONTAINER...]

# 删除已停止的容器
$ docker rm user-service
user-service

# 强制删除运行中的容器（先 kill 再删）
$ docker rm -f user-service

# 删除容器同时删除其匿名卷
$ docker rm -v user-service

# 批量删除所有已停止的容器
$ docker container prune
WARNING! This will remove all stopped containers.
Are you sure? [y/N] y

# 按状态过滤删除
$ docker rm $(docker ps -a -q --filter "status=exited")  # 删除所有已退出容器
$ docker rm $(docker ps -a -q --filter "name=test-")     # 删除名称以 test- 开头的容器
```

#### `docker create` —— 创建但不启动容器

```bash
# 语法：与 docker run 参数相同，但只创建不启动
$ docker create --name user-service -p 8080:8080 myapp:latest
a1b2c3d4e5f6...

# 后续启动
$ docker start user-service

# 使用场景：需要先创建容器、修改配置后再启动
# 或者配合 docker cp 先往容器里放文件
$ docker create --name myapp -p 8080:8080 myapp:latest
$ docker cp custom-config.yml myapp:/app/config.yml
$ docker start myapp
```

---

### 1.2.3 容器交互

#### `docker exec` —— 在运行中的容器内执行命令

```bash
# 语法
docker exec [OPTIONS] CONTAINER COMMAND [ARG...]

# 进入容器的交互式终端
$ docker exec -it user-service /bin/bash
# -i 保持 stdin 打开，-t 分配伪终端
# 进入后可以像 SSH 登录一样操作容器内部

# 如果容器内没有 bash（如 Alpine 基础镜像），使用 sh
$ docker exec -it user-service /bin/sh

# 不进入容器，直接执行单条命令
$ docker exec user-service cat /app/config.yml

# 在容器内执行 Java 诊断命令
$ docker exec user-service jps -l
1 my.company.UserServiceApplication

$ docker exec user-service jstat -gc 1
 S0C    S1C    S0U    S1U      EC       EU        OC         OU       MC     MU    ...
 512.0  512.0   0.0   128.3   2048.0   1024.5    4096.0     2048.3   25600  24576 ...

# 以 root 用户执行（即使容器默认用户不是 root）
$ docker exec -u root user-service apt-get update

# 指定工作目录
$ docker exec -w /app/logs user-service ls -la
```

#### `docker logs` —— 查看容器日志

```bash
# 语法
docker logs [OPTIONS] CONTAINER

# 查看全部日志
$ docker logs user-service

# 实时跟踪日志（最常用）
$ docker logs -f user-service
# -f = --follow，类似 tail -f

# 显示最近 N 行日志
$ docker logs --tail 100 user-service
# 只显示最后 100 行

# 实时跟踪 + 最近 N 行（生产排障最常用组合）
$ docker logs -f --tail 200 user-service

# 显示时间戳
$ docker logs -t user-service
2024-01-15T10:30:00.123456789Z [main] INFO  c.m.UserService - Started in 3.5s

# 查看指定时间范围的日志
$ docker logs --since "2024-01-15T10:00:00" user-service        # 某时间之后
$ docker logs --since "2024-01-15T10:00:00" --until "2024-01-15T11:00:00" user-service
$ docker logs --since 30m user-service                           # 最近30分钟

# 查看容器上一次运行的日志（容器重启后看崩溃前的日志）
$ docker logs --previous user-service
# 场景：容器 OOM 被杀后自动重启，想看崩溃前的日志

# Java 应用日志输出配置建议：
# 1. Spring Boot 默认输出到 stdout/stderr → docker logs 可直接看到
# 2. 如果用了 logback 且输出到文件 → 需要 -v 挂载日志目录
# 3. 推荐配置：同时输出到 stdout 和文件
# logback-spring.xml:
#   <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
#     <encoder>...</encoder>
#   </appender>
#   <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
#     <file>/app/logs/app.log</file>
#     ...
#   </appender>
#   <root level="INFO">
#     <appender-ref ref="CONSOLE" />
#     <appender-ref ref="FILE" />
#   </root>
```

#### `docker inspect` —— 查看容器/镜像详细信息

```bash
# 语法
docker inspect [OPTIONS] NAME|ID [NAME|ID...]

# 查看容器完整信息（JSON 格式，内容很多）
$ docker inspect user-service

# 使用 --format 提取特定字段（Go 模板语法）

# 获取容器 IP 地址
$ docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' user-service
172.17.0.2

# 获取容器绑定的端口映射
$ docker inspect --format '{{json .NetworkSettings.Ports}}' user-service
{"8080/tcp":[{"HostIp":"0.0.0.0","HostPort":"8081"}]}

# 获取容器启动命令
$ docker inspect --format '{{.Config.Cmd}}' user-service
[java -jar /app/app.jar]

# 获取容器环境变量
$ docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' user-service
SPRING_PROFILES_ACTIVE=prod
JAVA_OPTS=-Xmx512m -Xms256m
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# 获取容器挂载信息
$ docker inspect --format '{{json .Mounts}}' user-service | python3 -m json.tool
[
    {
        "Type": "bind",
        "Source": "/opt/config/app.yml",
        "Destination": "/app/config.yml",
        "Mode": "ro",
        "RW": false
    },
    {
        "Type": "volume",
        "Name": "app-logs",
        "Destination": "/app/logs",
        "RW": true
    }
]

# 获取容器健康检查状态
$ docker inspect --format '{{json .State.Health}}' user-service | python3 -m json.tool
{
  "Status": "healthy",
  "FailingStreak": 0,
  "Log": [
    {
      "ExitCode": 0,
      "Output": "{\"status\":\"UP\"}"
    }
  ]
}

# 获取容器重启策略
$ docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' user-service
unless-stopped
```

#### `docker stats` —— 实时资源占用监控

```bash
# 语法
docker stats [OPTIONS] [CONTAINER...]

# 实时监控所有容器（动态刷新，类似 top）
$ docker stats
CONTAINER ID   NAME            CPU %   MEM USAGE / LIMIT   MEM %   NET I/O     BLOCK I/O   PIDS
a1b2c3d4e5f6   user-service    2.35%   384MiB / 1GiB      37.5%   1.2kB / 0B  50MB / 0B   42
g7h8i9j0k1l2   order-service   0.85%   256MiB / 512MiB    50.0%   850B / 0B   20MB / 0B   38

# 只看一次（不动态刷新）
$ docker stats --no-stream
# 输出同上，但只显示一次当前值，适合脚本采集

# 只监控特定容器
$ docker stats user-service order-service

# 自定义输出格式
$ docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
NAME            CPU %   MEM USAGE / LIMIT
user-service    2.35%   384MiB / 1GiB
order-service   0.85%   256MiB / 512MiB

# Java 容器内存监控注意事项：
# 1. MEM USAGE 包含 JVM 堆 + 非堆（Metaspace、线程栈、直接内存）
# 2. 不要只看 JVM 堆内存，容器 OOM Kill 看的是进程总内存
# 3. -Xmx 只是堆上限，JVM 实际内存 = 堆 + Metaspace + 线程栈 + 堆外内存
# 4. 建议容器内存限制设为 -Xmx 的 1.5~2 倍
```

#### `docker top` —— 查看容器内进程

```bash
# 语法
docker top CONTAINER [ps OPTIONS]

# 查看容器内的进程列表
$ docker top user-service
UID    PID    PPID   C   STIME   TTY     TIME       CMD
root   12345  12330  2   10:30   ?       00:00:05   java -jar /app/app.jar
root   12678  12345  0   10:31   ?       00:00:00   /bin/bash

# PID 是宿主机上的进程 ID（不是容器内的 PID）
# 这说明容器进程就是宿主机上的普通进程，只是被 namespace 隔离

# 显示完整命令行
$ docker top user-service aux
USER   PID %CPU %MEM    VSZ   RSS TTY   STAT START  TIME COMMAND
root  12345  2.3 37.5 4567890 384000 ?   Sl   10:30 0:05 java -jar /app/app.jar --spring.profiles.active=prod

# 排查场景：容器 CPU 飙高，查看是哪个线程
$ docker top user-service -H
# -H 显示线程
UID    PID    PPID   C   STIME   TTY     TIME       CMD
root   12345  12330  2   10:30   ?       00:00:05   java -jar /app/app.jar
root   12346  12345  95  10:30   ?       00:02:30   /usr/bin/java ...  ← CPU 飙高的线程
```

#### `docker port` —— 查看端口映射

```bash
# 语法
docker port CONTAINER [PRIVATE_PORT[/PROTO]]

# 查看容器所有端口映射
$ docker port user-service
8080/tcp -> 0.0.0.0:8081
8443/tcp -> 0.0.0.0:8444

# 查看特定容器端口的映射
$ docker port user-service 8080
0.0.0.0:8081

$ docker port user-service 8080/tcp
0.0.0.0:8081

# 排查场景：容器内服务启动了但外部访问不了
# 1. 先用 docker port 确认端口映射是否正确
$ docker port my-app 8080
# 如果没有输出 → 端口没有映射，启动时漏了 -p 参数
# 2. 如果映射了，检查是否绑定了 127.0.0.1 而非 0.0.0.0
$ docker port my-app 8080
127.0.0.1:8080   # ← 只能从宿主机本地访问，外部访问不了！
# 应该用 -p 0.0.0.0:8080:8080 或 -p 8080:8080
```

#### `docker cp` —— 容器与宿主机之间拷贝文件

```bash
# 语法
docker cp [OPTIONS] CONTAINER:SRC_PATH DEST_PATH|-
docker cp [OPTIONS] SRC_PATH|- CONTAINER:DEST_PATH

# 从容器内拷贝文件到宿主机
$ docker cp user-service:/app/logs/app.log ./app.log

# 从容器内拷贝整个目录
$ docker cp user-service:/app/logs/ ./container-logs/

# 从宿主机拷贝文件到容器内
$ docker cp ./new-config.yml user-service:/app/config.yml

# 拷贝时保留权限和时间戳
$ docker cp -a user-service:/app/data/ ./backup/

# 典型排障场景：
# 1. 拷贝 Java 应用的 heap dump 出来分析
$ docker exec user-service jcmd 1 GC.heap_dump /tmp/heap.hprof
$ docker cp user-service:/tmp/heap.hprof ./heap.hprof
# 然后用 MAT 或 VisualVM 分析

# 2. 拷贝线程 dump
$ docker exec user-service jcmd 1 Thread.print > thread_dump.txt

# 3. 拷贝容器内的配置文件来检查
$ docker cp user-service:/app/config.yml ./check-config.yml
```

#### `docker diff` —— 查看容器文件系统变更

```bash
# 语法
docker diff CONTAINER

# 查看容器相对于镜像的文件系统变化
$ docker diff user-service
C /app           # C = Changed（修改）
A /app/logs      # A = Added（新增）
A /app/logs/app.log
C /etc/localtime
D /tmp/old-file  # D = Deleted（删除）

# 排查场景：容器行为异常，检查是否有人修改了关键文件
$ docker diff my-app
C /app/config.yml    # 配置被修改了？
A /usr/bin/wget      # 被装了新软件？（可能被入侵）
```

---

### 1.2.4 网络与数据卷

#### 网络管理命令

```bash
# docker network create —— 创建自定义网络
$ docker network create --driver bridge app-network
# --driver 指定网络驱动，默认 bridge

# 创建指定子网的网络
$ docker network create --driver bridge --subnet 172.20.0.0/16 --gateway 172.20.0.1 app-network

# docker network ls —— 列出所有网络
$ docker network ls
NETWORK ID     NAME            DRIVER    SCOPE
a1b2c3d4e5f6   bridge          bridge    local
g7h8i9j0k1l2   host            host      local
m3n4o5p6q7r8   none            null      local
s9t0u1v2w3x4   app-network     bridge    local    ← 自定义网络

# docker network rm —— 删除网络
$ docker network rm app-network
# 注意：有容器使用中的网络不能删除

# docker network connect —— 将运行中的容器加入网络
$ docker network connect app-network user-service
# user-service 原来在默认 bridge，现在同时加入了 app-network
# 一个容器可以同时属于多个网络

# docker network disconnect —— 将容器从网络移除
$ docker network disconnect app-network user-service

# docker network inspect —— 查看网络详情
$ docker network inspect app-network
[
    {
        "Name": "app-network",
        "Driver": "bridge",
        "Subnet": "172.20.0.0/16",
        "Gateway": "172.20.0.1",
        "Containers": {
            "abc123...": {
                "Name": "user-service",
                "IPv4Address": "172.20.0.2/16"
            },
            "def456...": {
                "Name": "order-service",
                "IPv4Address": "172.20.0.3/16"
            }
        }
    }
]

# 实用场景：Java 微服务本地联调
# 1. 创建共享网络
$ docker network create microservice-net

# 2. 启动各个服务加入同一网络
$ docker run -d --name mysql --network microservice-net -e MYSQL_ROOT_PASSWORD=secret mysql:8.0
$ docker run -d --name redis --network microservice-net redis:7-alpine
$ docker run -d --name user-service --network microservice-net -p 8081:8080 myapp:latest
$ docker run -d --name order-service --network microservice-net -p 8082:8080 myapp:latest

# 3. Spring Boot 配置中用容器名作为主机名
# spring.datasource.url=jdbc:mysql://mysql:3306/mydb
# spring.redis.host=redis

# 4. 容器间互通验证
$ docker exec user-service curl -s http://order-service:8080/actuator/health
```

#### 数据卷管理命令

```bash
# docker volume create —— 创建数据卷
$ docker volume create app-data
app-data

# 创建时指定驱动和选项
$ docker volume create --driver local --opt type=nfs --opt o=addr=192.168.1.100,rw --opt device=:/data/nfs-share nfs-data

# docker volume ls —— 列出所有数据卷
$ docker volume ls
DRIVER    VOLUME NAME
local     app-data
local     app-logs
local     mysql-data

# 过滤悬空卷（没有被任何容器引用的卷）
$ docker volume ls -f "dangling=true"

# docker volume rm —— 删除数据卷
$ docker volume rm app-data
app-data

# docker volume inspect —— 查看数据卷详情
$ docker volume inspect mysql-data
[
    {
        "CreatedAt": "2024-01-15T10:30:00Z",
        "Driver": "local",
        "Mountpoint": "/var/lib/docker/volumes/mysql-data/_data",
        "Name": "mysql-data",
        "Options": {},
        "Scope": "local"
    }
]

# 数据卷备份（关键操作！）
# 方法1：用临时容器打包
$ docker run --rm \
  -v mysql-data:/source:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/mysql-data-backup.tar.gz -C /source .

# 方法2：直接从 Mountpoint 打包（需要 root 权限）
$ sudo tar czf mysql-data-backup.tar.gz -C /var/lib/docker/volumes/mysql-data/_data .

# 数据卷恢复
$ docker run --rm \
  -v mysql-data:/target \
  -v $(pwd):/backup \
  alpine sh -c "cd /target && tar xzf /backup/mysql-data-backup.tar.gz"
```

---

### 1.2.5 系统清理

```bash
# docker system prune —— 一键清理（最常用）
$ docker system prune
WARNING! This will remove:
  - all stopped containers
  - all networks not used by at least one container
  - all dangling images
  - all dangling build cache
Are you sure you want to continue? [y/N] y

# 彻底清理（包括未被容器使用的镜像和卷，谨慎使用！）
$ docker system prune -a --volumes
WARNING! This will remove:
  - all stopped containers
  - all networks not used by at least one container
  - all images without at least one container associated to them
  - all volumes not used by at least one container
  - all build cache
Are you sure? [y/N] y
Total reclaimed space: 5.2GB

# docker image prune —— 清理镜像
$ docker image prune                  # 清理悬空镜像（无标签的）
$ docker image prune -a               # 清理所有无容器使用的镜像
$ docker image prune -a --filter "until=48h"  # 清理48小时前创建的无容器使用的镜像

# docker volume prune —— 清理数据卷
$ docker volume prune                 # 清理未被容器引用的卷
$ docker volume prune --filter "label!=keep"  # 清理没有 keep 标签的卷

# docker container prune —— 清理容器
$ docker container prune              # 清理所有已停止的容器
$ docker container prune --filter "until=24h"  # 清理24小时前停止的容器

# 查看磁盘占用总览
$ docker system df
TYPE            TOTAL   ACTIVE  SIZE    RECLAIMABLE
Images          15      3       5.2GB   3.8GB (73%)
Containers      8       3       120MB   80MB (67%)
Local Volumes   5       2       1.5GB   800MB (53%)
Build Cache     50      0       2.1GB   2.1GB (100%)

# 查看详细占用
$ docker system df -v
Images space usage:
REPOSITORY     TAG      IMAGE ID       SIZE    SHARED   UNIQUE   CONTAINERS
openjdk        17-slim  2a1d7c4c5e8f   405MB   200MB    205MB    3
myapp          latest   5b6c7d8e9f0a   410MB   405MB    5MB      2
...
```

---

## 1.3 私有镜像仓库操作

### 1.3.1 登录认证

#### `docker login` —— 登录私有仓库

```bash
# 语法
docker login [OPTIONS] [SERVER]

# 登录 Docker Hub（默认）
$ docker login
Login with your Docker ID to push and pull images from Docker Hub.
Username: myusername
Password: ********
Login Succeeded

# 登录 Harbor 私有仓库
$ docker login harbor.company.com
Username: admin
Password: ********
Login Succeeded
# 认证信息保存在 ~/.docker/config.json

# 使用令牌登录（推荐，比密码更安全）
$ docker login harbor.company.com
Username: robot$project+robot-account    # Harbor 的机器人账号
Password: ***********                    # 机器人账号的令牌
Login Succeeded

# 查看/修改已保存的认证信息
$ cat ~/.docker/config.json
{
  "auths": {
    "harbor.company.com": {
      "auth": "YWRtaW46SGFyYm9yMTIzNDU="   # Base64 编码的 username:password
    },
    "https://index.docker.io/v1/": {
      "auth": "bXl1c2VybmFtZTpteXBhc3N3b3Jk"
    }
  }
}

# 登出
$ docker logout harbor.company.com
Removing login credentials for harbor.company.com
```

---

### 1.3.2 推送镜像完整流程

```bash
# ========== 典型场景：Java 服务构建并推送到 Harbor ==========

# 步骤1：构建镜像
$ docker build -t user-service:2.3.1 .

# 步骤2：按私有仓库规范打 tag
# 格式：registry地址/project/image:tag
$ docker tag user-service:2.3.1 harbor.company.com/dev/user-service:2.3.1
$ docker tag user-service:2.3.1 harbor.company.com/dev/user-service:latest

# 步骤3：登录私有仓库
$ docker login harbor.company.com
Username: admin
Password: ********
Login Succeeded

# 步骤4：推送镜像
$ docker push harbor.company.com/dev/user-service:2.3.1
The push refers to repository [harbor.company.com/dev/user-service]
5f70bf18a086: Pushed
a1b2c3d4e5f6: Pushed
2.3.1: digest: sha256:abc123... size: 2200

$ docker push harbor.company.com/dev/user-service:latest
The push refers to repository [harbor.company.com/dev/user-service]
5f70bf18a086: Layer already exists    # ← 已存在的层不重复上传
a1b2c3d4e5f6: Layer already exists
latest: digest: sha256:def456... size: 2200

# 步骤5：验证推送结果
$ curl -u admin:password -s https://harbor.company.com/v2/dev/user-service/tags/list | python3 -m json.tool
{
  "name": "dev/user-service",
  "tags": [
    "2.3.1",
    "latest"
  ]
}
```

---

### 1.3.3 拉取私有镜像

```bash
# 步骤1：登录（如果还没登录）
$ docker login harbor.company.com

# 步骤2：拉取镜像
$ docker pull harbor.company.com/dev/user-service:2.3.1
2.3.1: Pulling from dev/user-service
a2abf6c4d29d: Pull complete
716b0e4a5020: Pull complete
Digest: sha256:abc123...
Status: Downloaded newer image for harbor.company.com/dev/user-service:2.3.1

# 步骤3：验证
$ docker images | grep user-service
harbor.company.com/dev/user-service   2.3.1   5b6c7d8e9f0a   5 minutes ago   410MB

# 步骤4：运行
$ docker run -d --name user-service -p 8080:8080 harbor.company.com/dev/user-service:2.3.1
```

---

### 1.3.4 镜像 tag 命名规范

```text
标准格式：registry-host[:port]/project/image:tag

组成部分详解：

1. registry-host[:port]
   - Docker Hub: docker.io（默认，可省略）
   - Harbor: harbor.company.com
   - 阿里云 ACR: registry.cn-hangzhou.aliyuncs.com
   - AWS ECR: 123456789.dkr.ecr.us-east-1.amazonaws.com
   - 自建 Registry: registry.internal:5000

2. project（Harbor 中叫"项目"，Docker Hub 中叫"namespace"）
   - Harbor 项目名：dev / staging / prod
   - Docker Hub: your-docker-id 或 organization
   - 通常按团队或环境划分

3. image（镜像名/仓库名）
   - 微服务名：user-service / order-service / gateway
   - 基础设施：mysql / redis / nginx
   - 使用小写字母、数字、中划线，不用下划线

4. tag（标签）
   - 语义化版本：v2.3.1 / 2.3.1
   - Git commit：sha-a1b2c3d
   - 构建号：build-20240115-001
   - 环境标识：latest / stable / rc / dev
   - 推荐组合：v2.3.1-prod / v2.3.1-rc1

完整示例：
┌─────────────────────────────────────────────────────────────────┐
│ harbor.company.com / prod / user-service : v2.3.1              │
│ ─────────────────   ────  ─────────────   ──────               │
│ 仓库地址             项目   服务名          版本标签             │
└─────────────────────────────────────────────────────────────────┘

推荐的生产环境标签策略：
- 每次构建打 3 个 tag：
  1. v2.3.1         ← 精确版本，永不覆盖（可回溯）
  2. v2.3           ← 次版本，指向最新的 2.3.x（方便小版本升级）
  3. latest         ← 指向最新稳定版（开发/测试用，生产慎用）
```

---

### 1.3.5 常见认证问题排查

#### 问题1：x509 证书错误

```bash
# 现象：使用自签名证书的 Harbor，推送/拉取时报错
$ docker push harbor.company.com/dev/myapp:v1
The push refers to repository [harbor.company.com/dev/myapp]
Get https://harbor.company.com/v2/: x509: certificate signed by unknown authority

# 解决方案1（推荐）：将 CA 证书添加到系统信任链
$ sudo mkdir -p /etc/docker/certs.d/harbor.company.com
$ sudo cp harbor-ca.crt /etc/docker/certs.d/harbor.company.com/ca.crt
$ sudo systemctl restart docker

# 解决方案2：配置 insecure-registry（仅测试环境！）
$ sudo vi /etc/docker/daemon.json
{
  "insecure-registries": ["harbor.company.com"]
}
$ sudo systemctl restart docker

# 验证 insecure-registries 是否生效
$ docker info | grep -A5 "Insecure Registries"
Insecure Registries:
  harbor.company.com
  127.0.0.0/8
```

#### 问题2：daemon.json 配置示例

```bash
# /etc/docker/daemon.json 完整配置示例
$ sudo cat /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",          # 腾讯云镜像加速
    "https://registry.docker-cn.com"               # Docker 官方中国区镜像
  ],
  "insecure-registries": [
    "harbor.company.com",                          # 内网 Harbor（HTTP）
    "registry.internal:5000"                       # 内网简易 Registry
  ],
  "max-concurrent-downloads": 10,                  # 并行下载层数
  "max-concurrent-uploads": 5,                     # 并行上传层数
  "log-driver": "json-file",                       # 日志驱动
  "log-opts": {
    "max-size": "100m",                            # 单个日志文件最大 100MB
    "max-file": "3"                                # 最多保留 3 个日志文件
  },
  "storage-driver": "overlay2",                    # 存储驱动（推荐）
  "exec-opts": ["native.cgroupdriver=systemd"],    # cgroup 驱动（K8s 需要 systemd）
  "bip": "172.17.0.1/16",                         # docker0 网桥 IP
  "data-root": "/data/docker"                      # Docker 数据目录（默认 /var/lib/docker）
}

# 修改后重启
$ sudo systemctl daemon-reload
$ sudo systemctl restart docker
```

#### 问题3：其他常见认证错误

```bash
# 错误1：未登录
$ docker push harbor.company.com/dev/myapp:v1
unauthorized: authentication required
# 解决：docker login harbor.company.com

# 错误2：没有推送权限
$ docker push harbor.company.com/prod/myapp:v1
denied: requested access to the resource is denied
# 解决：在 Harbor Web 界面给用户/机器人账号授权该项目的推送权限

# 错误3：项目不存在
$ docker push harbor.company.com/nonexist/myapp:v1
repository name not known to registry
# 解决：先在 Harbor Web 界面创建项目（如 dev、prod）

# 错误4：登录凭证过期
$ docker push harbor.company.com/dev/myapp:v1
unauthorized: authentication required
# 即使之前登录过，token 也可能过期
# 解决：重新 docker login

# 错误5：HTTP 协议访问 HTTPS 仓库
$ docker pull harbor.company.com/dev/myapp:v1
http: server gave HTTP response to HTTPS client
# 解决：在 daemon.json 中添加 insecure-registries（见上方配置）
```

---

### 1.3.6 Harbor Web 界面操作要点

```text
Harbor 核心界面操作流程：

1. 创建项目
   导航：项目 → 新建项目
   - 项目名称：dev / staging / prod（通常按环境分）
   - 访问级别：
     ☐ 公开（Public）：任何人可拉取，无需登录
     ☑ 私有（Private）：必须登录才能拉取
   - 存储配额：限制项目总镜像大小

2. 用户与权限管理
   导航：项目 → [项目名] → 成员
   - 添加成员：输入用户名，选择角色
   - 角色权限：
     ┌────────────┬──────┬──────┬──────┬──────┬──────┐
     │ 操作       │访客  │开发者│Master│项目管理员│系统管理员│
     ├────────────┼──────┼──────┼──────┼──────┼──────┤
     │ 拉取镜像   │  ✓   │  ✓   │  ✓   │  ✓   │  ✓   │
     │ 推送镜像   │      │  ✓   │  ✓   │  ✓   │  ✓   │
     │ 删除镜像   │      │      │  ✓   │  ✓   │  ✓   │
     │ 管理成员   │      │      │      │  ✓   │  ✓   │
     │ 项目配置   │      │      │      │  ✓   │  ✓   │
     └────────────┴──────┴──────┴──────┴──────┴──────┘

3. 机器人账号（CI/CD 推荐使用）
   导航：项目 → [项目名] → 机器人账号 → 新建机器人账号
   - 名称：ci-push-bot
   - 权限：推送和拉取
   - 过期时间：30天/90天/永不过期
   - 创建后生成令牌，格式：机器人账号名 + 令牌
   - Docker login 使用：
     $ docker login harbor.company.com -u 'robot$dev+ci-push-bot' -p '令牌字符串'

4. 镜像管理
   导航：项目 → [项目名] → 仓库
   - 查看所有镜像及标签
   - 删除指定标签（支持按规则批量清理）
   - 查看镜像层详情、漏洞扫描结果
   - 设置标签保留策略：
     例如：每个镜像只保留最近 10 个标签，自动清理旧版本

5. 漏洞扫描
   导航：项目 → [项目名] → 配置 → 漏洞扫描
   - 集成 Trivy / Clair 扫描器
   - 推送时自动扫描
   - 阻止有严重漏洞的镜像被拉取（可配置）

6. 复制规则（多数据中心同步）
   导航：注册中心 → 新建规则
   - 源：harbor-cn.company.com/dev/*
   - 目标：harbor-us.company.com/dev/
   - 触发模式：事件驱动（推送时自动同步） / 定时
```

---

## 1.4 Java 开发者容器内调试

### 1.4.1 docker exec 进入容器查看 Java 进程

```bash
# 进入容器（最基本操作）
$ docker exec -it user-service /bin/bash

# 如果没有 bash（Alpine 镜像），用 sh
$ docker exec -it user-service /bin/sh

# 查看所有 Java 进程
$ docker exec user-service jps -l
1 my.company.UserServiceApplication
42 jdk.jcmd/sun.tools.jps.Jps

# 查看进程的完整命令行参数
$ docker exec user-service jps -v
1 my.company.UserServiceApplication -Xmx512m -Xms256m -Dspring.profiles.active=prod

# 查看进程的 JVM 参数
$ docker exec user-service jcmd 1 VM.flags
1:
-XX:CICompilerCount=2 -XX:InitialHeapSize=268435456 -XX:MaxHeapSize=536870912
-XX:+UseCompressedClassPointers -XX:+UseCompressedOops ...

# 查看所有系统进程
$ docker exec user-service ps aux
PID   USER     TIME  COMMAND
    1 root      0:05 java -jar /app/app.jar
   42 root      0:00 ps aux

# 查看进程的资源占用
$ docker exec user-service top -bn1
# -b 批处理模式，-n1 只输出一次
```

---

### 1.4.2 容器内 jps / jstat / jmap 使用

**核心问题：JRE 镜像中没有 JDK 诊断工具！**

```bash
# 问题重现：使用 JRE 镜像启动容器
$ docker run -d --name myapp eclipse-temurin:17-jre-alpine java -jar app.jar

# 尝试使用 jps 报错
$ docker exec myapp jps
OCI runtime exec failed: exec: "jps": executable file not found in $PATH

# 原因：jps、jstat、jmap 等工具属于 JDK，JRE 中不包含
```

**解决方案1：使用 JDK 镜像（最简单，但镜像体积大）**

```dockerfile
# 开发/测试环境可以用 JDK 镜像
FROM eclipse-temurin:17-jdk-alpine    # ~170MB 比 JRE 的 ~85MB 大一倍
COPY target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**解决方案2：在 JRE 镜像中临时安装 JDK 工具（运行时安装）**

```bash
# 基于 Debian 的镜像
$ docker exec -u root myapp apt-get update && apt-get install -y openjdk-17-jdk-headless

# 基于 Alpine 的镜像
$ docker exec -u root myapp apk add --no-cache openjdk17-jdk
```

**解决方案3：从宿主机使用 jcmd / jmap（推荐生产环境）**

```bash
# 容器内没有 JDK 工具，但宿主机有！
# 关键：找到容器内 Java 进程在宿主机上的 PID

# 步骤1：获取容器内 Java 进程在宿主机上的 PID
$ docker top myapp
UID    PID    PPID   C   STIME   TTY     TIME       CMD
root   12345  12330  2   10:30   ?       00:00:05   java -jar /app/app.jar
# ↑ PID 12345 就是宿主机上的进程号

# 步骤2：用宿主机的 jcmd 操作该 PID
$ jcmd 12345 VM.flags
$ jcmd 12345 GC.heap_info
$ jcmd 12345 Thread.print
$ jcmd 12345 GC.heap_dump /tmp/heap.hprof

# 注意：宿主机 JDK 版本需要与容器内 JDK 版本兼容
```

**解决方案4：使用 Docker 的 --pid=host 模式**

```bash
# 启动一个带 JDK 工具的调试容器，共享宿主机 PID 命名空间
$ docker run -it --rm --pid=host eclipse-temurin:17-jdk-alpine jcmd

# 可以看到宿主机上所有进程（包括其他容器中的 Java 进程）
# 然后可以对这些进程执行 jcmd 命令
```

**各诊断工具使用示例：**

```bash
# ========== jstat：JVM 统计监控 ==========
# 语法：jstat -<option> <pid> [interval] [count]

# 查看 GC 概况（最常用）
$ docker exec myapp jstat -gc 1
 S0C    S1C    S0U    S1U      EC       EU        OC         OU       MC     MU    CCSC   CCSU   YGC   YGCT   FGC  FGCT   GCT
 512.0  512.0   0.0   128.3   2048.0   1024.5    4096.0     2048.3   25600  24576  3072   2890   42    0.523   2    0.234   0.757
# S0C/S1C: Survivor 区容量    S0U/S1U: Survivor 区使用量
# EC: Eden 区容量             EU: Eden 区使用量
# OC: Old 区容量              OU: Old 区使用量
# MC: Metaspace 容量          MU: Metaspace 使用量
# YGC: Young GC 次数         YGCT: Young GC 总耗时
# FGC: Full GC 次数          FGCT: Full GC 总耗时
# GCT: GC 总耗时

# 每 1 秒采样一次，共 10 次（实时监控 GC）
$ docker exec myapp jstat -gc 1 1000 10

# 查看 GC 汇总信息
$ docker exec myapp jstat -gcutil 1
  S0     S1     E      O      M     CCS    YGC   YGCT   FGC  FGCT   GCT
  0.00  25.05  50.12  50.01  96.00  94.01   42   0.523   2    0.234  0.757
# 输出是百分比，更直观

# ========== jmap：堆内存分析 ==========
# 查看 Java 堆配置
$ docker exec myapp jmap -heap 1

# 查看堆中对象统计（按类统计实例数和占用空间）
$ docker exec myapp jmap -histo 1 | head -20
 num     #instances         #bytes  class name
   1:         45678       36542400  [B                    # byte 数组
   2:         23456       11234560  java.lang.String
   3:         12345        5678900  java.util.HashMap$Node
   ...

# 生成堆转储（Heap Dump）
$ docker exec myapp jmap -dump:format=b,file=/tmp/heap.hprof 1
Dumping heap to /tmp/heap.hprof ...
Heap dump file created

# 然后拷贝出来分析
$ docker cp myapp:/tmp/heap.hprof ./heap.hprof
# 用 Eclipse MAT 或 VisualVM 分析

# ========== jcmd：全能诊断工具（JDK 7+ 推荐） ==========
# 列出所有 Java 进程
$ docker exec myapp jcmd -l
1 my.company.UserServiceApplication

# 查看 JVM 命令行参数
$ docker exec myapp jcmd 1 VM.command_line

# 查看所有系统属性
$ docker exec myapp jcmd 1 VM.system_properties

# 线程转储
$ docker exec myapp jcmd 1 Thread.print -l

# 生成堆转储（比 jmap 更安全）
$ docker exec myapp jcmd 1 GC.heap_dump /tmp/heap.hprof

# 查看 JVM 旗标
$ docker exec myapp jcmd 1 VM.flags

# 查看 GC 配置
$ docker exec myapp jcmd 1 GC.heap_info
```

---

### 1.4.3 容器内网络调试

**问题：精简的 Java 镜像（如 Alpine-JRE）几乎没有网络调试工具。**

```bash
# 尝试 ping → 找不到命令
$ docker exec myapp ping mysql-svc
OCI runtime exec failed: exec: "ping": executable file not found

# 尝试 curl → 找不到命令
$ docker exec myapp curl http://user-svc:8080/health
OCI runtime exec failed: exec: "curl": executable file not found
```

**解决方案：临时安装网络工具**

```bash
# Alpine 镜像安装网络工具
$ docker exec -u root myapp apk add --no-cache curl bind-tools net-tools

# Debian/Ubuntu 镜像安装网络工具
$ docker exec -u root myapp apt-get update && apt-get install -y curl dnsutils net-tools iputils-ping
```

**各工具使用示例：**

```bash
# ========== curl：HTTP 请求测试 ==========
# 测试其他微服务的健康端点
$ docker exec myapp curl -s http://order-service:8080/actuator/health
{"status":"UP"}

# 测试带超时的请求
$ docker exec myapp curl -s --connect-timeout 5 --max-time 10 http://order-service:8080/api/orders

# 测试数据库连接（通过 Spring Boot Actuator）
$ docker exec myapp curl -s http://localhost:8080/actuator/health/db
{"status":"UP","details":{"database":"MySQL","validationQuery":"isValid()"}}

# 查看 HTTP 响应头（排查 CORS/重定向问题）
$ docker exec myapp curl -I http://order-service:8080/api/orders
HTTP/1.1 200
Content-Type: application/json
X-Application-Context: order-service:prod:8080

# ========== DNS 解析测试 ==========
# nslookup：验证容器名 DNS 解析（自定义 bridge 网络中）
$ docker exec myapp nslookup order-service
Server:    127.0.0.11                            # Docker 内置 DNS
Address 1: 127.0.0.11

Name:      order-service
Address 1: 172.20.0.3 order-service.app-network  # 解析到容器 IP

# dig：更详细的 DNS 查询
$ docker exec myapp dig order-service
;; ANSWER SECTION:
order-service.  600  IN  A  172.20.0.3

# 如果 nslookup 失败 → 可能不在同一个自定义网络中
# 默认 bridge 网络不支持容器名 DNS 解析！

# ========== netstat：查看网络连接 ==========
# 查看容器内所有监听端口
$ docker exec myapp netstat -tlnp
Active Internet connections (only servers)
Proto Recv-Q Send-Q Local Address    Foreign Address  State   PID/Program
tcp        0      0 0.0.0.0:8080     0.0.0.0:*        LISTEN  1/java
tcp        0      0 127.0.0.1:8005   0.0.0.0:*        LISTEN  1/java

# 查看所有已建立的连接
$ docker exec myapp netstat -tnp
Active Internet connections
Proto Recv-Q Send-Q Local Address    Foreign Address  State   PID/Program
tcp        0      0 172.20.0.2:8080  172.20.0.5:54321 ESTABLISHED 1/java
tcp        0      0 172.20.0.2:50123 172.20.0.3:3306  ESTABLISHED 1/java   # 连接 MySQL
tcp        0      0 172.20.0.2:50124 172.20.0.4:6379  ESTABLISHED 1/java   # 连接 Redis

# 大量 TIME_WAIT 连接？
$ docker exec myapp netstat -tnp | grep TIME_WAIT | wc -l
1250   # 可能需要调整连接池配置

# ========== ping：基础连通性测试 ==========
$ docker exec myapp ping -c 3 order-service
PING order-service (172.20.0.3): 56 data bytes
64 bytes from 172.20.0.3: seq=0 ttl=64 time=0.123 ms
64 bytes from 172.20.0.3: seq=1 ttl=64 time=0.098 ms
64 bytes from 172.20.0.3: seq=2 ttl=64 time=0.105 ms
--- order-service ping statistics ---
3 packets transmitted, 3 packets received, 0% packet loss
```

**不用安装工具的网络调试方法（纯 Java 方式）：**

```bash
# 使用 Java 自带的网络能力（JRE 中也有）
# 测试端口连通性
$ docker exec myapp java -cp /app/app.jar -e '
  import java.net.*;
  try {
    Socket s = new Socket("order-service", 8080);
    System.out.println("Connected to order-service:8080");
    s.close();
  } catch (Exception e) {
    System.out.println("Failed: " + e.getMessage());
  }'

# 更简单的方式：直接用 Shell 的 /dev/tcp（bash 内置功能）
$ docker exec myapp bash -c 'echo > /dev/tcp/order-service/8080 && echo "OK" || echo "FAIL"'
OK

$ docker exec myapp bash -c 'echo > /dev/tcp/mysql-svc/3306 && echo "OK" || echo "FAIL"'
OK
```

---

### 1.4.4 从容器内拷贝文件出来

```bash
# ========== 拷贝日志文件 ==========
# 拷贝单个日志文件
$ docker cp user-service:/app/logs/app.log ./app.log

# 拷贝整个日志目录
$ docker cp user-service:/app/logs/ ./logs-backup/

# ========== 拷贝 Heap Dump ==========
# 步骤1：在容器内生成 heap dump
$ docker exec user-service jcmd 1 GC.heap_dump /tmp/heap-$(date +%Y%m%d%H%M).hprof
Dumping heap to /tmp/heap-202401151030.hprof ...
Heap dump file created

# 步骤2：拷贝到宿主机
$ docker cp user-service:/tmp/heap-202401151030.hprof ./heap-202401151030.hprof

# 步骤3：用 MAT 或 VisualVM 分析

# ========== 拷贝线程 Dump ==========
# 直接输出到宿主机文件（不需要 docker cp）
$ docker exec user-service jcmd 1 Thread.print > thread-dump-$(date +%Y%m%d%H%M).txt

# ========== 拷贝 GC 日志 ==========
# 如果 JVM 启动参数中加了 -Xlog:gc*:file=/app/logs/gc.log
$ docker cp user-service:/app/logs/gc.log ./gc.log
# 用 GCEasy.io 或 GCViewer 分析

# ========== 拷贝 Spring Boot Actuator 数据 ==========
$ docker exec user-service curl -s http://localhost:8080/actuator/env > env-info.json
$ docker exec user-service curl -s http://localhost:8080/actuator/configprops > config-props.json
$ docker exec user-service curl -s http://localhost:8080/actuator/beans > beans-info.json

# ========== 拷贝容器内整个应用目录（应急排查） ==========
$ docker cp user-service:/app/ ./app-backup/
# 拷贝整个 /app 目录出来，包括配置、日志、临时文件等

# ========== 拷贝 JFR（Java Flight Recorder）录制文件 ==========
# 步骤1：启动 JFR 录制（持续 60 秒）
$ docker exec user-service jcmd 1 JFR.start duration=60s filename=/tmp/recording.jfr

# 步骤2：等待录制完成后拷贝
$ docker cp user-service:/tmp/recording.jprof ./recording.jfr

# 步骤3：用 JDK Mission Control 分析
```

---

### 1.4.5 实时查看容器资源占用

```bash
# ========== docker stats：基础监控 ==========

# 监控所有容器
$ docker stats
CONTAINER ID   NAME            CPU %   MEM USAGE / LIMIT   MEM %   NET I/O     BLOCK I/O   PIDS
a1b2c3d4       user-service    2.35%   384MiB / 1GiB      37.5%   1.2kB / 0B  50MB / 0B   42
g7h8i9j0       order-service   0.85%   256MiB / 512MiB    50.0%   850B / 0B   20MB / 0B   38

# 字段含义：
# CPU %       → 容器占用的 CPU 百分比（多核可能超过 100%）
# MEM USAGE   → 当前内存使用量
# LIMIT       → 容器内存限制（--memory 参数设置的值）
# MEM %       → 内存使用率 = MEM USAGE / LIMIT
# NET I/O     → 网络输入/输出流量
# BLOCK I/O   → 磁盘读写量
# PIDS        → 容器内的进程/线程数

# 只看一次（脚本采集用）
$ docker stats --no-stream

# 只监控特定容器
$ docker stats user-service order-service

# ========== 容器内 Java 专用监控 ==========

# 查看 JVM 内存使用（比 docker stats 更精确）
$ docker exec user-service jcmd 1 GC.heap_info
1:
 heap = 268435456(256M),  used = 134217728(128M)
 eden = 67108864(64M),   100% used
 survivor = 8388608(8M), 50% used
 old = 192937984(184M),  33% used
 Metaspace = 256M,  used = 245M

# 查看 JVM 各内存池使用情况
$ docker exec user-service jstat -gcutil 1
  S0     S1     E      O      M     CCS    YGC   YGCT   FGC  FGCT   GCT
  0.00  25.05  99.12  33.01  96.00  94.01   42   0.523   2   0.234  0.757

# ========== 常见问题排查 ==========

# 问题1：容器内存持续增长，可能内存泄漏
$ docker stats --no-stream user-service
# 记录 MEM USAGE → 等 30 分钟 → 再次查看 → 持续增长 → 疑似泄漏
# 下一步：生成 heap dump 对比

# 问题2：CPU 飙高
$ docker top user-service -H
# 找到 CPU 占用最高的线程 PID
# 然后用 jstack 查看该线程在做什么
$ docker exec user-service jstack 1 | grep -A20 "nid=0x$(printf '%x' 12346)"
# 12346 是宿主机上的线程 PID，转十六进制后在 jstack 输出中搜索

# 问题3：频繁 Full GC
$ docker exec user-service jstat -gcutil 1 1000 5
  S0     S1     E      O      M     CCS    YGC   YGCT   FGC  FGCT   GCT
  0.00  25.05  50.12  85.01  96.00  94.01   42   0.523   2   0.234  0.757
  0.00  45.15  60.20  88.23  96.00  94.01   43   0.535   2   0.234  0.769
  0.00  15.30  70.35  92.10  96.00  94.01   44   0.548   3   0.356  0.904  ← FGC+1
  0.00  55.40  80.45  95.80  96.00  94.01   45   0.561   4   0.478  1.039  ← FGC+1
  0.00  35.50  90.55  98.50  96.00  94.01   46   0.574   5   0.600  1.174  ← FGC+1
# 老年代（O列）持续增长到 98.5%，Full GC 间隔越来越短 → 内存不足
# 解决：增大 -Xmx 或排查内存泄漏

# 问题4：容器被 OOM Kill
$ docker inspect user-service --format '{{.State.OOMKilled}}'
true
# OOM Kill = 容器进程使用的总内存超过了 --memory 限制
# 注意：不是 JVM OOM，是 Linux 内核杀掉了进程
# JVM OOM：java.lang.OutOfMemoryError → 应用还能运行
# OOM Kill：进程直接被杀 → docker ps 显示 Exited (137)

# 排查步骤：
# 1. 查看 docker stats 中的 MEM USAGE 是否接近 LIMIT
# 2. 检查 -Xmx 与 --memory 的比例（建议 --memory ≥ 1.5 × -Xmx）
# 3. 检查是否有大量堆外内存使用（DirectByteBuffer、JNI、线程栈）
# 4. 查看 dmesg 确认 OOM Kill 记录
$ dmesg | grep -i "oom"
[12345.678] java invoked oom-killer: gfp_mask=0x...
[12345.679] Task java (pid 12345) was killed
```

**JVM 容器内存配置最佳实践总结：**

```bash
# 关键参数说明：
# -XX:MaxRAMPercentage=75.0    ← 让 JVM 自动根据容器内存限制计算堆大小（推荐）
#   容器限制 1GB → 堆 ≈ 750MB，剩余 250MB 给非堆
# -XX:InitialRAMPercentage=50.0 ← 初始堆大小

# 推荐的 Java 容器启动命令
$ docker run -d \
  --name user-service \
  -m 1g \                                            # 容器内存限制 1GB
  --memory-swap 1g \                                 # 禁用 swap（与 -m 相同 = 无 swap）
  -e JAVA_OPTS="-XX:MaxRAMPercentage=75.0 -XX:InitialRAMPercentage=50.0 -XX:+UseContainerSupport" \
  myapp:latest

# -XX:+UseContainerSupport（JDK 10+ 默认开启）
#   让 JVM 感知容器的内存限制，而不是看宿主机的总内存
#   没有此参数时，JVM 可能按宿主机 64GB 内存来算堆大小 → 超过容器限制 → OOM Kill

# 常见错误配置：
# 错误1：-Xmx1g 但容器限制 -m 512m → JVM 堆 + 非堆 > 512m → OOM Kill
# 错误2：-Xmx512m -m 512m → 非堆（Metaspace、线程栈、直接内存）无空间 → OOM Kill
# 正确：-Xmx512m -m 1g 或 -XX:MaxRAMPercentage=50.0 -m 1g
```

---

# 第二章：Dockerfile 详解（Java 服务专用）

## 2.1 Dockerfile 每条指令详解

### FROM

**语法：**

```dockerfile
FROM [--platform=<platform>] <image>[:<tag>] [AS <name>]
```

**作用：** 指定基础镜像，是 Dockerfile 中唯一必须存在的指令。每个 Dockerfile 必须以 `FROM` 开头（`ARG` 除外，`ARG` 可以出现在 `FROM` 之前）。

**注意事项：**
- 在多阶段构建中，可以有多个 `FROM`，每个 `FROM` 开始一个新的构建阶段
- `AS <name>` 为阶段命名，后续阶段可通过 `COPY --from=<name>` 引用
- `--platform` 用于指定平台架构，如 `linux/amd64`、`linux/arm64`，在跨平台构建时使用
- 如果不指定 tag，默认使用 `latest`，生产环境**必须**指定明确版本号

**Java 场景示例代码：**

```dockerfile
# 单阶段构建：直接使用 JRE 运行镜像
FROM eclipse-temurin:8-jre-alpine

# 多阶段构建：阶段一，Maven 编译
FROM maven:3.9-eclipse-temurin-8 AS builder
# 此阶段的指令...
COPY pom.xml /app/
COPY src /app/src/
RUN mvn package -DskipTests

# 多阶段构建：阶段二，JRE 运行
FROM eclipse-temurin:8-jre-alpine
# 只从 builder 阶段拷贝构建产物
COPY --from=builder /app/target/*.jar /app/app.jar
```

```dockerfile
# ARG 可以出现在 FROM 之前，用于参数化基础镜像版本
ARG JAVA_VERSION=8
FROM eclipse-temurin:${JAVA_VERSION}-jre-alpine
```

---

### RUN

**语法：**

```dockerfile
# Shell 格式：命令通过 /bin/sh -c 执行
RUN <command>

# Exec 格式：直接执行，不经过 shell
RUN ["executable", "param1", "param2"]
```

**作用：** 在当前镜像层之上执行命令，并创建新的镜像层。执行结果会被 `docker commit` 提交到镜像中。

**注意事项：**
- **Shell 格式**会通过 `/bin/sh -c` 执行，支持管道 `|`、重定向 `>`、变量替换 `$VAR` 等 shell 特性
- **Exec 格式**直接调用可执行文件，不启动 shell，因此不支持 shell 特性；如果需要 shell 特性，可以写成 `RUN ["/bin/sh", "-c", "echo $HOME"]`
- **缓存层影响：** `RUN` 指令的缓存会在指令文本未改变时复用。但如果 `RUN apt-get install` 这类命令，即使文本不变，软件源可能已更新，导致安装结果不同但缓存被错误复用。解决方案：在命令末尾清除包管理器缓存
- **合并 RUN 减少 layers：** 每个 `RUN` 创建一层，层数过多会增加镜像体积。应将相关命令用 `&&` 合并为一条 `RUN`，并使用 `\` 换行保持可读性

**Java 场景示例代码：**

```dockerfile
# ====== Shell 格式 ======
RUN echo "Hello from shell format"

# ====== Exec 格式 ======
RUN ["/bin/echo", "Hello from exec format"]

# ====== 错误示范：多层 RUN，每一层都会增加镜像体积 ======
RUN apk add --no-cache tzdata
RUN apk add --no-cache curl
RUN cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
RUN echo "Asia/Shanghai" > /etc/timezone
RUN apk del tzdata
# 结果：5 个中间层，每层都保留文件变更，即使后续层删除了文件，
#       前面层的文件仍然占用空间（Docker 层是增量的，删除只是标记删除）

# ====== 正确示范：合并 RUN，一层搞定 ======
RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata
# 结果：只有 1 个中间层，安装和删除在同一层完成，不浪费空间

# ====== Java 场景：安装字体和时区 ======
RUN set -eux \
    && apk add --no-cache tzdata fontconfig ttf-dejavu \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata
# set -eux 的作用：
#   -e：命令失败时立即退出（防止部分失败继续执行）
#   -u：使用未定义变量时报错
#   -x：打印每条执行的命令（方便调试）
```

---

### COPY vs ADD

**语法：**

```dockerfile
COPY [--chown=<user>:<group>] <src>... <dest>
COPY [--chown=<user>:<group>] ["<src>",..., "<dest>"]

ADD [--chown=<user>:<group>] <src>... <dest>
ADD [--chown=<user>:<group>] ["<src>",..., "<dest>"]
```

**作用：** 将文件从构建上下文（宿主机）拷贝到镜像中。

**区别详解：**

| 特性 | COPY | ADD |
|------|------|-----|
| 基本文件拷贝 | ✅ | ✅ |
| 自动解压 tar 归档 | ❌ | ✅（自动解压 .tar/.tar.gz/.tar.xz 等） |
| 从远程 URL 下载 | ❌ | ✅（但**不推荐使用**） |
| 多阶段构建 COPY --from | ✅ | ❌（ADD 不支持 --from） |
| 推荐程度 | ⭐⭐⭐ 推荐 | ⭐ 不推荐（行为容易混淆） |

**注意事项：**
- **ADD 的自动解压**：当源文件是 tar 归档时，`ADD` 会自动解压到目标目录。这个"隐式行为"容易导致意外，所以 Docker 官方推荐使用 `COPY`，如果需要解压，显式使用 `RUN tar` 命令
- **ADD 的远程 URL**：`ADD http://example.com/file.txt /app/` 可以从 URL 下载文件，但这会导致构建不可复现（远程文件可能变化），且不会自动解压。推荐使用 `RUN curl` 或 `RUN wget` 替代
- **COPY 的 --chown 参数**：`COPY --chown=appuser:appgroup app.jar /app/`，在拷贝的同时设置文件属主，避免后续用 `RUN chown` 多建一层
- **路径尾部斜杠**：目标路径有 `/` 表示目录，没有 `/` 且不存在则作为文件名

**Java 场景示例代码：**

```dockerfile
# ====== 拷贝 JAR 包（推荐使用 COPY） ======
COPY target/app.jar /app/app.jar

# ====== ADD 的自动解压行为演示（不推荐，但需要了解） ======
# 假设构建上下文中有 app.tar.gz
ADD app.tar.gz /app/
# 结果：app.tar.gz 被自动解压到 /app/ 目录下
# 注意：这是 ADD 唯一比 COPY 多的功能，但行为隐式，不推荐

# ====== 如果需要解压，显式使用 RUN（推荐） ======
COPY app.tar.gz /tmp/
RUN tar -xzf /tmp/app.tar.gz -C /app/ && rm /tmp/app.tar.gz
# 结果：行为明确，且可以在同一层清理临时文件

# ====== 使用 --chown 在拷贝时设置属主（推荐） ======
COPY --chown=1001:1001 target/app.jar /app/app.jar
# 等价于：
# COPY target/app.jar /app/app.jar
# RUN chown 1001:1001 /app/app.jar
# 但 --chown 方式不创建额外的镜像层

# ====== 多阶段构建中的 COPY --from ======
COPY --from=builder /app/target/*.jar /app/app.jar
# 注意：ADD 不支持 --from 参数
```

---

### ENV

**语法：**

```dockerfile
ENV <key>=<value> ...
ENV <key> <value>  # 旧格式，只支持单个变量
```

**作用：** 设置环境变量，在镜像构建时和容器运行时都可用。环境变量会持久化到镜像中。

**注意事项：**
- 新格式 `ENV KEY=VALUE` 支持一行设置多个变量：`ENV TZ=Asia/Shanghai LANG=C.UTF-8`
- 在 Dockerfile 中后续指令可通过 `$KEY` 或 `${KEY}` 引用
- 运行时可通过 `docker run -e KEY=NEW_VALUE` 或 `docker run --env-file` 覆盖
- ENV 设置的值会**持久化到镜像**，不会因为 `docker run -e` 覆盖而改变镜像中的默认值
- 敏感信息（密码、密钥）**不要**用 ENV 设置，应使用 `docker run -e` 运行时传入或 Docker Secrets

**Java 场景示例代码：**

```dockerfile
# ====== 设置 Java 常用环境变量 ======
ENV JAVA_OPTS="-Xms512m -Xmx512m" \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8

# ====== 在后续指令中引用 ENV ======
ENV APP_HOME=/app
WORKDIR $APP_HOME           # WORKDIR /app
COPY app.jar $APP_HOME/     # 拷贝到 /app/

# ====== 运行时覆盖 ENV ======
# 构建时设置的默认值：
ENV JAVA_OPTS="-Xms512m -Xmx512m"

# 运行时可以覆盖：
# docker run -e JAVA_OPTS="-Xms1g -Xmx1g" myapp
# 容器内的 JAVA_OPTS 将是 "-Xms1g -Xmx1g"

# ====== 在 ENTRYPOINT 中使用 ENV ======
ENV JAVA_OPTS="-Xms512m -Xmx512m"
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar /app/app.jar"]
# 注意：exec 格式的 ENTRYPOINT/CMD 不会自动做变量替换，
#       需要通过 sh -c 来触发 shell 变量替换
```

---

### ARG

**语法：**

```dockerfile
ARG <name>[=<default value>]
```

**作用：** 定义构建时变量，仅在 `docker build` 阶段可用，**不会**持久化到镜像中。

**注意事项：**
- ARG 与 ENV 的关键区别：

| 特性 | ARG | ENV |
|------|-----|-----|
| 可用阶段 | 仅构建时 | 构建时 + 运行时 |
| 持久化到镜像 | ❌ | ✅ |
| 运行时可访问 | ❌ | ✅ |
| docker run 时覆盖 | ❌ | ✅（用 -e） |
| docker build 时传入 | ✅（用 --build-arg） | ❌ |
| 安全性 | 稍好（不留在镜像中） | 较差（留在镜像中） |

- ARG 在 `FROM` 之前声明的变量，只能在 `FROM` 指令中使用
- ARG 在 `FROM` 之后声明的变量，只能在当前构建阶段使用
- 不要用 ARG 传递密码等敏感信息，因为 `docker history` 可以看到构建参数

**Java 场景示例代码：**

```dockerfile
# ====== ARG 在 FROM 之前：参数化基础镜像版本 ======
ARG JAVA_VERSION=8
ARG IMAGE_TAG=jre-alpine
FROM eclipse-temurin:${JAVA_VERSION}-${IMAGE_TAG}

# ====== ARG 在 FROM 之后：参数化构建信息 ======
ARG APP_VERSION=1.0.0
ARG BUILD_DATE

# ARG 不会持久化，如果运行时也需要，需要配合 ENV
ARG APP_VERSION=1.0.0
ENV APP_VERSION=${APP_VERSION}
# 这样构建时可以通过 --build-arg 传入，运行时也能通过 ENV 读取

# ====== 构建时传入 ARG ======
# docker build --build-arg JAVA_VERSION=17 --build-arg APP_VERSION=2.0.0 -t myapp .

# ====== 使用 ARG 设置 LABEL ======
ARG BUILD_DATE
ARG VCS_REF
LABEL build-date=$BUILD_DATE \
      vcs-ref=$VCS_REF
# docker build --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
#              --build-arg VCS_REF=$(git rev-parse --short HEAD) \
#              -t myapp .
```

---

### WORKDIR

**语法：**

```dockerfile
WORKDIR /path/to/workdir
```

**作用：** 设置后续 `RUN`、`CMD`、`ENTRYPOINT`、`COPY`、`ADD` 指令的工作目录。

**注意事项：**
- 如果目录不存在，Docker 会自动创建
- 可以多次使用，每次都是基于上一次的路径（相对路径会拼接）
- 推荐使用绝对路径，避免混淆
- **不要**使用 `RUN cd /app && ...` 代替 WORKDIR，因为 `RUN cd` 只在当前 RUN 指令内生效

**Java 场景示例代码：**

```dockerfile
# ====== 设置应用工作目录 ======
WORKDIR /app
# 后续的 COPY、RUN 等都在 /app 下执行
COPY app.jar .
# 等价于 COPY app.jar /app/app.jar

# ====== WORKDIR 的路径拼接 ======
WORKDIR /a
WORKDIR b
WORKDIR c
RUN pwd
# 输出：/a/b/c

# ====== 错误示范 ======
RUN cd /app               # cd 只在当前 RUN 层生效
COPY app.jar .            # 此时工作目录不是 /app！而是 FROM 镜像的默认目录

# ====== 正确做法 ======
WORKDIR /app
COPY app.jar .            # 拷贝到 /app/app.jar
```

---

### EXPOSE

**语法：**

```dockerfile
EXPOSE <port>[/<protocol>]
```

**作用：** 声明容器运行时监听的端口。**这只是文档作用，不会实际发布端口。**

**注意事项：**
- `EXPOSE` 仅仅是声明，告诉使用者这个容器会使用哪些端口，**不会**自动在运行时发布端口
- 实际发布端口需要在 `docker run` 时使用 `-p` 参数：`docker run -p 8080:8080 myapp`
- `EXPOSE` 指定的端口在 `docker run -P`（大写 P）时会自动映射到宿主机随机端口
- 可以指定协议：`EXPOSE 8080/tcp`（默认 tcp）、`EXPOSE 53/udp`
- 即使没有 EXPOSE，用 `-p` 也能发布端口；即使有 EXPOSE，不用 `-p` 也不会发布

**Java 场景示例代码：**

```dockerfile
# ====== Spring Boot 应用暴露端口 ======
EXPOSE 8080

# ====== 同时暴露 HTTP 和管理端口 ======
EXPOSE 8080 8081

# ====== 指定 UDP 协议 ======
EXPOSE 53/udp

# ====== 运行时发布端口 ======
# docker run -p 8080:8080 myapp      # 将容器 8080 映射到宿主机 8080
# docker run -P myapp                # 自动将所有 EXPOSE 的端口映射到宿主机随机高端口
```

---

### VOLUME

**语法：**

```dockerfile
VOLUME ["/data"]
VOLUME /data
```

**作用：** 声明一个数据卷挂载点。在容器运行时，该路径会自动挂载为匿名卷。

**注意事项：**
- `VOLUME` 声明的目录，在容器运行时 Docker 会自动创建一个匿名卷挂载到该路径
- 如果 `docker run -v /host/path:/data`，则宿主机目录会覆盖匿名卷
- `VOLUME` 的主要目的是告诉使用者：这个目录包含持久化数据，容器删除后数据不应丢失
- Dockerfile 中的 `VOLUME` 声明后，该目录的任何后续 `RUN` 指令的修改都不会生效（因为运行时会被卷覆盖）
- **Java 场景注意**：如果 Spring Boot 应用写日志到 `/app/logs`，可以声明为 VOLUME，但不一定要在 Dockerfile 中声明，更推荐在 `docker run` 时用 `-v` 挂载

**Java 场景示例代码：**

```dockerfile
# ====== 声明日志目录为数据卷 ======
VOLUME ["/app/logs"]

# ====== 运行时挂载 ======
# docker run -v /var/log/myapp:/app/logs myapp
# 将宿主机 /var/log/myapp 挂载到容器 /app/logs

# ====== 注意：VOLUME 后的 RUN 修改不会持久化 ======
VOLUME ["/app/data"]
RUN echo "hello" > /app/data/test.txt
# ⚠️ 运行时 /app/data 会被匿名卷覆盖，test.txt 不会存在！
# 正确做法：通过初始化脚本在容器启动时写入
```

---

### USER

**语法：**

```dockerfile
USER <user>[:<group>]
USER <UID>[:<GID>]
```

**作用：** 设置后续 `RUN`、`CMD`、`ENTRYPOINT` 指令的运行用户。

**注意事项：**
- 使用 USER 切换到非 root 用户是**安全最佳实践**
- 需要先创建用户和组（通过 `RUN adduser` 或 `RUN useradd`）
- 确保用户对工作目录和文件有足够的权限
- `COPY --chown` 可以在拷贝文件时设置属主，避免后续 `RUN chown` 额外创建层

**Java 场景示例代码：**

```dockerfile
# ====== Alpine 镜像创建非 root 用户 ======
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
# -S: 创建系统用户/组
# Alpine 使用 adduser/addgroup（BusyBox 实现）

# ====== Debian/Ubuntu 镜像创建非 root 用户 ======
RUN groupadd -r appgroup && useradd -r -g appgroup appuser
# -r: 创建系统用户/组
# Debian/Ubuntu 使用 groupadd/useradd

# ====== 设置文件属主并切换用户 ======
WORKDIR /app
COPY --chown=appuser:appgroup app.jar app.jar
USER appuser
# 后续的 RUN、CMD、ENTRYPOINT 都以 appuser 身份运行

# ====== 验证当前用户 ======
USER appuser
RUN whoami   # 输出: appuser
```

---

### HEALTHCHECK

**语法：**

```dockerfile
HEALTHCHECK [OPTIONS] CMD command
HEALTHCHECK NONE   # 禁用健康检查
```

**OPTIONS：**
- `--interval=DURATION`：检查间隔，默认 30s
- `--timeout=DURATION`：超时时间，默认 30s
- `--start-period=DURATION`：容器启动后等待多久开始检查，默认 0s
- `--retries=N`：连续失败多少次才标记为 unhealthy，默认 3

**作用：** 配置容器健康检查。Docker 会定期执行检查命令，根据退出码判断容器状态：
- 0：healthy
- 1：unhealthy
- 2：reserved（不要使用）

**注意事项：**
- 健康检查命令应该是轻量级的，不要执行耗时操作
- Spring Boot 应用可以用 `curl` 或 `wget` 请求 actuator 健康端点
- Alpine 镜像默认没有 `curl`，需要安装或使用 `wget`

**Java 场景示例代码：**

```dockerfile
# ====== 使用 wget 检查 Spring Boot Actuator（Alpine 镜像） ======
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD wget -qO- http://localhost:8080/actuator/health || exit 1
# --interval=30s: 每 30 秒检查一次
# --timeout=3s: 超时 3 秒视为失败
# --start-period=60s: 容器启动后 60 秒内不计入失败次数（给 JVM 预热时间）
# --retries=3: 连续 3 次失败标记为 unhealthy
# wget -qO-: 静默模式，输出到 stdout，失败时退出码非 0

# ====== 使用 curl 检查（Debian 镜像） ======
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/actuator/health || exit 1
# curl -f: HTTP 错误码时返回非 0 退出码

# ====== 禁用从基础镜像继承的健康检查 ======
HEALTHCHECK NONE

# ====== 查看健康状态 ======
# docker inspect --format='{{.State.Health.Status}}' <container_id>
# 输出: healthy / unhealthy / starting
```

---

### LABEL

**语法：**

```dockerfile
LABEL <key>=<value> <key>=<value> ...
```

**作用：** 为镜像添加元数据标签，用于描述、组织、搜索镜像。

**注意事项：**
- 推荐使用一个 LABEL 指令设置多个标签，减少镜像层数
- 常用标签遵循 OCI 标准或自定义约定
- 可通过 `docker inspect` 查看标签
- 替代了已弃用的 `MAINTAINER` 指令

**Java 场景示例代码：**

```dockerfile
# ====== 标准元数据标签 ======
LABEL maintainer="team@example.com" \
      version="1.0.0" \
      description="Spring Boot 微服务 - 用户服务" \
      org.opencontainers.image.title="user-service" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.description="用户管理微服务" \
      org.opencontainers.image.source="https://github.com/example/user-service" \
      org.opencontainers.image.vendor="Example Corp"

# ====== 配合 ARG 动态设置 ======
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION
LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.version=$VERSION
# docker build \
#   --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
#   --build-arg VCS_REF=$(git rev-parse --short HEAD) \
#   --build-arg VERSION=1.0.0 \
#   -t myapp .

# ====== 查看标签 ======
# docker inspect --format='{{.Config.Labels}}' myapp
# docker image inspect myapp --format='{{json .Config.Labels}}' | python -m json.tool
```

---

### STOPSIGNAL

**语法：**

```dockerfile
STOPSIGNAL <signal>
```

**作用：** 设置停止容器时发送的系统信号，默认是 `SIGTERM`。

**注意事项：**
- `docker stop` 会先发送 STOPSIGNAL 指定的信号，等待超时后发送 `SIGKILL`
- Java 应用默认会注册 `SIGTERM` 的 ShutdownHook，收到信号后优雅关闭
- 如果使用 `SIGINT`（2），相当于 Ctrl+C
- 一般不需要修改，保持默认的 `SIGTERM` 即可

**Java 场景示例代码：**

```dockerfile
# ====== 默认行为（通常不需要修改） ======
STOPSIGNAL SIGTERM
# docker stop 发送 SIGTERM，Spring Boot 的 ShutdownHook 会执行清理
# 等待 10 秒（默认）后发送 SIGKILL 强制终止

# ====== 如果需要修改停止信号 ======
STOPSIGNAL SIGINT
# SIGINT 等同于 Ctrl+C，某些场景下可能更合适

# ====== 配合 docker stop 的超时设置 ======
# docker stop -t 30 <container_id>
# 等待 30 秒后才发送 SIGKILL，给 Java 应用更多时间优雅关闭
```

---

### ENTRYPOINT vs CMD（重点！）

这是 Dockerfile 中最容易混淆的两个指令，也是面试高频考点。

#### 语法区别

```dockerfile
# ====== ENTRYPOINT 语法 ======
# Exec 格式（推荐）：
ENTRYPOINT ["executable", "param1", "param2"]

# Shell 格式：
ENTRYPOINT command param1 param2

# ====== CMD 语法 ======
# Exec 格式（推荐）：
CMD ["executable", "param1", "param2"]

# Shell 格式：
CMD command param1 param2

# 作为 ENTRYPOINT 的默认参数：
CMD ["param1", "param2"]
```

#### 核心区别

| 特性 | ENTRYPOINT | CMD |
|------|-----------|-----|
| 定位 | 容器的**主命令** | 容器的**默认命令/默认参数** |
| `docker run` 传参行为 | 传的参数**追加**到 ENTRYPOINT 后 | 传的参数**替换**整个 CMD |
| 是否可被覆盖 | 需 `--entrypoint` 才能覆盖 | `docker run` 末尾参数直接覆盖 |
| 存在意义 | 定义容器"是什么" | 定义容器"默认做什么" |

#### docker run 传参行为详解

```dockerfile
# 假设 Dockerfile 中：
ENTRYPOINT ["java", "-jar", "app.jar"]
CMD ["--spring.profiles.active=dev"]
```

```bash
# 场景 1：不传参
docker run myapp
# 实际执行：java -jar app.jar --spring.profiles.active=dev
# CMD 作为默认参数追加到 ENTRYPOINT 后

# 场景 2：传入参数
docker run myapp --spring.profiles.active=prod
# 实际执行：java -jar app.jar --spring.profiles.active=prod
# 传入的参数替换了 CMD 的默认值

# 场景 3：覆盖 ENTRYPOINT
docker run --entrypoint sh myapp
# 实际执行：sh
# 原来的 ENTRYPOINT 和 CMD 都被替换
```

```dockerfile
# 假设 Dockerfile 中只有 CMD：
CMD ["java", "-jar", "app.jar"]
```

```bash
# 场景 1：不传参
docker run myapp
# 实际执行：java -jar app.jar

# 场景 2：传入参数
docker run myapp --spring.profiles.active=prod
# 实际执行：--spring.profiles.active=prod
# ⚠️ 整个 CMD 被替换！java 命令都没了，会报错！
# 因为 docker run 后面的参数会替换整个 CMD
```

#### 组合使用的 3 种模式

**模式一：ENTRYPOINT + CMD（推荐）**

```dockerfile
# ENTRYPOINT 定义不变的执行程序，CMD 定义可覆盖的默认参数
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--spring.profiles.active=dev"]
# 用户可以通过 docker run myapp --spring.profiles.active=prod 覆盖 CMD 部分
# 而 java -jar /app/app.jar 始终保留
```

**模式二：仅 ENTRYPOINT**

```dockerfile
# 适用于不希望用户随意修改执行命令的场景
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
# docker run myapp 的任何参数都会追加到 java -jar /app/app.jar 后面
# 注意：如果用户不传参数，容器会以默认配置启动，没有"默认参数"的概念
```

**模式三：仅 CMD**

```dockerfile
# 适用于简单场景，灵活性最高
CMD ["java", "-jar", "/app/app.jar"]
# docker run myapp some-command 会完全替换 CMD
# ⚠️ 风险：用户可能不小心覆盖了整个启动命令
```

#### Java 服务推荐用法

```dockerfile
# ====== 推荐方式一：ENTRYPOINT + CMD（最灵活） ======
ENTRYPOINT ["java"]
CMD ["-jar", "/app/app.jar"]
# 优点：用户可以在运行时灵活追加 JVM 参数
# docker run myapp -Xmx1g -jar /app/app.jar --spring.profiles.active=prod

# ====== 推荐方式二：使用 shell 脚本作为 ENTRYPOINT（最实用） ======
COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--spring.profiles.active=dev"]
# entrypoint.sh 内容：
# #!/bin/sh
# exec java $JAVA_OPTS -jar /app/app.jar "$@"
# 优点：
#   1. JAVA_OPTS 环境变量可在运行时动态设置 JVM 参数
#   2. "$@" 接收 CMD 或 docker run 传入的参数
#   3. exec 确保 java 进程成为 PID 1，正确接收信号

# ====== entrypoint.sh 完整示例 ======
```

```bash
#!/bin/sh
# entrypoint.sh - Java 应用启动脚本

# 如果设置了 JAVA_OPTS 环境变量，则使用它
# 否则使用默认值
: "${JAVA_OPTS:=-Xms512m -Xmx512m -XX:+UseG1GC}"

# exec 的作用：用 java 进程替换当前 shell 进程
# 这样 java 进程成为 PID 1，能正确接收 SIGTERM 信号实现优雅关闭
# 如果不用 exec，shell 是 PID 1，java 是子进程，
# docker stop 时 shell 收到 SIGTERM 但不会转发给 java
exec java ${JAVA_OPTS} -jar /app/app.jar "$@"
# "$@" 展开为所有传入的参数，如 CMD 中的 --spring.profiles.active=dev
```

#### 完整对比表格

| 对比项 | ENTRYPOINT | CMD |
|--------|-----------|-----|
| **作用** | 定义容器主命令 | 定义默认命令或默认参数 |
| **Exec 格式** | `["exec", "p1"]` | `["exec", "p1"]` 或 `["p1"]` |
| **Shell 格式** | `exec p1` | `exec p1` |
| **docker run 传参** | 追加到 ENTRYPOINT 后 | 替换整个 CMD |
| **覆盖方式** | `--entrypoint` | docker run 末尾参数 |
| **Dockerfile 中多个** | 只有最后一个生效 | 只有最后一个生效 |
| **Shell 格式问题** | 不会成为 PID 1 | 不会成为 PID 1 |
| **Java 推荐用法** | `["java"]` 或启动脚本 | 默认参数 |
| **信号处理** | Exec 格式可接收 SIGTERM | Exec 格式可接收 SIGTERM |

---

## 2.2 Java 基础镜像选择

### 主流 Java 基础镜像对比

| 镜像 | 维护方 | 特点 | 适用场景 |
|------|--------|------|----------|
| **openjdk** | Oracle/Docker Hub | 官方镜像，但已停止更新（Java 8/11 后不再维护新版本） | 旧项目，不推荐新项目使用 |
| **eclipse-temurin** | Eclipse Adoptium（原 AdoptOpenJDK） | 社区维护，持续更新，LTS 版本支持到 2030+ | **推荐**，生产环境首选 |
| **GraalVM** | Oracle | 支持 AOT 编译为原生镜像，启动极快 | Serverless / 微服务启动敏感场景 |

### 各版本 tag 含义详解

```
eclipse-temurin:17-jre-alpine
                │   │   │
                │   │   └── 操作系统变体
                │   └────── JRE 或 JDK
                └────────── Java 大版本号
```

| Tag 部分 | 可选值 | 含义 |
|----------|--------|------|
| **版本号** | 8, 11, 17, 21 | Java 大版本号，LTS 版本为 8、11、17、21 |
| **运行时** | jdk | 完整 JDK，包含编译器、调试工具、jstat、jmap 等 |
| | jre | 仅 JRE，只包含运行时，体积更小 |
| **系统变体** | alpine | 基于 Alpine Linux，使用 musl libc，体积最小 |
| | focal | 基于 Ubuntu 20.04，使用 glibc，兼容性最好 |
| | jammy | 基于 Ubuntu 22.04，使用 glibc，较新 |
| | slim | 基于 Debian slim，使用 glibc，体积适中 |

### 各基础镜像大小对比

| 镜像 Tag | 压缩后大小（约） | libc | 说明 |
|-----------|------------------|------|------|
| `eclipse-temurin:8-jdk` | ~450 MB | glibc | 完整 JDK，Debian 基础 |
| `eclipse-temurin:8-jre` | ~210 MB | glibc | 仅 JRE，Debian 基础 |
| `eclipse-temurin:8-jdk-alpine` | ~170 MB | musl | 完整 JDK，Alpine 基础 |
| `eclipse-temurin:8-jre-alpine` | **~85 MB** | musl | **Java 8 生产推荐** |
| `eclipse-temurin:17-jdk` | ~470 MB | glibc | 完整 JDK，Debian 基础 |
| `eclipse-temurin:17-jre` | ~220 MB | glibc | 仅 JRE，Debian 基础 |
| `eclipse-temurin:17-jdk-alpine` | ~180 MB | musl | 完整 JDK，Alpine 基础 |
| `eclipse-temurin:17-jre-alpine` | **~90 MB** | musl | **Java 17 生产推荐** |
| `eclipse-temurin:17-jre-focal` | ~220 MB | glibc | Ubuntu 20.04 基础 |
| `eclipse-temurin:17-jre-jammy` | ~220 MB | glibc | Ubuntu 22.04 基础 |

### 选择决策流程

```
                    ┌─────────────────────────┐
                    │  选择 Java 基础镜像      │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │ 是否需要编译/调试工具？   │
                    └─────┬──────────────┬─────┘
                     是   │              │  否
               ┌─────────▼──┐    ┌───────▼───────┐
               │ 使用 JDK   │    │ 使用 JRE      │
               └──────┬─────┘    └───────┬───────┘
                      │                 │
           ┌──────────▼─────────────────▼──────────┐
           │ 应用是否使用 Native Library？            │
           │ （如 Netty 的 native transport、         │
           │   SQLite、JNA、语音/图像处理库等）       │
           └─────┬──────────────────────┬───────────┘
              是 │                      │  否
     ┌───────────▼────────┐   ┌────────▼──────────┐
     │ 使用 Debian/Ubuntu │   │ 使用 Alpine       │
     │ （glibc 兼容）     │   │ （体积最小）       │
     │ jre-focal/jammy    │   │ jre-alpine        │
     └────────────────────┘   └───────────────────┘
```

### Alpine vs Debian 的取舍

| 对比项 | Alpine | Debian/Ubuntu |
|--------|--------|---------------|
| **libc** | musl libc | glibc |
| **基础镜像大小** | ~5 MB | ~70-80 MB |
| **JRE 镜像大小** | ~85-90 MB | ~210-220 MB |
| **Native Library 兼容性** | ❌ 部分库不兼容 | ✅ 完全兼容 |
| **包管理器** | apk | apt |
| **shell** | ash（BusyBox） | bash |
| **DNS 解析** | 可能与 glibc 行为不同 | 标准 glibc 行为 |
| **典型兼容性问题** | Netty native transport 需要额外编译 | 无 |
| | Cassandra 的 JNA 绑定可能失败 | 无 |
| | 某些加密库的 native 绑定可能失败 | 无 |

**生产环境推荐：**
- **Java 8**：`eclipse-temurin:8-jre-alpine`（如无 Native Library 依赖）或 `eclipse-temurin:8-jre-jammy`（如有）
- **Java 17**：`eclipse-temurin:17-jre-alpine`（如无 Native Library 依赖）或 `eclipse-temurin:17-jre-jammy`（如有）
- **需要调试工具**：将 `jre` 替换为 `jdk`，以便使用 `jmap`、`jstack`、`jstat` 等工具

---

## 2.3 单阶段构建示例

以下是一个完整的 Spring Boot JAR 部署 Dockerfile，适用于将本地已构建好的 JAR 包直接拷贝进镜像：

```dockerfile
# ============================================================
# 基础镜像：Eclipse Temurin JRE 8 Alpine
# 选择理由：生产环境推荐，体积小（约 85MB），满足大多数 Java 8 应用需求
# ============================================================
FROM eclipse-temurin:8-jre-alpine

# ============================================================
# 元数据标签：描述镜像信息，便于管理和搜索
# ============================================================
LABEL maintainer="team@example.com" \
      version="1.0.0" \
      description="Spring Boot 用户服务"

# ============================================================
# 安装必要工具和设置时区
# 使用 && 合并多个命令，减少镜像层数
# set -eux: -e 命令失败时退出, -u 未定义变量报错, -x 打印命令
# apk add --no-cache: 不缓存索引，减小镜像体积
# 安装 tzdata 设置时区后删除，避免留在镜像中
# 安装 curl 用于健康检查
# ============================================================
RUN set -eux \
    && apk add --no-cache tzdata curl \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata

# ============================================================
# 设置环境变量
# TZ: 时区，与上面的时区设置配合，确保 java.util.Date 等正确
# LANG: 字符编码，确保日志和输出中文不乱码
# JAVA_OPTS: JVM 参数默认值，运行时可通过 -e 覆盖
# ============================================================
ENV TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    JAVA_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC"

# ============================================================
# 创建应用目录
# /app 作为应用的根目录
# ============================================================
WORKDIR /app

# ============================================================
# 创建非 root 用户
# -S: 创建系统用户（不创建 home 目录等）
# -G: 指定所属组
# 安全最佳实践：容器内不以 root 运行
# ============================================================
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# ============================================================
# 拷贝 JAR 包
# --chown: 在拷贝时设置文件属主，避免额外的 RUN chown 层
# 注意：JAR 包应在构建上下文中（通常在 target/ 目录）
# ============================================================
COPY --chown=appuser:appgroup target/user-service-1.0.0.jar app.jar

# ============================================================
# 声明端口
# 8080: Spring Boot 默认端口
# 注意：这只是文档声明，不实际发布端口
# 实际发布需要 docker run -p 8080:8080
# ============================================================
EXPOSE 8080

# ============================================================
# 声明数据卷
# /app/logs: 应用日志目录
# 运行时可挂载到宿主机持久化：docker run -v /var/log/app:/app/logs
# ============================================================
VOLUME ["/app/logs"]

# ============================================================
# 健康检查
# --interval=30s: 每 30 秒检查一次
# --timeout=3s: 超时 3 秒视为失败
# --start-period=60s: 启动后 60 秒内不计入失败次数
#   （给 JVM 预热和 Spring Boot 启动留足时间）
# --retries=3: 连续 3 次失败标记为 unhealthy
# curl -f: HTTP 错误码时返回非 0 退出码
# ============================================================
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/actuator/health || exit 1

# ============================================================
# 切换到非 root 用户
# 必须在 COPY --chown 之后，否则 appuser 没有文件权限
# ============================================================
USER appuser

# ============================================================
# 启动命令
# ENTRYPOINT: 定义不可变的执行程序
# CMD: 定义可覆盖的默认参数
# 用户可通过 docker run myapp --spring.profiles.active=prod 覆盖参数
# ============================================================
ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS} -jar /app/app.jar"]
CMD ["--spring.profiles.active=dev"]

# ============================================================
# 构建命令：
# docker build -t user-service:1.0.0 .
#
# 运行命令：
# docker run -d \
#   -p 8080:8080 \
#   -e JAVA_OPTS="-Xms1g -Xmx1g" \
#   -v /var/log/user-service:/app/logs \
#   --name user-service \
#   user-service:1.0.0
# ============================================================
```

---

## 2.4 多阶段构建示例

多阶段构建的核心思想：**构建阶段**使用包含完整编译工具链的镜像（JDK + Maven），**运行阶段**只使用精简的 JRE 镜像。最终镜像不包含源代码、编译工具、依赖缓存等，体积大幅减小。

```dockerfile
# ============================================================
# 阶段一：Maven 构建
# 命名为 builder，后续阶段可引用
# 使用包含 Maven 和 JDK 的镜像
# ============================================================
FROM maven:3.9-eclipse-temurin-8 AS builder

# ============================================================
# 缓存优化：先拷贝 pom.xml，再下载依赖
# 原理：Docker 构建缓存基于指令文本和上下文文件
#   - 如果 pom.xml 没变，依赖下载层可以使用缓存
#   - 如果直接 COPY 整个项目再 RUN mvn package，
#     任何源代码修改都会使依赖下载缓存失效
#   - 分两步：先 COPY pom.xml + 下载依赖（缓存层），
#     再 COPY 源代码 + 编译（频繁变化的层）
# ============================================================

# 设置工作目录
WORKDIR /build

# 第一步：拷贝 Maven 项目文件
# 先拷贝 pom.xml，这层只有 pom.xml 变化时才重新构建
COPY pom.xml .

# 第二步：下载依赖（这步通常很慢，利用缓存可节省大量时间）
# -B: 批处理模式，不交互
# dependency:go-offline: 下载所有依赖到本地仓库
# 这一层在 pom.xml 不变时会使用缓存，避免每次重新下载依赖
RUN mvn dependency:go-offline -B

# 第三步：拷贝源代码
# 源代码经常变化，放在最后，不影响依赖缓存层
COPY src ./src

# 第四步：编译打包
# -DskipTests: 跳过测试（测试应在 CI 流水线中单独执行）
# -B: 批处理模式
# -Dmaven.test.skip=true: 不编译也不执行测试
RUN mvn package -B -DskipTests

# ============================================================
# 阶段二：JRE 运行
# 使用精简的 JRE Alpine 镜像
# 只拷贝构建产物，不包含 Maven、源代码、编译缓存
# ============================================================
FROM eclipse-temurin:8-jre-alpine

# 设置时区
RUN set -eux \
    && apk add --no-cache tzdata curl \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata

# 环境变量
ENV TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    JAVA_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC"

# 工作目录
WORKDIR /app

# 创建非 root 用户
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# ============================================================
# 从 builder 阶段拷贝构建产物
# --from=builder: 指定从 builder 阶段拷贝
# /build/target/*.jar: Maven 构建输出的 JAR 包
# app.jar: 重命名为 app.jar
# --chown: 设置文件属主
# ============================================================
COPY --from=builder --chown=appuser:appgroup /build/target/*.jar app.jar

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/actuator/health || exit 1

# 切换用户
USER appuser

# 启动命令
ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS} -jar /app/app.jar"]

# ============================================================
# 多阶段构建的镜像体积差异：
#
# 单阶段（包含 Maven + JDK + 源代码 + 依赖缓存）:
#   镜像大小：约 600-800 MB
#
# 多阶段（只包含 JRE + JAR 包）:
#   镜像大小：约 120-150 MB（85MB JRE + 30-50MB JAR + 其他）
#
# 体积减少约 70-80%
# ============================================================
```

### 多阶段构建的缓存优化原理

```
构建缓存失效流程：

┌─────────────────────────────────────────────────┐
│ 场景：修改了一行 Java 代码                        │
└─────────────────────────────────────────────────┘

❌ 不分步拷贝（每次都要重新下载依赖）：
  COPY pom.xml      → 缓存命中 ✓
  COPY src ./src    → 缓存失效 ✗ （源码变了）
  RUN mvn package   → 缓存失效 ✗ （依赖前面的层）
                    → 重新下载所有依赖（3-10 分钟）

✅ 分步拷贝（依赖下载可复用缓存）：
  COPY pom.xml             → 缓存命中 ✓
  RUN mvn go-offline       → 缓存命中 ✓ （pom.xml 没变）
  COPY src ./src           → 缓存失效 ✗ （源码变了）
  RUN mvn package          → 缓存失效 ✗ （但依赖已在本地仓库）
                           → 只需增量编译（10-30 秒）
```

---

## 2.5 Spring Boot 分层 JAR + 分层 Dockerfile

### 分层概念详解

Spring Boot 从 2.3 开始支持分层 JAR（Layered JAR），将 JAR 包内部按变化频率分为四层：

| 层名 | 内容 | 变化频率 | 示例 |
|------|------|----------|------|
| **dependencies** | 第三方依赖（非 SNAPSHOT） | 最低 | spring-core、jackson、mybatis |
| **spring-boot-loader** | Spring Boot Loader 类 | 几乎不变 | JarLauncher、Launcher |
| **snapshot-dependencies** | SNAPSHOT 版本依赖 | 低 | 内部 SNAPSHOT 模块 |
| **application** | 应用自身的类和资源 | 最高 | Controller、Service、配置文件 |

```
Spring Boot Fat JAR 内部结构：
┌──────────────────────────────────┐
│ BOOT-INF/lib/                    │ ← dependencies 层
│   ├── spring-core-5.3.20.jar     │
│   ├── jackson-databind-2.13.jar  │
│   └── ...                        │
├──────────────────────────────────┤
│ org/springframework/boot/loader/ │ ← spring-boot-loader 层
│   ├── JarLauncher.class          │
│   └── ...                        │
├──────────────────────────────────┤
│ BOOT-INF/lib/                    │ ← snapshot-dependencies 层
│   └── my-lib-1.0-SNAPSHOT.jar    │
├──────────────────────────────────┤
│ BOOT-INF/classes/                │ ← application 层
│   ├── com/example/               │
│   │   ├── controller/            │
│   │   ├── service/               │
│   │   └── Application.class      │
│   ├── application.yml            │
│   └── ...                        │
└──────────────────────────────────┘
```

### 缓存命中率提升原理

```
未分层 Dockerfile 的缓存行为：
  COPY app.jar /app/app.jar  → 只要代码改一行，整个 JAR 变了，缓存全部失效
                                → 重新上传 50MB+ 的 JAR，重新构建整个镜像

分层 Dockerfile 的缓存行为：
  COPY dependencies         → 第三方依赖不变，缓存命中 ✓ （每次构建省 40MB+）
  COPY spring-boot-loader   → 几乎不变，缓存命中 ✓
  COPY snapshot-dependencies → 偶尔变，缓存命中 ✓
  COPY application          → 经常变，缓存失效 ✗ （只需重新上传 1-5MB）
                                → 总传输量从 50MB+ 降到 1-5MB

图解：
  ┌─────────────────────────────────────────────┐
  │ 未分层：每次代码改动                          │
  │ ████████████████████████████████████████████ │ ← 50MB 全部重新上传
  │                                             │
  │ 分层后：每次代码改动                          │
  │ ██████████████████████████████████          │ ← 40MB 依赖：缓存命中，不传输
  │ ██████                                       │ ← 6MB loader：缓存命中，不传输
  │ █                                            │ ← 1MB snapshot：缓存命中，不传输
  │ ████                                         │ ← 3MB 应用代码：需重新传输
  └─────────────────────────────────────────────┘
```

### layertools 使用方法

```bash
# 1. 提取分层信息（查看 JAR 包含哪些层）
java -Djarmode=layertools -jar app.jar list
# 输出：
# dependencies
# spring-boot-loader
# snapshot-dependencies
# application

# 2. 将 JAR 内容按层提取到指定目录
java -Djarmode=layertools -jar app.jar extract
# 会在当前目录创建：
#   dependencies/
#   spring-boot-loader/
#   snapshot-dependencies/
#   application/

# 3. 提取后可以分别 COPY 每一层
```

### 分层 Dockerfile 完整示例

```dockerfile
# ============================================================
# 阶段一：Maven 构建
# ============================================================
FROM maven:3.9-eclipse-temurin-8 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -B -DskipTests

# ============================================================
# 阶段二：分层提取
# 使用 layertools 将 JAR 内容按层提取
# 这一步是分层构建的关键
# ============================================================
FROM eclipse-temurin:8-jre-alpine AS extractor
WORKDIR /extract
# 从 builder 阶段拷贝 JAR 包
COPY --from=builder /build/target/*.jar app.jar
# 使用 Spring Boot 的 layertools 模式提取分层
# -Djarmode=layertools: 激活分层工具模式
# extract: 将 JAR 内容按层提取到各自目录
java -Djarmode=layertools -jar app.jar extract

# ============================================================
# 阶段三：运行镜像
# 按层拷贝，变化频率从低到高排列
# 这样前面不变时可以复用缓存
# ============================================================
FROM eclipse-temurin:8-jre-alpine

RUN set -eux \
    && apk add --no-cache tzdata curl \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata

ENV TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    JAVA_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC"

WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# ============================================================
# 分层拷贝：从变化最少到变化最多
# 每一层单独 COPY，Docker 会按层计算缓存
# ============================================================

# 第一层：第三方依赖（变化最少，缓存命中率最高）
# 包含 spring-core、jackson 等数百个 jar，体积最大
COPY --from=extractor --chown=appuser:appgroup /extract/dependencies/ ./

# 第二层：Spring Boot Loader（几乎不变）
# 包含 JarLauncher 等 Spring Boot 启动相关类
COPY --from=extractor --chown=appuser:appgroup /extract/spring-boot-loader/ ./

# 第三层：SNAPSHOT 依赖（低频变化）
# 包含 SNAPSHOT 版本的内部依赖
COPY --from=extractor --chown=appuser:appgroup /extract/snapshot-dependencies/ ./

# 第四层：应用代码（变化最频繁）
# 包含 Controller、Service、配置文件等
COPY --from=extractor --chown=appuser:appgroup /extract/application/ ./

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/actuator/health || exit 1

USER appuser

# ============================================================
# 启动命令
# 注意：分层后不能再用 -jar 方式启动
# 需要使用 JarLauncher 来启动，它会按照分层顺序加载类
# ============================================================
ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS} org.springframework.boot.loader.JarLauncher"]

# 如果是 Spring Boot 3.x（Java 17+），Loader 类名不同：
# ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS} org.springframework.boot.loader.launch.JarLauncher"]
```

### Spring Boot 2.3+ 启用分层

Spring Boot 2.3+ 默认支持分层 JAR，但需要在 `pom.xml` 中确认配置：

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <!-- Spring Boot 2.3+ 默认已启用分层，也可以显式声明 -->
        <layers>
            <enabled>true</enabled>
        </layers>
    </configuration>
</plugin>
```

---

## 2.6 JVM 参数在容器中的设置（重点！）

### Java 8u191 之前的容器感知问题

**问题本质：** JVM 通过读取 `/proc/meminfo` 和 `/proc/cpuinfo` 来获取内存和 CPU 信息。但在容器中，这些文件显示的是**宿主机**的资源，而非容器的限制。

```
宿主机内存：64GB
容器限制：  2GB（docker run -m 2g）

Java 8u191 之前的 JVM 行为：
  JVM 读取 /proc/meminfo → 看到 64GB
  默认 -Xmx = 64GB * 1/4 = 16GB
  JVM 尝试分配 16GB 堆内存
  容器实际只有 2GB → OOM Killed！

宿主机视角：
  容器内存使用超过 2GB 限制 → 内核 OOM Killer 杀掉容器进程
  docker ps 显示 Exit Code: 137 （被 SIGKILL）
```

**Java 8u191 之前的临时解决方案：**

```bash
# 手动开启容器感知（实验性参数）
java -XX:+UseCGroupCpuLimitController -XX:+UseCGroupMemoryLimitForHeap ...
# -XX:+UseCGroupMemoryLimitForHeap: 让 JVM 读取 cgroup 的内存限制
# -XX:+UseCGroupCpuLimitController: 让 JVM 读取 cgroup 的 CPU 限制

# 或者手动指定固定值
java -Xmx1500m ...  # 手动计算：2GB * 75% ≈ 1500m
```

### Java 8u191+ / Java 11+：容器感知已默认开启

```bash
# 从 Java 8u191 开始，容器感知默认开启
# -XX:+UseContainerSupport 默认为 true
# JVM 会自动读取 cgroup 的内存和 CPU 限制

# 验证容器感知是否生效
java -XX:+PrintContainerInfo -version
# 输出类似：
# Operating System Metrics:
#   Provider: cgroupv1
#   Effective CPU Count: 2
#   CPU Period: 100000
#   CPU Quota: 200000
#   Memory Limit: 2147483648    ← 2GB，说明正确读取了容器限制
#   Memory Swap Limit: ...

# 如果需要关闭容器感知（不推荐）
java -XX:-UseContainerSupport ...
```

### -XX:MaxRAMPercentage=75.0 vs 固定 -Xmx2g

| 对比项 | MaxRAMPercentage | 固定 -Xmx |
|--------|------------------|-----------|
| **灵活性** | ✅ 自动适配容器内存 | ❌ 需要手动调整 |
| **可维护性** | ✅ 同一镜像可用于不同规格 | ❌ 每个规格需不同镜像/参数 |
| **精确性** | ❌ 百分比计算可能不精确 | ✅ 精确控制 |
| **推荐场景** | 容器环境（推荐） | 调试/性能调优 |

**推荐使用 MaxRAMPercentage：**

```bash
# 容器限制 2GB 时：
java -XX:MaxRAMPercentage=75.0 ...
# JVM 堆 = 2GB * 75% = 1.5GB

# 容器限制 4GB 时，同一个镜像：
java -XX:MaxRAMPercentage=75.0 ...
# JVM 堆 = 4GB * 75% = 3GB

# 不需要改镜像，不需要改启动参数，自动适配！
```

**固定 -Xmx 的问题：**

```bash
# 场景：Dockerfile 中硬编码 -Xmx2g
ENTRYPOINT ["java", "-Xmx2g", "-jar", "app.jar"]

# 问题 1：如果容器限制改为 4GB，JVM 仍然只用 2GB 堆，浪费资源
# 问题 2：如果容器限制改为 1GB，JVM 尝试分配 2GB 堆，OOM Killed
# 问题 3：每次调整都需要修改 Dockerfile 或运行时参数
```

### 容器内存限制与 JVM 堆内存的关系

```
容器内存限制：2GB（docker run -m 2g）

┌─────────────────────────── 容器总内存 2GB ───────────────────────────┐
│                                                                      │
│  ┌──────────────── JVM 进程使用的 2GB ────────────────┐              │
│  │                                                     │              │
│  │  ┌─────────── Java 堆内存 1.5GB ───────────┐       │              │
│  │  │                                          │       │              │
│  │  │  -XX:MaxRAMPercentage=75.0               │       │              │
│  │  │  2GB * 75% = 1.5GB                       │       │              │
│  │  │                                          │       │              │
│  │  │  存放：对象实例、数组等                     │       │              │
│  │  └──────────────────────────────────────────┘       │              │
│  │                                                     │              │
│  │  ┌──── 非堆内存 ~500MB ────┐                       │              │
│  │  │                          │                       │              │
│  │  │  元空间 (Metaspace)      │  ~50-100MB            │              │
│  │  │  类元数据、方法信息       │  默认无上限，           │              │
│  │  │                          │  实际受容器限制         │              │
│  │  │                          │                       │              │
│  │  │  线程栈 (Thread Stack)   │  ~100-200MB            │              │
│  │  │  每线程 ~1MB             │  100个线程 = 100MB     │              │
│  │  │                          │                       │              │
│  │  │  直接内存 (Direct Mem)   │  ~50-100MB             │              │
│  │  │  NIO ByteBuffer          │  Netty 等使用          │              │
│  │  │                          │                       │              │
│  │  │  JNI/Native 内存         │  ~20-50MB              │              │
│  │  │  本地方法分配的内存       │  取决于 Native 库      │              │
│  │  │                          │                       │              │
│  │  │  JVM 内部结构            │  ~20-50MB              │              │
│  │  │  CodeCache、GC 结构等    │                       │              │
│  │  └──────────────────────────┘                       │              │
│  └─────────────────────────────────────────────────────┘              │
│                                                                      │
│  容器保留给 OS 的内存：极少，容器共享宿主机内核                         │
└──────────────────────────────────────────────────────────────────────┘

⚠️ 关键：-XX:MaxRAMPercentage=75.0 只控制堆内存！
   非 heap 内存（元空间、线程栈、直接内存等）不算在 75% 内！
   所以 75% 是一个相对安全的值，给非堆内存留出约 25% 空间。
   如果应用使用大量堆外内存（如 Netty），需要降低百分比到 60-65%。
```

### 其他容器中常用 JVM 参数

```bash
# ====== 初始堆内存百分比 ======
-XX:InitialRAMPercentage=50.0
# 等价于 -Xms，但基于容器内存百分比
# 建议设为 MaxRAMPercentage 的 50%-75%
# 避免初始堆过小导致频繁 Full GC

# ====== 容器感知开关 ======
-XX:+UseContainerSupport
# Java 8u191+ / Java 11+ 默认已开启
# 显式声明仅为了文档目的，确保任何人看到都知道容器感知是开启的

# ====== SecureRandom 加速 ======
-Djava.security.egd=file:/dev/./urandom
# 问题：默认 /dev/random 是阻塞式的，熵不足时会导致启动极慢
#       容器中熵源有限，/dev/random 可能阻塞数分钟
# 解决：使用 /dev/urandom（非阻塞式伪随机数生成器）
# 注意：中间的 ./ 不是笔误！这是 Java Security API 的约定
#       file:/dev/urandom 在某些 JDK 版本会被忽略
#       file:/dev/./urandom 可以确保使用 urandom

# ====== OOM 时自动 Dump 堆 ======
-XX:+HeapDumpOnOutOfMemoryError
# OOM 时自动生成堆转储文件，用于事后分析
-XX:HeapDumpPath=/app/logs/heapdump.hprof
# 指定堆转储文件路径
# 确保路径可写且挂载了卷，否则容器重启后 dump 文件丢失

# ====== GC 选择建议 ======
# Java 8：推荐 ParallelGC（吞吐量优先）
-XX:+UseParallelGC
# Java 8 的默认 GC，适合批处理、后台任务等吞吐量敏感场景

# Java 8：也可用 G1GC（延迟优先，但 Java 8 中不够成熟）
-XX:+UseG1GC
# 适合需要低延迟的 Web 服务

# Java 11+：推荐 G1GC（默认就是 G1，无需显式指定）
-XX:+UseG1GC
# Java 11+ 的默认 GC，适合大多数场景
# 平衡了吞吐量和延迟

# Java 11+：大堆内存（6GB+）可考虑 ZGC
-XX:+UseZGC
# 超低延迟，STW 停顿 < 10ms
# Java 11 中是实验性功能，Java 15+ 正式可用
```

### 在 Dockerfile 中设置 JVM 参数的多种方式

**方式一：ENV 变量 + ENTRYPOINT 引用（推荐）**

```dockerfile
# 设置默认 JVM 参数
ENV JAVA_OPTS="-Xms512m -Xmx512m -XX:MaxRAMPercentage=75.0 \
    -XX:+UseContainerSupport \
    -Djava.security.egd=file:/dev/./urandom \
    -XX:+HeapDumpOnOutOfMemoryError \
    -XX:HeapDumpPath=/app/logs/heapdump.hprof"

# 在 ENTRYPOINT 中引用
ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS} -jar /app/app.jar"]
# 运行时覆盖：docker run -e JAVA_OPTS="-Xms1g -Xmx1g ..." myapp
```

**方式二：entrypoint.sh 脚本（更灵活，推荐生产使用）**

```dockerfile
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
```

```bash
#!/bin/sh
# entrypoint.sh

# 默认 JVM 参数（如果环境变量未设置）
: "${JAVA_OPTS:=-Xms512m -Xmx512m -XX:MaxRAMPercentage=75.0}"
: "${JAVA_OPTS:=-XX:+UseContainerSupport}"
: "${JAVA_OPTS:=-Djava.security.egd=file:/dev/./urandom}"

# 打印 JVM 参数（方便调试，生产环境可移除）
echo "Starting Java application with JAVA_OPTS: ${JAVA_OPTS}"

# exec 确保 java 进程成为 PID 1
# "$@" 接收 CMD 或 docker run 传入的参数
exec java ${JAVA_OPTS} -jar /app/app.jar "$@"
```

**方式三：CMD 中直接指定（简单但不灵活）**

```dockerfile
CMD ["java", "-Xms512m", "-Xmx512m", "-jar", "/app/app.jar"]
# 缺点：运行时无法方便地修改 JVM 参数
# 只能通过 docker run myapp java -Xmx1g -jar /app/app.jar 完整替换
```

**方式四：使用 JAVA_TOOL_OPTIONS 环境变量**

```dockerfile
# JAVA_TOOL_OPTIONS 是 JVM 自动识别的环境变量
# JVM 启动时会自动读取并应用，无需在启动命令中引用
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0 -Djava.security.egd=file:/dev/./urandom"
# 注意：JVM 会打印 "Picked up JAVA_TOOL_OPTIONS: ..." 的提示信息
# 这是正常行为，不影响功能
# 优先级：命令行参数 > JAVA_TOOL_OPTIONS

# 与其他环境变量的区别：
# JAVA_TOOL_OPTIONS: 任何 JVM 都识别，适用于所有 Java 工具（jstat、jmap 等）
# JAVA_OPTS: 不是 JVM 内置识别的，需要在启动脚本中手动引用
# _JAVA_OPTIONS: Oracle/OpenJDK 专用，优先级最高，会覆盖命令行参数
```

---

## 2.7 时区 / 字体 / SSL 证书

### 时区设置

**方式一：TZ 环境变量（最简单，推荐）**

```dockerfile
# ====== Alpine 镜像 ======
# 需要安装 tzdata 包，否则 TZ 变量无效
RUN apk add --no-cache tzdata
ENV TZ=Asia/Shanghai
# 注意：Alpine 必须安装 tzdata，否则不识别 TZ 变量
# tzdata 包约 1-2MB，保留在镜像中（因为运行时需要时区数据文件）

# ====== Debian/Ubuntu 镜像 ======
# 通常已包含 tzdata，直接设置即可
ENV TZ=Asia/Shanghai
# 如果没有 tzdata：
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
```

**方式二：软链接（不需要 tzdata 包）**

```dockerfile
# ====== Alpine 镜像 ======
RUN apk add --no-cache tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata
# 安装 tzdata → 创建软链接 → 删除 tzdata
# 软链接创建后，即使删除 tzdata 包，链接仍然有效
# 但 /usr/share/zoneinfo 文件会被删除，所以这种方式其实有问题
# 推荐保留 tzdata 包

# ====== Debian/Ubuntu 镜像 ======
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone
```

**方式三：运行时通过环境变量覆盖**

```bash
# 不在 Dockerfile 中设置，运行时指定
docker run -e TZ=Asia/Shanghai myapp
# 前提：镜像中已安装 tzdata
```

### 中文字体安装

验证码生成、PDF 导出等场景需要中文字体支持。

**Alpine 镜像安装字体：**

```dockerfile
RUN set -eux \
    && apk add --no-cache fontconfig ttf-dejavu \
    && fc-cache -fv
# fontconfig: 字体管理库
# ttf-dejavu: 开源字体，包含中文基础支持
# fc-cache -fv: 刷新字体缓存

# 如果需要更多中文字体（如宋体、黑体），需要手动安装
# 方式一：从构建上下文拷贝字体文件
COPY fonts/SimHei.ttf /usr/share/fonts/truetype/
RUN fc-cache -fv

# 方式二：从网上下载（不推荐，构建不可复现）
# RUN apk add --no-cache wget \
#     && mkdir -p /usr/share/fonts/truetype \
#     && wget -q https://example.com/SimHei.ttf -O /usr/share/fonts/truetype/SimHei.ttf \
#     && fc-cache -fv \
#     && apk del wget
```

**Debian/Ubuntu 镜像安装字体：**

```dockerfile
RUN set -eux \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       fontconfig \
       fonts-dejavu \
       fonts-wqy-zenhei \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*
# fonts-dejavu: 开源西文字体
# fonts-wqy-zenhei: 文泉驿正黑，开源中文字体
# --no-install-recommends: 不安装推荐包，减小体积
# rm -rf /var/lib/apt/lists/*: 清除 apt 缓存，减小镜像体积
```

**Java 验证字体是否可用：**

```java
// Java 代码中验证可用字体
import java.awt.GraphicsEnvironment;
public class FontTest {
    public static void main(String[] args) {
        String[] fonts = GraphicsEnvironment
            .getLocalGraphicsEnvironment()
            .getAvailableFontFamilyNames();
        for (String font : fonts) {
            if (font.contains("Hei") || font.contains("Song") || font.contains("DejaVu")) {
                System.out.println("Found font: " + font);
            }
        }
    }
}
```

### SSL 证书导入

**方式一：keytool 导入到 Java TrustStore**

```dockerfile
# 拷贝自签名证书或企业内部 CA 证书
COPY certs/company-ca.crt /tmp/company-ca.crt

# 使用 keytool 导入到 JVM 的 cacerts 文件
# -importcert: 导入证书
# -alias: 证书别名
# -keystore: 目标 keystore 路径
# -storepass: keystore 密码（默认 changeit）
# -noprompt: 不提示确认
# -file: 证书文件路径
RUN keytool -importcert -noprompt \
    -alias company-ca \
    -keystore $JAVA_HOME/lib/security/cacerts \
    -storepass changeit \
    -file /tmp/company-ca.crt \
    && rm /tmp/company-ca.crt
# 默认 cacerts 密码是 changeit（Java 传统）
# $JAVA_HOME 在 Eclipse Temurin 镜像中已自动设置
# 导入后删除证书文件，减小镜像体积
```

**方式二：update-ca-certificates 导入到系统 TrustStore**

```dockerfile
# ====== Alpine 镜像 ======
# 拷贝证书到系统 CA 目录
COPY certs/company-ca.crt /usr/local/share/ca-certificates/company-ca.crt
# 更新系统 CA 证书库
RUN update-ca-certificates
# Alpine 默认已安装 ca-certificates 包

# ====== Debian/Ubuntu 镜像 ======
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
COPY certs/company-ca.crt /usr/local/share/ca-certificates/company-ca.crt
RUN update-ca-certificates
# 证书文件必须以 .crt 结尾，否则 update-ca-certificates 不识别
```

**两种方式的区别：**
- `keytool` 方式：证书只导入到 JVM 的 cacerts，Java 应用可以使用，但系统级工具（curl、wget）不识别
- `update-ca-certificates` 方式：证书导入到系统 CA 库，系统工具可用，但 JVM 默认不读取系统 CA 库
- **推荐**：如果只需要 Java 应用识别，用 keytool；如果系统工具也需要，两种都做

```dockerfile
# 同时导入到系统和 JVM 的完整示例
COPY certs/company-ca.crt /usr/local/share/ca-certificates/company-ca.crt
RUN update-ca-certificates \
    && keytool -importcert -noprompt \
       -alias company-ca \
       -keystore $JAVA_HOME/lib/security/cacerts \
       -storepass changeit \
       -file /usr/local/share/ca-certificates/company-ca.crt
```

---

## 2.8 .dockerignore 文件

### 作用与原理

`.dockerignore` 文件告诉 Docker 在构建上下文中排除哪些文件和目录。构建上下文是 `docker build` 时发送给 Docker Daemon 的所有文件，体积越小，构建越快。

**原理：**
1. 执行 `docker build .` 时，Docker CLI 将当前目录（构建上下文）打包发送给 Docker Daemon
2. `.dockerignore` 中的规则在打包前生效，匹配的文件不会被发送
3. 这意味着即使 `COPY` 指令想拷贝被忽略的文件，也无法找到

**为什么重要：**
- **加速构建**：减少发送给 Daemon 的数据量
- **安全性**：防止敏感文件（.git、.env、密钥文件）意外进入镜像
- **缓存优化**：排除无关文件变化，避免缓存失效

### Java 项目常用模板

```gitignore
# ====== 版本控制 ======
.git
.gitignore
.gitattributes

# ====== IDE 文件 ======
.idea/
*.iml
.vscode/
.settings/
.project
.classpath
*.swp
*.swo
*~

# ====== 构建产物 ======
target/
build/
out/
*.class
*.jar
*.war
# 注意：如果需要在 Dockerfile 中 COPY target/*.jar，
# 不能忽略整个 target/ 目录！
# 应该忽略 target/ 中的临时文件，但保留 JAR 包
# 修正：不忽略 target/，或者在多阶段构建中忽略（构建在 Docker 内完成）
# 对于多阶段构建（Maven 构建在 Docker 内），可以安全地忽略 target/

# ====== Node.js（如果前端在同一个仓库） ======
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# ====== 日志文件 ======
*.log
logs/

# ====== 环境配置（敏感信息） ======
.env
.env.*
!.env.example

# ====== Docker 相关 ======
docker-compose*.yml
.docker/
Dockerfile*
# 注意：Dockerfile 本身不需要被排除，它不会进入构建上下文
# 但其他 Dockerfile 变体可以排除

# ====== 文档 ======
README.md
CONTRIBUTING.md
CHANGELOG.md
docs/

# ====== CI/CD ======
.github/
.gitlab-ci.yml
Jenkinsfile

# ====== 操作系统文件 ======
.DS_Store
Thumbs.db

# ====== 临时文件 ======
tmp/
temp/
*.tmp
*.bak
```

**对于单阶段构建（JAR 在宿主机构建），需要调整 target/ 的忽略规则：**

```gitignore
# 单阶段构建时：不忽略 target/ 中的 JAR 包
target/
!target/*.jar
# 忽略 target/ 目录，但不忽略 target/*.jar
# 这样 COPY target/*.jar app.jar 可以正常工作

# 或者更精确地只忽略不需要的：
target/classes/
target/generated-sources/
target/maven-status/
target/surefire-reports/
# 保留 target/*.jar
```

---

## 2.9 阅读已有 Dockerfile 的方法论

### 分析思路流程

阅读一个 Dockerfile 时，按照以下顺序逐层分析：

```
步骤 1：基础镜像 → 了解运行时环境和基础大小
  ↓
步骤 2：构建阶段 → 是否多阶段构建？构建工具是什么？
  ↓
步骤 3：运行阶段 → 安装了什么？环境变量？用户权限？
  ↓
步骤 4：暴露端口 → 应用监听哪些端口？
  ↓
步骤 5：启动命令 → ENTRYPOINT + CMD 如何组合？启动参数是否合理？
```

**逐步骤详解：**

```
步骤 1：基础镜像
  ├── 使用的什么镜像？（eclipse-temurin? openjdk? 不知名的镜像?）
  ├── 什么版本？（Java 8? 11? 17? 是否已停止维护?）
  ├── JDK 还是 JRE？（生产环境应该用 JRE，除非需要调试工具）
  ├── Alpine 还是 Debian？（Alpine 更小但有兼容性风险）
  └── 是否指定了 tag？（没有 tag 的 latest 是危险的）

步骤 2：构建阶段
  ├── 是否多阶段构建？（不是则镜像可能很大）
  ├── 构建工具？（Maven? Gradle?）
  ├── 是否有缓存优化？（先拷贝 pom.xml 再拷贝源码?）
  └── 构建参数？（是否有硬编码版本号?）

步骤 3：运行阶段
  ├── 安装了什么包？（是否安装了不必要的包?）
  ├── 环境变量设置？（JVM 参数? 时区? 字符编码?）
  ├── 文件权限？（--chown? 后续 chown? 没有设置?）
  ├── 用户权限？（是否以 root 运行?）
  ├── 时区设置？（是否设置了正确的时区?）
  └── 健康检查？（是否配置了 HEALTHCHECK?）

步骤 4：暴露端口
  ├── 哪些端口？（业务端口? 管理端口? 调试端口?）
  └── 是否有多余端口暴露?

步骤 5：启动命令
  ├── ENTRYPOINT + CMD 的组合方式？
  ├── 是否使用 exec 格式？（Shell 格式不会成为 PID 1，影响信号处理）
  ├── JVM 参数是否合理？（MaxRAMPercentage? UseContainerSupport?）
  └── 是否有优雅关闭的支持？（exec 格式 + SIGTERM?）
```

### 常见反模式识别清单

| # | 反模式 | 问题 | 改进 |
|---|--------|------|------|
| 1 | **以 root 运行** | 安全风险，容器逃逸后获得 root 权限 | 使用 USER 指定非 root 用户 |
| 2 | **镜像过大** | 拉取/推送慢，占用存储 | 多阶段构建，使用 Alpine/JRE 镜像 |
| 3 | **没有 .dockerignore** | 构建上下文过大，可能泄露敏感信息 | 创建 .dockerignore |
| 4 | **多层 RUN 未合并** | 增加不必要的镜像层数和体积 | 用 `&&` 合并相关 RUN |
| 5 | **使用 ADD 而非 COPY** | ADD 的隐式解压行为可能导致意外 | 优先使用 COPY |
| 6 | **硬编码敏感信息** | 密码、密钥等通过 ENV 或 ARG 写入镜像 | 运行时通过 -e 或 Secret 传入 |
| 7 | **使用 latest tag** | 基础镜像版本不可控，构建不可复现 | 指定明确版本号 |
| 8 | **没有 HEALTHCHECK** | Docker 无法判断容器是否真正健康 | 添加 HEALTHCHECK |
| 9 | **Shell 格式的 ENTRYPOINT/CMD** | 不使用 exec 时，应用不是 PID 1，收不到 SIGTERM | 使用 exec 格式或脚本中加 exec |
| 10 | **JVM 不感知容器** | Java 8u191 前 JVM 看到宿主机内存 | 使用 MaxRAMPercentage + UseContainerSupport |
| 11 | **安装后不清除缓存** | apt/apk 缓存留在镜像中增大体积 | 同一 RUN 中安装后立即清除 |
| 12 | **没有时区设置** | 默认 UTC 时间，日志时间不正确 | 设置 TZ 或安装 tzdata |

### "坏 Dockerfile" vs "改进版 Dockerfile"

**坏 Dockerfile：**

```dockerfile
FROM java:8
# 问题 1：java:8 是已弃用的官方镜像，基于 Debian Jessie，不再更新
# 问题 2：使用了 latest（实际上 java:8 就是 openjdk:8，已停止维护）

MAINTAINER developer@example.com
# 问题 3：MAINTAINER 已弃用，应使用 LABEL

RUN apt-get update
RUN apt-get install -y wget
RUN apt-get install -y curl
RUN apt-get install -y vim
# 问题 4：多层 RUN 未合并，每层增加约 20-50MB
# 问题 5：安装了不需要的 vim（调试工具不应在生产镜像中）
# 问题 6：安装后没有清除 apt 缓存

ADD target/my-app.jar /app/my-app.jar
# 问题 7：使用 ADD 而非 COPY
# 问题 8：没有 --chown，文件属主为 root

ENV DB_PASSWORD=mypassword123
# 问题 9：硬编码密码！docker history 可以看到！

WORKDIR /app

EXPOSE 8080
# 没问题

CMD java -Xmx2g -jar my-app.jar
# 问题 10：Shell 格式的 CMD，java 不是 PID 1
# 问题 11：硬编码 -Xmx2g，不灵活
# 问题 12：没有容器感知参数
# 问题 13：没有时区设置
# 问题 14：以 root 用户运行
# 问题 15：没有健康检查
```

**改进版 Dockerfile：**

```dockerfile
# 问题 1 修复：使用 Eclipse Temurin，指定明确版本
FROM eclipse-temurin:8-jre-alpine

# 问题 3 修复：使用 LABEL 替代 MAINTAINER
LABEL maintainer="team@example.com" \
      version="1.0.0" \
      description="用户管理微服务"

# 问题 4/5/6 修复：合并 RUN，只安装必要工具，安装后清除缓存
RUN set -eux \
    && apk add --no-cache tzdata curl \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata
# 只安装 curl（健康检查需要），不装 vim
# tzdata 安装后删除，减小体积
# 问题 13 修复：同时设置了时区

# 问题 12 修复：设置 JVM 容器感知参数
ENV TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    JAVA_OPTS="-XX:MaxRAMPercentage=75.0 \
               -XX:+UseContainerSupport \
               -Djava.security.egd=file:/dev/./urandom \
               -XX:+HeapDumpOnOutOfMemoryError \
               -XX:HeapDumpPath=/app/logs/heapdump.hprof"
# 不硬编码 -Xmx，使用 MaxRAMPercentage 自动适配
# 问题 9 修复：不硬编码密码，运行时通过 -e 或 Secret 传入

WORKDIR /app

# 问题 14 修复：创建非 root 用户
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# 问题 7/8 修复：使用 COPY + --chown
COPY --chown=appuser:appgroup target/my-app.jar app.jar

EXPOSE 8080

# 新增：健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/actuator/health || exit 1

# 切换到非 root 用户
USER appuser

# 问题 10/11 修复：使用 ENTRYPOINT + CMD，exec 格式
# 通过 entrypoint.sh 脚本确保 java 是 PID 1
COPY --chown=appuser:appgroup entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
CMD ["--spring.profiles.active=dev"]
```

```bash
#!/bin/sh
# entrypoint.sh
: "${JAVA_OPTS:=-XX:MaxRAMPercentage=75.0 -XX:+UseContainerSupport}"
exec java ${JAVA_OPTS} -jar /app/app.jar "$@"
# exec: java 成为 PID 1，正确接收 SIGTERM
# "$@": 接收 CMD 或 docker run 传入的参数
```

**改进效果对比：**

| 对比项 | 坏 Dockerfile | 改进版 Dockerfile |
|--------|---------------|-------------------|
| 基础镜像 | java:8（~600MB） | eclipse-temurin:8-jre-alpine（~85MB） |
| 最终镜像大小 | ~800MB | ~120MB |
| 运行用户 | root | appuser |
| 密码安全 | 硬编码在镜像中 | 运行时注入 |
| JVM 参数 | 硬编码 -Xmx2g | MaxRAMPercentage 自动适配 |
| 信号处理 | Shell 格式，不是 PID 1 | exec 格式，PID 1 |
| 健康检查 | 无 | 有 |
| 时区 | 默认 UTC | Asia/Shanghai |
| 镜像层数 | 多层冗余 | 合并优化 |

---

# 第三章：部署 Shell 脚本详解

## 3.1 Shell 脚本基础语法速查

### 3.1.1 变量

**普通变量**

```bash
# 等号两侧不能有空格，这是初学者最常犯的错误
APP_NAME="user-service"          # 字符串赋值
PORT=8080                        # 数字（Shell 中一切皆字符串，数字只是可运算的字符串）
RETRY_COUNT=3                    # 赋值时不需要 $，读取时才需要

# 读取变量必须加 $ 符号
echo $APP_NAME                   # 输出: user-service
echo ${APP_NAME}                 # 输出: user-service（花括号用于界定变量名边界）
echo "服务名: ${APP_NAME}"       # 双引号中变量会展开，输出: 服务名: user-service
echo '服务名: ${APP_NAME}'       # 单引号中变量不展开，输出: 服务名: ${APP_NAME}

# 变量拼接
FULL_IMAGE="registry.example.com/${APP_NAME}:${PORT}"
# FULL_IMAGE → registry.example.com/user-service:8080
```

**环境变量与 export**

```bash
# 普通变量只在当前 Shell 进程中可见，子进程无法访问
LOCAL_VAR="only-here"
bash -c 'echo $LOCAL_VAR'        # 输出空行，子进程看不到

# export 将变量导出为环境变量，子进程可以继承
export DB_HOST="mysql.prod.svc"
bash -c 'echo $DB_HOST'          # 输出: mysql.prod.svc，子进程可以访问

# 常见用法：在部署脚本中设置 Java 应用需要的环境变量
export JAVA_OPTS="-Xms512m -Xmx2048m -Dspring.profiles.active=prod"
export SPRING_DATASOURCE_URL="jdbc:mysql://${DB_HOST}:3306/appdb"

# docker run -e 可以将这些环境变量传入容器
docker run -e JAVA_OPTS -e SPRING_DATASOURCE_URL my-app:latest
# -e VAR_NAME 不带值时，会取当前 Shell 中同名环境变量的值传入容器
```

**特殊变量**

```bash
# $? —— 上一条命令的退出状态码，0 表示成功，非 0 表示失败
docker pull my-app:latest
if [ $? -eq 0 ]; then
    echo "镜像拉取成功"
else
    echo "镜像拉取失败，退出码: $?"
    exit 1
fi
# 注意：if [ $? -eq 0 ] 中的 $? 是 if 上一条命令(docker pull)的状态
# 但一旦执行了其他命令，$? 就会被覆盖，所以通常立即保存
pull_result=$?
echo "拉取结果: ${pull_result}"

# $! —— 最近一个后台进程的 PID
sleep 60 &
bg_pid=$!                        # 捕获后台 sleep 进程的 PID
echo "后台进程 PID: ${bg_pid}"
kill ${bg_pid} 2>/dev/null        # 需要时可以终止该后台进程

# $0 —— 当前脚本名称（含调用路径）
echo "当前脚本: $0"
# ./deploy.sh 调用时，$0="./deploy.sh"
# bash /opt/scripts/deploy.sh 调用时，$0="/opt/scripts/deploy.sh"

# $1 ~ $9 —— 位置参数（脚本的第 1 到第 9 个参数）
# ${10} —— 第 10 个及以上的参数需要花括号
./deploy.sh user-service v1.2.3 8080 prod
# 脚本内: $1="user-service", $2="v1.2.3", $3="8080", $4="prod"

# $# —— 参数个数
echo "共传入 $# 个参数"          # 上例输出: 共传入 4 个参数

# $@ —— 所有参数，每个参数作为独立字符串（保留参数边界）
# $* —— 所有参数，合并为一个字符串
for arg in "$@"; do               # "$@" 正确处理含空格的参数
    echo "参数: ${arg}"
done

# 区别演示
set -- "hello world" foo bar
echo "$@"   # 输出: hello world foo bar（三个独立参数）
echo "$*"   # 输出: hello world foo bar（一个合并字符串，用 IFS 连接）
for i in "$@"; do echo "[$i]"; done
# 输出: [hello world] [foo] [bar]  —— 三个参数，空格未被拆分
for i in "$*"; do echo "[$i]"; done
# 输出: [hello world foo bar]       —— 一个参数
```

### 3.1.2 条件判断

**if/elif/else/fi 基本结构**

```bash
DEPLOY_ENV="prod"

if [ "$DEPLOY_ENV" = "prod" ]; then
    echo "生产环境部署"
elif [ "$DEPLOY_ENV" = "staging" ]; then
    echo "预发环境部署"
else
    echo "未知环境: ${DEPLOY_ENV}"
    exit 1
fi
# 注意：if/then/elif/else/fi 每个关键字必须单独一行或用分号分隔
```

**test 命令、[ ] 与 [[ ]]**

```bash
# test 命令是条件判断的原始形式
test -f /etc/passwd && echo "文件存在"
# 等价于
[ -f /etc/passwd ] && echo "文件存在"
# [ ] 实际上是 test 命令的语法糖，注意 [ 后和 ] 前必须有空格

# [[ ]] 是 Bash 增强版条件判断，推荐优先使用
# 优势 1：不需要对变量加双引号防分裂
VAR=""
[ $VAR = "hello" ]               # 报错！展开为 [ = "hello" ]，语法错误
[ "$VAR" = "hello" ]             # 正确，需要加引号
[[ $VAR = "hello" ]]             # 正确，[[ ]] 自动处理空变量

# 优势 2：支持模式匹配（通配符）
FILE="app-config.yml"
[[ $FILE = *.yml ]] && echo "YAML 文件"       # 匹配成功
[ "$FILE" = *.yml ]                            # 不支持，* 不会被展开为通配符

# 优势 3：支持正则匹配
IMAGE_TAG="v1.2.3"
[[ $IMAGE_TAG =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] && echo "合法版本号"

# 优势 4：支持 && 和 || 逻辑运算符
[[ -n "$APP_NAME" && -n "$IMAGE_TAG" ]] && echo "参数完整"
# [ ] 中只能用 -a 和 -o，且可读性差
[ -n "$APP_NAME" -a -n "$IMAGE_TAG" ]         # 不推荐
```

**常用判断条件**

```bash
# === 文件判断 ===
[ -f deploy.sh ]          # 文件存在且为普通文件（最常用）
[ -d /opt/app ]           # 路径存在且为目录
[ -e /var/log/app.log ]   # 路径存在（不区分类型）
[ -r config.yml ]         # 文件存在且可读
[ -w /tmp ]               # 文件存在且可写
[ -x /usr/bin/docker ]    # 文件存在且可执行
[ -s app.log ]            # 文件存在且非空（size > 0）
[ -L /usr/bin/java ]      # 路径存在且为符号链接

# === 字符串判断 ===
[ -n "$APP_NAME" ]        # 字符串非空（nonzero length）
[ -z "$APP_NAME" ]        # 字符串为空（zero length）
[ "$ENV" = "prod" ]       # 字符串相等（注意用 = 而非 ==，== 是 Bash 扩展）
[ "$ENV" != "dev" ]       # 字符串不等
[[ "$VERSION" > "v1.0" ]] # 字典序比较（仅 [[ ]] 支持）

# === 数值判断 ===
# 数值比较必须用 -eq/-ne/-lt/-gt/-le/-ge，不能用 = 或 !=
[ $PORT -eq 8080 ]        # 数值相等
[ $PORT -ne 80 ]          # 数值不等
[ $PORT -lt 1024 ]        # 小于（less than）
[ $PORT -gt 1024 ]        # 大于（greater than）
[ $PORT -le 65535 ]       # 小于等于
[ $PORT -ge 1 ]           # 大于等于

# 数值运算使用双括号 (( ))
TOTAL=10
CURRENT=3
(( REMAINING = TOTAL - CURRENT ))    # 数值运算赋值
echo $REMAINING                       # 输出: 7
(( PORT++ ))                          # 自增，PORT 变量 +1
```

### 3.1.3 循环

**for 循环**

```bash
# 遍历列表
for SVC in user-service order-service payment-service; do
    echo "部署服务: ${SVC}"
    docker pull "registry.example.com/${SVC}:${TAG}"
done

# 遍历数字范围
for i in $(seq 1 5); do            # seq 1 5 生成 1 2 3 4 5
    echo "第 ${i} 次重试..."
    sleep 2
done

# C 风格 for 循环
for ((i=0; i<30; i++)); do
    if curl -sf http://localhost:8080/actuator/health > /dev/null; then
        echo "健康检查通过"
        break
    fi
    echo "等待启动... (${i}/30)"
    sleep 2
done

# 遍历数组
SERVICES=("user-service" "order-service" "payment-service")
for SVC in "${SERVICES[@]}"; do     # "${array[@]}" 逐个展开数组元素
    echo "服务: ${SVC}"
done

# 遍历文件
for f in /opt/config/*.yml; do
    echo "处理配置文件: ${f}"
done
```

**while 循环**

```bash
# 条件为真时持续执行（最常用于健康检查）
RETRY=0
MAX_RETRY=30
while [ $RETRY -lt $MAX_RETRY ]; do
    if curl -sf http://localhost:${PORT}/actuator/health > /dev/null 2>&1; then
        echo "服务启动成功"
        break                          # 健康检查通过，跳出循环
    fi
    RETRY=$((RETRY + 1))
    echo "等待服务启动... (${RETRY}/${MAX_RETRY})"
    sleep 2
done

# 读取文件逐行处理
while IFS= read -r line; do           # IFS= 防止去除前导空格，-r 防止反斜杠转义
    echo "服务器: ${line}"
done < server_list.txt
```

**until 循环**

```bash
# 条件为假时持续执行，直到条件为真（与 while 逻辑相反）
until docker info > /dev/null 2>&1; do
    echo "等待 Docker 启动..."
    sleep 3
done
echo "Docker 已就绪"
```

### 3.1.4 函数

```bash
# 定义函数（两种写法等价）
function log_info() {                  # function 关键字写法
    echo "[INFO] $*"                   # $* 接收函数的所有参数
}

log_error() {                          # 省略 function 关键字写法
    echo "[ERROR] $*" >&2              # >&2 输出到标准错误流
}

# 调用函数（不需要括号，直接写函数名和参数）
log_info "开始部署服务 ${APP_NAME}"
log_error "端口 ${PORT} 已被占用"

# 带返回值的函数
check_port() {
    local port=$1                      # local 声明局部变量，不污染全局作用域
    if ss -tlnp | grep -q ":${port} "; then
        return 1                       # 返回非零表示端口被占用
    fi
    return 0                           # 返回零表示端口空闲
}

check_port 8080
if [ $? -ne 0 ]; then                 # 通过 $? 获取函数返回值
    echo "端口 8080 被占用"
fi

# 更实用的写法：直接在 if 中调用
if ! check_port 8080; then
    echo "端口 8080 被占用"
    exit 1
fi

# 通过 echo 返回字符串值（Shell 函数无法直接 return 字符串）
get_image_id() {
    local name=$1
    local tag=$2
    docker images -q "${name}:${tag}"  # -q 只输出镜像 ID
}
IMAGE_ID=$(get_image_id "user-service" "v1.2.3")
echo "镜像 ID: ${IMAGE_ID}"

# 局部变量（强烈建议函数内都用 local）
deploy_service() {
    local name=$1                      # 函数参数
    local tag=$2
    local container_id                 # 先声明后赋值也可以
    container_id=$(docker run -d --name "${name}" "${name}:${tag}")
    echo "容器 ID: ${container_id}"
    # name/tag/container_id 都是局部变量，函数外不可访问
}
```

### 3.1.5 字符串操作

```bash
STR="registry.example.com/user-service:v1.2.3"

# === 截取 ===
# ${var:offset:length} —— 从 offset 位置截取 length 个字符（offset 从 0 开始）
echo ${STR:0:7}                    # 输出: registry（从第 0 位截取 7 个字符）
echo ${STR:24}                     # 输出: user-service:v1.2.3（省略 length 则截到末尾）

# ${var#pattern}  —— 从头部删除最短匹配
echo ${STR#*/}                     # 输出: user-service:v1.2.3（删除 registry.example.com/）
# ${var##pattern} —— 从头部删除最长匹配
FILE="/opt/app/logs/app.log"
echo ${FILE##*/}                   # 输出: app.log（取文件名，删除最长匹配 */）

# ${var%pattern}  —— 从尾部删除最短匹配
echo ${STR%:*}                     # 输出: registry.example.com/user-service（删除 :v1.2.3）
# ${var%%pattern} —— 从尾部删除最长匹配
echo ${STR%%/*}                    # 输出: registry.example.com（删除最长匹配 /*）

# 常见实战用法：从镜像全名提取各部分
IMAGE="registry.example.com/user-service:v1.2.3"
TAG=${IMAGE##*:}                   # v1.2.3（取冒号后的 tag）
NAME=${IMAGE##*/}                  # user-service:v1.2.3（取最后一个 / 后的部分）
NAME_NO_TAG=${NAME%:*}             # user-service（去掉 tag 部分）
REGISTRY=${IMAGE%%/*}              # registry.example.com（取 registry 部分）

# === 替换 ===
# ${var/pattern/replacement}  —— 替换第一个匹配
echo ${STR/user/order}            # 输出: registry.example.com/order-service:v1.2.3
# ${var//pattern/replacement} —— 替换所有匹配
PATH_STR="/opt/app/bin:/opt/app/lib:/opt/app/config"
echo ${PATH_STR//\/opt\/app/\/usr\/app}
# 输出: /usr/app/bin:/usr/app/lib:/usr/app/config

# === 长度 ===
echo ${#STR}                       # 输出: 43（字符串长度）

# === 大小写 ===
echo ${STR^^}                      # 全部大写: REGISTRY.EXAMPLE.COM/USER-SERVICE:V1.2.3
echo ${STR,,}                      # 全部小写: registry.example.com/user-service:v1.2.3
ENV="PROD"
echo ${ENV,,}                      # prod（常用于规范化环境变量）

# === 默认值 ===
DEPLOY_ENV=${DEPLOY_ENV:-"dev"}    # 如果 DEPLOY_ENV 为空或未设置，则使用 "dev"
IMAGE_TAG=${IMAGE_TAG:?"必须指定镜像标签"}  # 如果为空则报错退出
```

### 3.1.6 数组操作

```bash
# 定义数组
SERVICES=("user-service" "order-service" "payment-service")
PORTS=(8080 8081 8082)

# 访问元素（下标从 0 开始）
echo ${SERVICES[0]}                # user-service
echo ${SERVICES[2]}                # payment-service

# 访问所有元素
echo ${SERVICES[@]}                # user-service order-service payment-service
echo ${SERVICES[*]}                # user-service order-service payment-service

# 数组长度
echo ${#SERVICES[@]}               # 3
echo ${#SERVICES[1]}               # 13（第二个元素的字符串长度："order-service"）

# 添加元素
SERVICES+=("gateway-service")      # 追加到末尾
SERVICES[4]="admin-service"        # 指定下标赋值

# 遍历数组
for i in "${!SERVICES[@]}"; do     # ${!array[@]} 获取所有下标
    echo "服务[${i}]: ${SERVICES[$i]} 端口: ${PORTS[$i]}"
done
# 输出:
# 服务[0]: user-service 端口: 8080
# 服务[1]: order-service 端口: 8081
# 服务[2]: payment-service 端口: 8082

# 切片
echo ${SERVICES[@]:1:2}            # order-service payment-service（从下标 1 取 2 个）

# 删除元素
unset 'SERVICES[2]'                # 删除下标 2 的元素，但下标不会重排
# 删除后: SERVICES=([0]="user-service" [1]="order-service" [3]="gateway-service" ...)

# 关联数组（Bash 4+，类似 Map）
declare -A SERVICE_MAP             # 必须用 declare -A 声明
SERVICE_MAP[user]=8080
SERVICE_MAP[order]=8081
SERVICE_MAP[payment]=8082

for svc in "${!SERVICE_MAP[@]}"; do
    echo "${svc} → 端口 ${SERVICE_MAP[$svc]}"
done
```

---

## 3.2 部署脚本典型结构

一个生产级部署脚本必须按照严格的顺序执行，任何环节出错都应立即中止，避免产生半成品状态。以下是典型结构的逐环节详解。

### 参数解析

```bash
# 使用 getopts 解析命名参数，这是最规范的方式
# :n:t:p:e 中，开头的 : 表示静默错误（脚本自行处理错误提示）
# 每个字母后跟 : 表示该选项需要一个参数值
while getopts ":n:t:p:e:" opt; do
    case $opt in
        n) APP_NAME="$OPTARG" ;;      # -n 服务名
        t) IMAGE_TAG="$OPTARG" ;;     # -t 镜像标签
        p) PORT="$OPTARG" ;;          # -p 端口
        e) ENV="$OPTARG" ;;           # -e 环境
        \?) echo "无效选项: -$OPTARG" >&2; exit 1 ;;
        :)  echo "选项 -$OPTARG 需要参数" >&2; exit 1 ;;
    esac
done
```

**设计要点**：
- 必选参数缺失时脚本应报错退出，不要使用默认值掩盖问题
- 对参数值做合法性校验（如端口范围、环境名白名单）
- 提供 `-h` 帮助选项，方便使用者查看

### 环境检查

```bash
# 1. Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "Docker 未运行，请先启动 Docker" >&2
    exit 1
fi

# 2. 端口是否被占用
if ss -tlnp | grep -q ":${PORT} "; then
    echo "端口 ${PORT} 已被占用" >&2
    exit 1
fi

# 3. 磁盘空间检查（镜像可能几百 MB 到几 GB）
AVAIL_GB=$(df -BG /opt | awk 'NR==2{gsub(/G/,"",$4); print $4}')
if [ "$AVAIL_GB" -lt 5 ]; then
    echo "磁盘剩余空间不足 5GB，当前: ${AVAIL_GB}GB" >&2
    exit 1
fi
```

**设计要点**：
- 环境检查越早越好，避免执行到一半才发现前置条件不满足
- 检查项根据实际情况增减：Docker 版本、内存、内核参数等
- `2>&1` 将错误输出重定向到 /dev/null，避免干扰用户阅读

### 停旧容器

```bash
# 优雅停机：先 SIGTERM，等待应用自行清理（Spring Boot 的 shutdown hook）
# 超时后 SIGKILL 强制终止
if docker ps -a --format '{{.Names}}' | grep -q "^${APP_NAME}$"; then
    echo "停止旧容器 ${APP_NAME}..."
    docker stop --time 30 "${APP_NAME}"   # --time 30: 最多等 30 秒
    docker rm "${APP_NAME}"                # 删除容器（释放名称）
fi
```

**设计要点**：
- `docker stop` 先发 SIGTERM，Java 应用可通过 `server.shutdown=graceful` 优雅关闭
- `--time` 参数要与 Spring Boot 的 `spring.lifecycle.timeout-per-shutdown-phase` 协调
- 必须先 `docker rm`，否则新容器无法使用同名 `--name`
- 如果旧容器不存在，不应报错（幂等性）

### 拉镜像

```bash
# 拉取镜像并校验
docker pull "${REGISTRY}/${APP_NAME}:${IMAGE_TAG}"
# 校验镜像是否真的存在（网络抖动可能导致 pull 失败但未抛出错误码）
if ! docker image inspect "${REGISTRY}/${APP_NAME}:${IMAGE_TAG}" > /dev/null 2>&1; then
    echo "镜像 ${REGISTRY}/${APP_NAME}:${IMAGE_TAG} 不存在" >&2
    exit 1
fi
```

**设计要点**：
- 私有仓库需要先 `docker login`，脚本中可使用 `--password-stdin` 避免密码泄露到进程列表
- 镜像拉取前可以先 `docker image inspect` 检查本地是否已有，避免重复拉取（节省时间）
- 大型镜像考虑使用 `docker pull` 的分层缓存特性，部署前不做 `docker rmi`

### 启新容器

```bash
docker run -d \
    --name "${APP_NAME}" \
    --restart unless-stopped \
    --memory 1g --cpus 1.0 \
    -p "${PORT}:${PORT}" \
    -v /opt/app/logs:/app/logs \
    -e "SPRING_PROFILES_ACTIVE=${ENV}" \
    -e "JAVA_OPTS=-Xms512m -Xmx768m" \
    --health-cmd="curl -sf http://localhost:${PORT}/actuator/health || exit 1" \
    --health-interval=10s \
    --health-timeout=5s \
    --health-retries=3 \
    "${REGISTRY}/${APP_NAME}:${IMAGE_TAG}"
```

**设计要点**：
- `-d` 后台运行，但脚本必须后续检查容器是否真正启动成功（`docker run` 成功只表示创建容器，不表示应用就绪）
- `--restart unless-stopped` 保证进程崩溃后自动重启，但手动 stop 不会重启
- `--memory` / `--cpus` 限制资源，防止一个容器吃光宿主机资源
- `--healthcheck` 让 Docker 引擎持续监控应用健康状态
- `-v` 挂载日志目录到宿主机，容器销毁后日志不丢失

### 健康检查

```bash
# 循环调用健康检查端点，直到成功或超时
MAX_WAIT=60
ELAPSED=0
INTERVAL=3
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf "http://localhost:${PORT}/actuator/health" > /dev/null 2>&1; then
        echo "服务启动成功，耗时 ${ELAPSED} 秒"
        break
    fi
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "服务启动超时（${MAX_WAIT}秒）" >&2
    docker logs --tail 50 "${APP_NAME}"    # 打印最近日志辅助排查
    exit 1
fi
```

**设计要点**：
- 健康检查端点要与 Spring Boot Actuator 的 `/actuator/health` 配合
- 必须有超时上限，否则脚本可能永远挂起
- 失败时打印容器日志，方便运维人员排查
- `curl -sf` 中 `-s` 静默、`-f` 服务器错误时返回非零

### 通知

```bash
# 彩色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'                 # No Color，重置颜色

if [ $DEPLOY_SUCCESS -eq 1 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  部署成功: ${APP_NAME}:${IMAGE_TAG}${NC}"
    echo -e "${GREEN}  端口: ${PORT}  环境: ${ENV}${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  部署失败: ${APP_NAME}:${IMAGE_TAG}${NC}"
    echo -e "${RED}========================================${NC}"
fi
```

**设计要点**：
- 彩色输出在终端中一目了然，但要注意 CI/CD 管道中 ANSI 转义码可能不被识别
- 生产环境建议接入企业微信/钉钉 Webhook 通知
- 通知内容应包含：服务名、版本、环境、耗时、操作人

---

## 3.3 完整 Java 服务部署脚本

以下是一个约 90 行的完整部署脚本，覆盖从参数解析到结果通知的全流程。每一行都有中文注释。

```bash
#!/bin/bash                                                                 # 指定解释器为 bash
# deploy.sh - Java 微服务 Docker 部署脚本                                     # 脚本用途说明
set -euo pipefail                                                           # 严格模式：遇错即停、未定义变量报错、管道错误传递

REGISTRY="registry.example.com"                                             # 私有镜像仓库地址
MAX_HEALTH_WAIT=90                                                          # 健康检查最大等待秒数
HEALTH_INTERVAL=3                                                           # 每次健康检查间隔秒数
GRACEFUL_TIMEOUT=30                                                         # 优雅停机等待秒数
DISK_MIN_GB=5                                                               # 最低磁盘空间要求(GB)

usage() {                                                                   # 定义帮助信息函数
    echo "用法: $0 -n 服务名 -t 镜像标签 -p 端口 -e 环境"
    echo "示例: $0 -n user-service -t v1.2.3 -p 8080 -e prod"
    exit 1
}

while getopts ":n:t:p:e:h" opt; do                                          # 解析命令行参数
    case $opt in
        n) APP_NAME="$OPTARG" ;;                                            # -n 服务名称
        t) IMAGE_TAG="$OPTARG" ;;                                           # -t 镜像标签版本
        p) PORT="$OPTARG" ;;                                                # -p 宿主机映射端口
        e) ENV="$OPTARG" ;;                                                 # -e 部署环境(dev/staging/prod)
        h) usage ;;                                                         # -h 显示帮助
        \?) echo "错误: 无效选项 -$OPTARG" >&2; usage ;;                    # 非法选项
        :)  echo "错误: 选项 -$OPTARG 缺少参数" >&2; usage ;;               # 缺少参数值
    esac
done

[ -z "${APP_NAME:-}" ] && echo "错误: 必须指定服务名(-n)" >&2 && usage      # 校验必选参数
[ -z "${IMAGE_TAG:-}" ] && echo "错误: 必须指定镜像标签(-t)" >&2 && usage   # 校验必选参数
[ -z "${PORT:-}" ] && echo "错误: 必须指定端口(-p)" >&2 && usage            # 校验必选参数
ENV="${ENV:-dev}"                                                           # 环境默认值设为 dev
[[ ! "$PORT" =~ ^[0-9]+$ ]] && echo "错误: 端口必须为数字" >&2 && exit 1    # 校验端口为数字
[[ "$PORT" -lt 1 || "$PORT" -gt 65535 ]] && echo "错误: 端口超出范围" >&2 && exit 1  # 校验端口范围

echo "===== 环境检查 ====="                                                 # 环境检查阶段开始
if ! docker info > /dev/null 2>&1; then                                     # 检查 Docker 是否运行
    echo "错误: Docker 未运行" >&2; exit 1                                  # Docker 未运行则退出
fi
if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then                        # 检查端口是否被占用
    echo "错误: 端口 ${PORT} 已被占用" >&2; exit 1                          # 端口占用则退出
fi
AVAIL_GB=$(df -BG / | awk 'NR==2{gsub(/G/,"",$4); print $4}')              # 获取磁盘可用空间(GB)
if [ "$AVAIL_GB" -lt "$DISK_MIN_GB" ]; then                                # 比较可用空间与最低要求
    echo "错误: 磁盘空间不足 ${DISK_MIN_GB}GB，当前 ${AVAIL_GB}GB" >&2; exit 1  # 空间不足则退出
fi
echo "环境检查通过"                                                         # 环境检查全部通过

echo "===== 停止旧容器 ====="                                               # 停止旧容器阶段
if docker ps -a --format '{{.Names}}' | grep -q "^${APP_NAME}$"; then      # 检查同名容器是否存在
    echo "停止容器: ${APP_NAME}"                                            # 打印停止信息
    docker stop --time "$GRACEFUL_TIMEOUT" "$APP_NAME" > /dev/null          # 优雅停止（先 SIGTERM 再 SIGKILL）
    docker rm "$APP_NAME" > /dev/null                                       # 删除已停止的容器（释放名称）
    echo "旧容器已移除"                                                      # 确认移除
else
    echo "未发现旧容器，跳过"                                                 # 容器不存在则跳过
fi

echo "===== 拉取镜像 ====="                                                 # 拉取镜像阶段
FULL_IMAGE="${REGISTRY}/${APP_NAME}:${IMAGE_TAG}"                           # 拼接完整镜像地址
echo "拉取镜像: ${FULL_IMAGE}"                                              # 打印镜像地址
docker pull "$FULL_IMAGE"                                                   # 从仓库拉取镜像
if ! docker image inspect "$FULL_IMAGE" > /dev/null 2>&1; then              # 校验镜像是否真实存在
    echo "错误: 镜像拉取失败或不存在" >&2; exit 1                           # 校验失败则退出
fi
IMAGE_SIZE=$(docker image inspect "$FULL_IMAGE" --format '{{.Size}}')       # 获取镜像大小(字节)
echo "镜像拉取成功，大小: $((IMAGE_SIZE / 1024 / 1024))MB"                  # 打印镜像大小

echo "===== 启动容器 ====="                                                 # 启动新容器阶段
docker run -d \                                                             # -d 后台运行
    --name "$APP_NAME" \                                                    # 容器名称（与旧容器同名）
    --restart unless-stopped \                                              # 异常退出自动重启（手动 stop 除外）
    --memory 1g \                                                           # 内存限制 1GB
    --memory-swap 1g \                                                      # swap 限制也为 1g（即禁用 swap）
    --cpus 1.0 \                                                            # CPU 限额 1 核
    -p "${PORT}:${PORT}" \                                                  # 端口映射：宿主机:容器
    -v "/opt/app/${APP_NAME}/logs:/app/logs" \                              # 日志目录挂载
    -v "/opt/app/${APP_NAME}/config:/app/config" \                          # 外部配置目录挂载
    -e "SPRING_PROFILES_ACTIVE=${ENV}" \                                    # Spring 环境 Profile
    -e "JAVA_OPTS=-Xms512m -Xmx768m -XX:+UseG1GC" \                        # JVM 参数（堆 512m-768m，G1 垃圾回收器）
    -e "TZ=Asia/Shanghai" \                                                 # 时区设置
    --health-cmd="curl -sf http://localhost:${PORT}/actuator/health || exit 1" \  # 健康检查命令
    --health-interval=10s \                                                 # 每 10 秒检查一次
    --health-timeout=5s \                                                   # 单次检查超时 5 秒
    --health-retries=3 \                                                    # 连续 3 次失败才标记 unhealthy
    --health-start-period=40s \                                             # 容器启动后 40 秒内不计入重试次数
    "$FULL_IMAGE"                                                           # 镜像名称:标签

CONTAINER_ID=$(docker ps -q --filter "name=${APP_NAME}")                    # 获取新容器短 ID
echo "容器已创建: ${CONTAINER_ID}"                                          # 打印容器 ID

echo "===== 健康检查 ====="                                                 # 健康检查阶段
ELAPSED=0                                                                   # 已等待时间计数器
while [ $ELAPSED -lt $MAX_HEALTH_WAIT ]; do                                 # 循环直到超时
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$APP_NAME" 2>/dev/null || echo "unknown")  # 读取容器健康状态
    case $HEALTH in
        healthy)                                                            # 状态为 healthy
            echo -e "\033[0;32m服务启动成功，耗时 ${ELAPSED} 秒\033[0m"       # 绿色输出成功
            break ;;                                                        # 跳出循环
        unhealthy)                                                          # 状态为 unhealthy
            echo -e "\033[0;31m健康检查失败，服务状态: unhealthy\033[0m"       # 红色输出失败
            docker logs --tail 50 "$APP_NAME"                               # 打印最近 50 行日志
            exit 1 ;;                                                       # 退出脚本
        *)                                                                  # starting 或 unknown
            echo "等待服务就绪... (${ELAPSED}/${MAX_HEALTH_WAIT}s) 状态: ${HEALTH}"  # 打印等待进度
            sleep "$HEALTH_INTERVAL"                                        # 等待间隔秒数
            ELAPSED=$((ELAPSED + HEALTH_INTERVAL)) ;;                       # 累加已等待时间
    esac
done

if [ $ELAPSED -ge $MAX_HEALTH_WAIT ]; then                                 # 判断是否超时
    echo -e "\033[0;31m健康检查超时(${MAX_HEALTH_WAIT}秒)\033[0m"             # 红色超时提示
    docker logs --tail 50 "$APP_NAME"                                       # 打印日志辅助排查
    exit 1                                                                  # 以失败退出
fi

echo "===== 部署完成 ====="                                                 # 部署成功汇总
echo -e "\033[0;32m==========================================\033[0m"        # 绿色分隔线
echo -e "\033[0;32m  服务: ${APP_NAME}    版本: ${IMAGE_TAG}\033[0m"         # 服务名和版本
echo -e "\033[0;32m  端口: ${PORT}       环境: ${ENV}\033[0m"               # 端口和环境
echo -e "\033[0;32m  容器: ${CONTAINER_ID}\033[0m"                          # 容器 ID
echo -e "\033[0;32m==========================================\033[0m"        # 绿色分隔线
```

**使用方式**：

```bash
# 赋予执行权限
chmod +x deploy.sh

# 执行部署
./deploy.sh -n user-service -t v1.2.3 -p 8080 -e prod

# 查看帮助
./deploy.sh -h
```

---

## 3.4 蓝绿部署脚本

### 蓝绿切换逻辑详解

蓝绿部署的核心思想是同时维护两套完全相同的生产环境——"蓝"和"绿"。任意时刻只有一套环境对外提供服务，另一套处于待命状态。部署新版本时，先将新版本部署到空闲环境，验证通过后通过切换流量入口（通常是 Nginx 或负载均衡器）将请求导向新环境。

```
当前状态：蓝环境(v1.0) ← 流量    绿环境(v1.1) 待命

部署步骤：
1. 将 v1.2 部署到绿环境（当前空闲）
2. 验证绿环境健康
3. 切换流量：蓝环境(v1.0) 待命    绿环境(v1.2) ← 流量
4. 如有问题：切回蓝环境（即回滚）

下次部署：
1. 将 v1.3 部署到蓝环境（当前空闲）
2. 验证蓝环境健康
3. 切换流量：蓝环境(v1.3) ← 流量    绿环境(v1.2) 待命
```

**关键设计原则**：
- 蓝绿环境通过容器命名区分（如 `app-blue` / `app-green`）
- 流量切换必须原子化，不能出现同时指向两个环境的情况
- 切换前必须确认目标环境健康，否则不切换
- 旧环境在切换后保留一段时间，用于可能的快速回滚

### 两个容器交替部署脚本

```bash
#!/bin/bash
set -euo pipefail

APP_NAME=${1:?"用法: $0 <服务名> <镜像标签>"}
IMAGE_TAG=${2:?"用法: $0 <服务名> <镜像标签>"}
REGISTRY="registry.example.com"
PORT_BLUE=8080                            # 蓝环境端口
PORT_GREEN=8081                           # 绿环境端口
NGINX_CONF="/etc/nginx/conf.d/upstream.conf"

# 确定当前活跃环境：读取 Nginx upstream 配置判断流量指向
if grep -q "server 127.0.0.1:${PORT_BLUE};" "$NGINX_CONF" 2>/dev/null; then
    ACTIVE="blue"
    STANDBY="green"
    STANDBY_PORT=$PORT_GREEN
elif grep -q "server 127.0.0.1:${PORT_GREEN};" "$NGINX_CONF" 2>/dev/null; then
    ACTIVE="green"
    STANDBY="blue"
    STANDBY_PORT=$PORT_BLUE
else
    ACTIVE="none"
    STANDBY="blue"                        # 首次部署默认先部署蓝环境
    STANDBY_PORT=$PORT_BLUE
fi

echo "当前活跃: ${ACTIVE}，部署目标: ${STANDBY}"

# 部署到待命环境
CONTAINER_NAME="${APP_NAME}-${STANDBY}"
FULL_IMAGE="${REGISTRY}/${APP_NAME}:${IMAGE_TAG}"

# 如果待命容器已存在，先停止移除
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker stop --time 30 "$CONTAINER_NAME" > /dev/null
    docker rm "$CONTAINER_NAME" > /dev/null
fi

# 拉取并启动新容器到待命环境
docker pull "$FULL_IMAGE"
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --memory 1g --cpus 1.0 \
    -p "${STANDBY_PORT}:${STANDBY_PORT}" \
    -e "SERVER_PORT=${STANDBY_PORT}" \
    -e "SPRING_PROFILES_ACTIVE=prod" \
    -e "JAVA_OPTS=-Xms512m -Xmx768m" \
    --health-cmd="curl -sf http://localhost:${STANDBY_PORT}/actuator/health || exit 1" \
    --health-interval=10s --health-timeout=5s --health-retries=3 \
    --health-start-period=40s \
    "$FULL_IMAGE"

# 健康检查：等待待命环境就绪
ELAPSED=0
while [ $ELAPSED -lt 90 ]; do
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    if [ "$HEALTH" = "healthy" ]; then
        echo "${STANDBY} 环境就绪"
        break
    fi
    [ "$HEALTH" = "unhealthy" ] && echo "${STANDBY} 环境不健康，中止切换" >&2 && exit 1
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
[ $ELAPSED -ge 90 ] && echo "待命环境启动超时" >&2 && exit 1

# 切换 Nginx upstream 指向待命环境（原子切换）
echo "切换流量到 ${STANDBY} 环境..."
cat > "$NGINX_CONF" <<EOF
upstream ${APP_NAME} {
    server 127.0.0.1:${STANDBY_PORT};
}
EOF
nginx -s reload                            # 优雅重载 Nginx（不中断现有连接）

echo -e "\033[0;32m蓝绿部署完成: ${STANDBY}(v${IMAGE_TAG}) 现在是活跃环境\033[0m"
echo "旧环境 ${ACTIVE} 保持运行，可用于回滚"
```

### Nginx 切换 upstream 的方式

```nginx
# /etc/nginx/conf.d/upstream.conf —— 蓝绿 upstream 配置文件
# 切换只需要修改这一个文件，然后 nginx -s reload

# 蓝环境活跃时：
upstream user-service {
    server 127.0.0.1:8080;                 # 蓝
}

# 绿环境活跃时（替换为以下内容）：
upstream user-service {
    server 127.0.0.1:8081;                 # 绿
}
```

```bash
# 脚本中切换 upstream 的几种方式：

# 方式 1：直接写入新配置（如上面脚本所用）
cat > "$NGINX_CONF" <<EOF
upstream ${APP_NAME} {
    server 127.0.0.1:${STANDBY_PORT};
}
EOF
nginx -s reload

# 方式 2：使用 sed 替换端口号（适合配置复杂的场景）
sed -i "s/server 127.0.0.1:${ACTIVE_PORT};/server 127.0.0.1:${STANDBY_PORT};/" "$NGINX_CONF"
nginx -s reload

# 方式 3：使用符号链接切换（最原子化的方式）
# 提前准备好两个配置文件
# /etc/nginx/conf.d/upstream-blue.conf
# /etc/nginx/conf.d/upstream-green.conf
# 切换时：
ln -sfn /etc/nginx/upstream-configs/upstream-green.conf /etc/nginx/conf.d/upstream-active.conf
nginx -s reload
# -f 强制替换已有符号链接，-n 不跟踪已有链接，保证原子性
```

---

## 3.5 回滚脚本

### 镜像版本历史管理

```bash
# 查看某个服务的所有镜像版本历史
docker images --format "{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}\t{{.Size}}" \
    | grep "${APP_NAME}" \
    | sort -k2

# 输出示例：
# registry.example.com/user-service:v1.2.3    2026-05-24 10:30:00    280MB
# registry.example.com/user-service:v1.2.2    2026-05-20 14:15:00    278MB
# registry.example.com/user-service:v1.2.1    2026-05-15 09:00:00    275MB
# registry.example.com/user-service:v1.2.0    2026-05-10 16:45:00    270MB

# 查看容器创建时使用的镜像（定位当前运行版本）
docker inspect --format '{{.Config.Image}}' "${APP_NAME}"
# 输出: registry.example.com/user-service:v1.2.3

# 获取当前容器使用的镜像 ID，反查 tag
CURRENT_IMAGE_ID=$(docker inspect --format '{{.Image}}' "${APP_NAME}")
docker image inspect --format '{{index .RepoTags 0}}' "$CURRENT_IMAGE_ID"
# 输出: registry.example.com/user-service:v1.2.3
```

### 回滚脚本完整示例

```bash
#!/bin/bash
set -euo pipefail

APP_NAME=${1:?"用法: $0 <服务名> [目标版本]"}
ROLLBACK_TAG=${2:-""}                      # 可选：指定回滚版本，为空则自动取上一版本
REGISTRY="registry.example.com"
GRACEFUL_TIMEOUT=30

# 获取当前运行版本
CURRENT_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$APP_NAME" 2>/dev/null || echo "")
if [ -z "$CURRENT_IMAGE" ]; then
    echo "错误: 容器 ${APP_NAME} 不存在" >&2; exit 1
fi
CURRENT_TAG=${CURRENT_IMAGE##*:}           # 提取当前 tag
echo "当前版本: ${CURRENT_TAG}"

# 确定回滚目标版本
if [ -n "$ROLLBACK_TAG" ]; then
    TARGET_TAG="$ROLLBACK_TAG"             # 用户显式指定
else
    # 自动查找上一版本：列出所有 tag，排除当前版本，取最近一个
    TARGET_TAG=$(docker images --format "{{.Tag}}" "${REGISTRY}/${APP_NAME}" \
        | grep -v "^${CURRENT_TAG}$" \
        | head -1)
    if [ -z "$TARGET_TAG" ]; then
        echo "错误: 未找到可回滚的版本" >&2; exit 1
    fi
fi
echo "回滚目标: ${TARGET_TAG}"

# 确认回滚（生产环境应加入人工确认环节）
echo "即将从 ${CURRENT_TAG} 回滚到 ${TARGET_TAG}，按 Ctrl+C 取消..."
sleep 5                                    # 留 5 秒反悔时间

# 确认目标镜像本地存在（回滚通常不需要重新拉取）
TARGET_IMAGE="${REGISTRY}/${APP_NAME}:${TARGET_TAG}"
if ! docker image inspect "$TARGET_IMAGE" > /dev/null 2>&1; then
    echo "本地未找到镜像 ${TARGET_IMAGE}，尝试从仓库拉取..."
    docker pull "$TARGET_IMAGE"            # 本地不存在则尝试拉取
fi

# 提取当前容器的运行参数（端口映射、环境变量、挂载等）
PORT=$(docker port "$APP_NAME" 2>/dev/null | head -1 | cut -d: -f2 || echo "8080")
# 如果 docker port 输出 "8080/tcp -> 0.0.0.0:8080"，则提取宿主机端口
HOST_PORT=$(docker port "$APP_NAME" 2>/dev/null | head -1 | sed 's/.*://' || echo "8080")
ENV=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$APP_NAME" \
    | grep SPRING_PROFILES_ACTIVE | cut -d= -f2 || echo "dev")

echo "停止当前容器..."
docker stop --time "$GRACEFUL_TIMEOUT" "$APP_NAME" > /dev/null
docker rm "$APP_NAME" > /dev/null

echo "启动回滚版本..."
docker run -d \
    --name "$APP_NAME" \
    --restart unless-stopped \
    --memory 1g --cpus 1.0 \
    -p "${HOST_PORT}:${PORT}" \
    -e "SPRING_PROFILES_ACTIVE=${ENV}" \
    -e "JAVA_OPTS=-Xms512m -Xmx768m" \
    --health-cmd="curl -sf http://localhost:${PORT}/actuator/health || exit 1" \
    --health-interval=10s --health-timeout=5s --health-retries=3 \
    --health-start-period=40s \
    "$TARGET_IMAGE"

# 健康检查
ELAPSED=0
while [ $ELAPSED -lt 90 ]; do
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$APP_NAME" 2>/dev/null || echo "unknown")
    [ "$HEALTH" = "healthy" ] && echo -e "\033[0;32m回滚成功: ${TARGET_TAG}\033[0m" && exit 0
    [ "$HEALTH" = "unhealthy" ] && echo -e "\033[0;31m回滚失败: 新版本也不健康\033[0m" >&2 && exit 1
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
echo -e "\033[0;31m回滚超时\033[0m" >&2
exit 1
```

**使用方式**：

```bash
# 自动回滚到上一版本
./rollback.sh user-service

# 回滚到指定版本
./rollback.sh user-service v1.2.1
```

---

## 3.6 批量部署脚本

### 服务器列表配置

```bash
# server_list.txt —— 服务器列表文件
# 格式：IP 用户 SSH端口 服务列表(逗号分隔)
# 注意：此文件包含敏感信息，权限应设为 600
10.0.1.10  deploy  22  user-service,order-service
10.0.1.11  deploy  22  payment-service,gateway-service
10.0.1.12  deploy  22  admin-service
```

### SSH 密钥与 sshpass

```bash
# 推荐方式：SSH 密钥认证（无密码明文风险）
# 1. 生成密钥对（如果还没有）
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""
# -t ed25519: 使用 Ed25519 算法（比 RSA 更安全更快）
# -f: 指定密钥文件路径
# -N "": 空密码短语（自动化场景需要，但密钥文件权限必须为 600）

# 2. 分发公钥到目标服务器
ssh-copy-id -i ~/.ssh/deploy_key.pub -p 22 deploy@10.0.1.10
# 将公钥追加到目标服务器的 ~/.ssh/authorized_keys

# 3. 脚本中使用密钥连接
ssh -i ~/.ssh/deploy_key -o StrictHostKeyChecking=no deploy@10.0.1.10 "docker ps"
# -i: 指定私钥文件
# -o StrictHostKeyChecking=no: 跳过主机密钥确认（首次连接自动化必须）

# 备选方式：sshpass 密码认证（不推荐，密码可能泄露到进程列表）
# 安装 sshpass
# CentOS: yum install -y sshpass
# Ubuntu: apt-get install -y sshpass

# 使用 sshpass
SSHPASS="your-password" sshpass -e ssh -o StrictHostKeyChecking=no deploy@10.0.1.10 "docker ps"
# -e: 从环境变量 SSHPASS 读取密码（比 -p 'password' 更安全，后者会暴露在进程列表中）
# 绝对不要使用: sshpass -p 'your-password' ssh ...（ps 命令可见）
```

### 并行部署 vs 串行部署

```bash
# === 串行部署（逐台执行）===
# 优点：安全可控，某台失败后可立即停止
# 缺点：慢，10 台服务器每台 2 分钟 = 20 分钟
while IFS=' ' read -r ip user port services; do
    echo "部署到 ${ip}..."
    ssh -i ~/.ssh/deploy_key -p "$port" "${user}@${ip}" \
        "bash /opt/scripts/deploy.sh -n ${APP_NAME} -t ${IMAGE_TAG} -p ${PORT} -e ${ENV}"
done < server_list.txt

# === 并行部署（后台 & + wait）===
# 优点：快，10 台并行 = 约 2 分钟
# 缺点：需要额外处理错误收集和汇总
pids=()                                    # 存放所有后台进程 PID
results=()                                 # 存放各服务器部署结果

while IFS=' ' read -r ip user port services; do
    ssh -i ~/.ssh/deploy_key -p "$port" "${user}@${ip}" \
        "bash /opt/scripts/deploy.sh -n ${APP_NAME} -t ${IMAGE_TAG} -p ${PORT} -e ${ENV}" \
        > "/tmp/deploy_${ip}.log" 2>&1 &   # & 放入后台执行，日志重定向到文件
    pids+=($!)                             # 记录后台进程 PID
    echo "已启动 ${ip} 部署，PID: $!"
done < server_list.txt

# 等待所有后台进程完成
for i in "${!pids[@]}"; do
    if wait "${pids[$i]}"; then            # wait 等待指定 PID，返回其退出码
        echo "服务器 $((i+1)) 部署成功"
    else
        echo "服务器 $((i+1)) 部署失败"
    fi
done
```

### 批量部署脚本示例

```bash
#!/bin/bash
set -euo pipefail

APP_NAME=${1:?"用法: $0 <服务名> <镜像标签> [并行度]"}
IMAGE_TAG=${2:?"用法: $0 <服务名> <镜像标签> [并行度]"}
PARALLEL=${3:-3}                           # 默认并行度 3
REGISTRY="registry.example.com"
PORT=8080
ENV="prod"
SSH_KEY="~/.ssh/deploy_key"
SERVER_LIST="/opt/scripts/server_list.txt"
LOG_DIR="/tmp/deploy_logs"
DEPLOY_SCRIPT="/opt/scripts/deploy.sh"

mkdir -p "$LOG_DIR"

# 并发控制函数：确保同时运行的后台任务不超过 PARALLEL 个
wait_for_slot() {
    while [ "$(jobs -r | wc -l)" -ge "$PARALLEL" ]; do
        sleep 1                            # 当前后台任务数 >= PARALLEL 时等待
    done
}

echo "===== 批量部署开始 ====="
echo "服务: ${APP_NAME}  版本: ${IMAGE_TAG}  并行度: ${PARALLEL}"

SUCCESS_COUNT=0
FAIL_COUNT=0
TOTAL=0

while IFS=' ' read -r ip user port services; do
    # 跳过注释行和空行
    [[ "$ip" =~ ^#.*$ ]] && continue
    [[ -z "$ip" ]] && continue

    # 检查该服务器是否需要部署此服务
    if ! echo "$services" | grep -qw "$APP_NAME"; then
        echo "跳过 ${ip}（不部署 ${APP_NAME}）"
        continue
    fi

    TOTAL=$((TOTAL + 1))
    wait_for_slot                          # 等待空闲槽位

    # 后台执行 SSH 部署
    (
        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            -p "$port" "${user}@${ip}" \
            "bash ${DEPLOY_SCRIPT} -n ${APP_NAME} -t ${IMAGE_TAG} -p ${PORT} -e ${ENV}" \
            > "${LOG_DIR}/deploy_${ip}.log" 2>&1
        exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo -e "\033[0;32m[成功] ${ip}\033[0m"
        else
            echo -e "\033[0;31m[失败] ${ip} (退出码: ${exit_code})\033[0m"
            echo "--- ${ip} 日志 ---"
            tail -20 "${LOG_DIR}/deploy_${ip}.log"
            echo "--- 日志结束 ---"
        fi
        exit $exit_code
    ) &
done < "$SERVER_LIST"

# 等待所有后台任务完成
wait

# 统计结果（遍历日志文件判断成功/失败）
for log_file in "${LOG_DIR}"/deploy_*.log; do
    ip=$(basename "$log_file" | sed 's/deploy_//;s/\.log//')
    TOTAL=$((TOTAL + 0))                   # 已在循环中计数
done

echo "===== 批量部署完成 ====="
echo "总计: ${TOTAL} 台服务器"
echo "详细日志目录: ${LOG_DIR}"
```

**使用方式**：

```bash
# 并行度 3 部署
./batch_deploy.sh user-service v1.2.3 3

# 并行度 1 即串行
./batch_deploy.sh user-service v1.2.3 1
```

---

## 3.7 脚本最佳实践

### set -euo pipefail 详解

```bash
#!/bin/bash
set -euo pipefail

# set -e：任何命令返回非零退出码时，立即终止脚本
# 不加 -e 时：
mkdir /nonexistent/path/app    # 失败，但脚本继续执行
cd /nonexistent/path/app       # 进入错误目录，后续操作可能造成严重后果
rm -rf *                       # 在错误目录下删除文件！灾难性后果

# 加了 -e 后：
# mkdir 失败 → 脚本立即终止 → 不会执行后续危险操作

# set -e 的例外情况（不会触发退出）：
if command_that_might_fail; then ... fi    # if 条件中的命令
command || true                            # || 后有备选命令
command || echo "失败但无所谓"              # 同上

# set -u：引用未定义变量时报错退出
# 不加 -u 时：
rm -rf /opt/app/${APP_NAME}/logs
# 如果 APP_NAME 未定义，展开为: rm -rf /opt/app//logs → 可能删除错误路径
# 加了 -u 后：直接报错 "APP_NAME: unbound variable"

# 常见兼容写法（变量可能未定义但需要默认值）：
echo "${MAYBE_EMPTY:-default}"             # 用 :- 提供默认值，避免 -u 报错

# set -o pipefail：管道中任何命令失败，整个管道返回失败退出码
# 不加 pipefail 时：
cat missing_file | grep "error" | wc -l
# cat 失败，但 wc -l 返回 0，管道退出码为 0（最后一个命令的退出码）
# 脚本误以为成功

# 加了 pipefail 后：
# cat 失败 → 管道退出码为 cat 的非零退出码
# set -e 捕获到非零退出码 → 脚本终止

# 三个选项组合 = 防御性编程的基础
# -e 防止错误累积   -u 防止拼写错误   pipefail 防止管道掩盖错误
```

### 日志函数

```bash
# 日志函数：带时间戳、颜色、级别
LOG_LEVEL="INFO"                           # 可通过环境变量调整日志级别

# 颜色定义
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'                               # 重置颜色

# 时间戳格式
TIMESTAMP='date +"%Y-%m-%d %H:%M:%S"'      # 注意这里是命令替换的延迟求值

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$($TIMESTAMP)

    # 级别过滤：只输出 >= LOG_LEVEL 的日志
    local -A level_num=([DEBUG]=0 [INFO]=1 [WARN]=2 [ERROR]=3)
    if [ "${level_num[$level]:-1}" -lt "${level_num[$LOG_LEVEL]:-1}" ]; then
        return
    fi

    # 根据级别选择颜色
    local color=""
    case $level in
        DEBUG) color=$BLUE ;;
        INFO)  color=$GREEN ;;
        WARN)  color=$YELLOW ;;
        ERROR) color=$RED ;;
    esac

    # 输出：ERROR/WARN 到 stderr，其余到 stdout
    if [ "$level" = "ERROR" ] || [ "$level" = "WARN" ]; then
        echo -e "${color}[${timestamp}] [${level}] ${message}${NC}" >&2
    else
        echo -e "${color}[${timestamp}] [${level}] ${message}${NC}"
    fi
}

# 使用示例
log DEBUG "开始解析参数"                    # 蓝色，LOG_LEVEL=INFO 时不显示
log INFO  "拉取镜像: ${FULL_IMAGE}"         # 绿色
log WARN  "磁盘空间偏低: ${AVAIL_GB}GB"     # 黄色，输出到 stderr
log ERROR "端口 ${PORT} 已被占用"           # 红色，输出到 stderr
```

### 错误处理与 trap

```bash
# trap 捕获信号和错误，用于清理和通知
cleanup() {
    local exit_code=$?
    log INFO "脚本退出，退出码: ${exit_code}"
    # 清理临时文件
    rm -f /tmp/deploy_${APP_NAME}_*.tmp
    # 如果部署失败且容器已创建但未就绪，考虑回滚
    if [ $exit_code -ne 0 ] && docker ps -a --format '{{.Names}}' | grep -q "^${APP_NAME}$"; then
        log WARN "部署异常退出，容器 ${APP_NAME} 可能处于不一致状态"
    fi
}

# 捕获脚本退出（无论何种原因退出都会触发）
trap cleanup EXIT

# 捕获特定信号
trap 'log INFO "收到 SIGINT，正在优雅退出..."; exit 130' INT   # Ctrl+C
trap 'log INFO "收到 SIGTERM，正在优雅退出..."; exit 143' TERM  # kill 命令

# 捕获错误行号（调试利器）
on_error() {
    local line_no=$1
    local func_name=${FUNCNAME[1]:-main}
    local command="${BASH_COMMAND}"
    log ERROR "命令执行失败: ${command}"
    log ERROR "位置: ${BASH_SOURCE[1]:-$0}:${line_no} (函数: ${func_name})"
}
trap 'on_error $LINENO' ERR

# 完整示例：部署脚本中的 trap 应用
#!/bin/bash
set -euo pipefail

APP_NAME=""
NEW_CONTAINER_ID=""
OLD_CONTAINER_ID=""

on_error() {
    local line=$1
    echo -e "\033[0;31m[ERROR] 第 ${line} 行执行失败\033[0m" >&2
    # 自动回滚：如果新容器已创建但部署失败，尝试恢复旧容器
    if [ -n "$NEW_CONTAINER_ID" ] && [ -z "$OLD_CONTAINER_ID" ]; then
        echo "正在清理失败的容器..."
        docker rm -f "$NEW_CONTAINER_ID" 2>/dev/null || true
    fi
}

cleanup() {
    rm -f /tmp/deploy_${APP_NAME}_*.tmp
}

trap 'on_error $LINENO' ERR
trap cleanup EXIT
```

### 超时重试模式

```bash
# retry 函数：带指数退避的重试
# 参数：$1=最大重试次数 $2=初始间隔秒数 $3...=要执行的命令
retry() {
    local max_attempts=$1
    local interval=$2
    shift 2
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        echo "尝试第 ${attempt}/${max_attempts} 次: $*"
        if "$@"; then                      # 执行传入的命令
            echo "第 ${attempt} 次尝试成功"
            return 0
        fi

        if [ $attempt -lt $max_attempts ]; then
            local wait_time=$((interval * (2 ** (attempt - 1))))  # 指数退避
            local max_wait=60
            [ $wait_time -gt $max_wait ] && wait_time=$max_wait   # 上限 60 秒
            echo "等待 ${wait_time} 秒后重试..."
            sleep $wait_time
        fi
        attempt=$((attempt + 1))
    done

    echo "重试 ${max_attempts} 次后仍然失败: $*" >&2
    return 1
}

# 使用示例
retry 3 5 docker pull "${FULL_IMAGE}"      # 最多重试 3 次，间隔 5→10→20 秒
retry 5 2 curl -sf "http://localhost:${PORT}/actuator/health"  # 健康检查重试

# timeout 函数：给命令加超时限制
# 使用 GNU timeout 命令（大多数 Linux 发行版自带）
timeout 60s docker pull "${FULL_IMAGE}"
if [ $? -eq 124 ]; then                   # 124 是 timeout 命令的专属退出码
    echo "镜像拉取超时" >&2
    exit 1
fi

# 纯 Shell 实现超时（无 GNU timeout 时）
run_with_timeout() {
    local timeout_sec=$1
    shift
    local cmd="$*"

    $cmd &                                 # 后台执行命令
    local pid=$!                           # 获取后台 PID

    local elapsed=0
    while [ $elapsed -lt $timeout_sec ]; do
        if ! kill -0 "$pid" 2>/dev/null; then  # kill -0 检测进程是否存在
            wait "$pid"                    # 进程已结束，获取退出码
            return $?
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    kill -9 "$pid" 2>/dev/null             # 超时，强制终止
    return 124                             # 模拟 timeout 退出码
}
```

### 锁文件防并发

```bash
# 使用 flock 防止脚本并发执行
# 场景：定时部署任务可能重叠，或多人同时触发部署

LOCK_FILE="/var/lock/deploy_${APP_NAME}.lock"

# 方式 1：整个脚本加锁（推荐，最简洁）
# 在脚本开头加入：
exec 200>"$LOCK_FILE"                      # 打开文件描述符 200 指向锁文件
flock -n 200 || {                          # -n 非阻塞模式尝试获取锁
    echo "另一个部署正在进行中，请稍后再试" >&2
    exit 1
}
# 获取锁成功后，脚本执行期间持有锁
# 脚本退出时文件描述符自动关闭，锁释放

# 方式 2：仅对关键区段加锁
deploy_critical_section() {
    local lock_file="/var/lock/deploy_${APP_NAME}.lock"
    (
        flock -n 9 || {                    # 子 shell 中获取锁，fd 9
            echo "部署锁获取失败" >&2
            exit 1
        }
        # 以下代码在锁保护下执行
        docker stop --time 30 "$APP_NAME"
        docker rm "$APP_NAME"
        docker run -d --name "$APP_NAME" "$FULL_IMAGE"
    ) 9>"$lock_file"                       # 子 shell 的 fd 9 重定向到锁文件
}

# 方式 3：带超时的锁等待
exec 200>"$LOCK_FILE"
if ! flock -w 300 200; then               # -w 300: 最多等 300 秒
    echo "等待部署锁超时(300秒)，可能存在死锁" >&2
    exit 1
fi

# 方式 4：不使用 flock（兼容性方案，但不如 flock 原子）
LOCK_FILE="/tmp/deploy_${APP_NAME}.lock"
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "进程 ${OLD_PID} 正在部署" >&2
        exit 1
    fi
    # 锁文件存在但进程已死，清理过期锁
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"                     # 写入当前 PID
trap 'rm -f "$LOCK_FILE"' EXIT            # 退出时清理锁文件
```

### 脚本模板骨架

```bash
#!/bin/bash
###############################################################################
# 脚本名称: deploy_template.sh
# 功能描述: Java 微服务 Docker 部署脚本模板
# 使用方式: ./deploy_template.sh -n <服务名> -t <镜像标签> -p <端口> [-e <环境>]
# 维护人员: DevOps Team
# 创建日期: 2026-05-25
# 变更记录:
#   2026-05-25  初始版本
###############################################################################

set -euo pipefail                          # 严格模式

# ========================= 常量定义 =========================
readonly SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)   # 脚本所在目录（绝对路径）
readonly SCRIPT_NAME=$(basename "$0")      # 脚本文件名
readonly REGISTRY="registry.example.com"   # 镜像仓库地址
readonly LOCK_DIR="/var/lock"              # 锁文件目录
readonly LOG_DIR="/var/log/deploy"         # 日志目录
readonly MAX_HEALTH_WAIT=90                # 健康检查超时(秒)
readonly HEALTH_INTERVAL=3                 # 健康检查间隔(秒)
readonly GRACEFUL_TIMEOUT=30               # 优雅停机超时(秒)
readonly DISK_MIN_GB=5                     # 最低磁盘空间(GB)

# ========================= 颜色定义 =========================
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# ========================= 日志函数 =========================
log() {
    local level=$1; shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color=""
    case $level in
        DEBUG) color=$BLUE ;;
        INFO)  color=$GREEN ;;
        WARN)  color=$YELLOW ;;
        ERROR) color=$RED ;;
    esac
    if [ "$level" = "ERROR" ] || [ "$level" = "WARN" ]; then
        echo -e "${color}[${timestamp}] [${level}] ${message}${NC}" >&2
    else
        echo -e "${color}[${timestamp}] [${level}] ${message}${NC}"
    fi
}

# ========================= 错误处理 =========================
on_error() {
    local line=$1
    log ERROR "命令失败: ${BASH_COMMAND} (${SCRIPT_NAME}:${line})"
}

cleanup() {
    local exit_code=$?
    rm -f "${LOCK_DIR}/deploy_${APP_NAME:-unknown}.lock"
    log DEBUG "脚本退出，退出码: ${exit_code}"
    exit $exit_code
}

trap 'on_error $LINENO' ERR
trap cleanup EXIT

# ========================= 并发锁 =========================
acquire_lock() {
    local lock_file="${LOCK_DIR}/deploy_${APP_NAME}.lock"
    exec 200>"$lock_file"
    flock -n 200 || {
        log ERROR "另一个部署正在执行中"
        exit 1
    }
}

# ========================= 重试函数 =========================
retry() {
    local max_attempts=$1
    local interval=$2
    shift 2
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        if "$@"; then
            return 0
        fi
        local wait_time=$((interval * 2 ** (attempt - 1)))
        [ $wait_time -gt 60 ] && wait_time=60
        log WARN "第 ${attempt} 次失败，${wait_time}s 后重试: $*"
        sleep $wait_time
        attempt=$((attempt + 1))
    done
    log ERROR "重试 ${max_attempts} 次后仍然失败: $*"
    return 1
}

# ========================= 环境检查 =========================
preflight_check() {
    log INFO "环境预检..."

    docker info > /dev/null 2>&1 || { log ERROR "Docker 未运行"; exit 1; }

    if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        log ERROR "端口 ${PORT} 已被占用"
        exit 1
    fi

    local avail_gb
    avail_gb=$(df -BG / | awk 'NR==2{gsub(/G/,"",$4); print $4}')
    if [ "$avail_gb" -lt "$DISK_MIN_GB" ]; then
        log ERROR "磁盘空间不足: ${avail_gb}GB < ${DISK_MIN_GB}GB"
        exit 1
    fi

    log INFO "环境预检通过"
}

# ========================= 参数解析 =========================
APP_NAME=""
IMAGE_TAG=""
PORT=""
ENV="dev"

usage() {
    cat <<EOF
用法: ${SCRIPT_NAME} -n 服务名 -t 镜像标签 -p 端口 [-e 环境]
选项:
  -n  服务名称（必选）
  -t  镜像标签（必选）
  -p  服务端口（必选）
  -e  部署环境（可选，默认 dev）
  -h  显示帮助
示例:
  ${SCRIPT_NAME} -n user-service -t v1.2.3 -p 8080 -e prod
EOF
    exit 1
}

while getopts ":n:t:p:e:h" opt; do
    case $opt in
        n) APP_NAME="$OPTARG" ;;
        t) IMAGE_TAG="$OPTARG" ;;
        p) PORT="$OPTARG" ;;
        e) ENV="$OPTARG" ;;
        h) usage ;;
        \?) log ERROR "无效选项: -$OPTARG"; usage ;;
        :)  log ERROR "选项 -$OPTARG 需要参数"; usage ;;
    esac
done

[ -z "${APP_NAME:-}" ] && { log ERROR "必须指定服务名(-n)"; usage; }
[ -z "${IMAGE_TAG:-}" ] && { log ERROR "必须指定镜像标签(-t)"; usage; }
[ -z "${PORT:-}" ] && { log ERROR "必须指定端口(-p)"; usage; }
[[ ! "$PORT" =~ ^[0-9]+$ ]] && { log ERROR "端口必须为数字"; exit 1; }

readonly APP_NAME IMAGE_TAG PORT ENV       # 参数确认后设为只读

# ========================= 主流程 =========================
acquire_lock
preflight_check

FULL_IMAGE="${REGISTRY}/${APP_NAME}:${IMAGE_TAG}"

log INFO "===== 停止旧容器 ====="
if docker ps -a --format '{{.Names}}' | grep -q "^${APP_NAME}$"; then
    docker stop --time "$GRACEFUL_TIMEOUT" "$APP_NAME" > /dev/null
    docker rm "$APP_NAME" > /dev/null
    log INFO "旧容器已移除"
else
    log INFO "未发现旧容器"
fi

log INFO "===== 拉取镜像 ====="
retry 3 10 docker pull "$FULL_IMAGE"
docker image inspect "$FULL_IMAGE" > /dev/null 2>&1 || {
    log ERROR "镜像不存在: ${FULL_IMAGE}"; exit 1;
}

log INFO "===== 启动容器 ====="
docker run -d \
    --name "$APP_NAME" \
    --restart unless-stopped \
    --memory 1g --memory-swap 1g --cpus 1.0 \
    -p "${PORT}:${PORT}" \
    -v "/opt/app/${APP_NAME}/logs:/app/logs" \
    -e "SPRING_PROFILES_ACTIVE=${ENV}" \
    -e "JAVA_OPTS=-Xms512m -Xmx768m -XX:+UseG1GC" \
    -e "TZ=Asia/Shanghai" \
    --health-cmd="curl -sf http://localhost:${PORT}/actuator/health || exit 1" \
    --health-interval=10s --health-timeout=5s \
    --health-retries=3 --health-start-period=40s \
    "$FULL_IMAGE"

log INFO "===== 健康检查 ====="
elapsed=0
while [ $elapsed -lt $MAX_HEALTH_WAIT ]; do
    health=$(docker inspect --format='{{.State.Health.Status}}' "$APP_NAME" 2>/dev/null || echo "unknown")
    case $health in
        healthy)
            log INFO "服务启动成功，耗时 ${elapsed}s"
            break ;;
        unhealthy)
            log ERROR "服务不健康"
            docker logs --tail 50 "$APP_NAME" >&2
            exit 1 ;;
        *)
            log DEBUG "等待就绪... (${elapsed}/${MAX_HEALTH_WAIT}s)"
            sleep "$HEALTH_INTERVAL"
            elapsed=$((elapsed + HEALTH_INTERVAL)) ;;
    esac
done
[ $elapsed -ge $MAX_HEALTH_WAIT ] && {
    log ERROR "健康检查超时"
    docker logs --tail 50 "$APP_NAME" >&2
    exit 1
}

log INFO "===== 部署完成 ====="
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  服务: ${APP_NAME}  版本: ${IMAGE_TAG}${NC}"
echo -e "${GREEN}  端口: ${PORT}  环境: ${ENV}${NC}"
echo -e "${GREEN}==========================================${NC}"
```

---

# 第四章：Dockerfile + 脚本配合模式

## 4.1 entrypoint.sh 模式

### 什么时候需要 entrypoint.sh

当容器启动时需要执行**比单一命令更复杂的逻辑**，就需要 entrypoint.sh。以下是四种典型场景：

**1. 配置替换**

容器镜像一旦构建完成，内部的配置文件就是固定的。但不同环境（开发/测试/生产）的数据库地址、端口、密钥各不相同。你需要在容器启动时，用环境变量的值去替换配置文件中的占位符：

```bash
# application.yml 中写了占位符：
#   url: jdbc:mysql://${MYSQL_HOST}:3306/${MYSQL_DB}
# 容器启动时用 sed 或 envsubst 把 ${MYSQL_HOST} 替换成真实值
sed -i "s/\${MYSQL_HOST}/${MYSQL_HOST}/g" /app/config/application.yml
```

没有 entrypoint.sh 的话，你只能在 Dockerfile 里硬编码配置值，这就丧失了镜像的通用性。

**2. 等待依赖服务就绪**

Java 服务通常依赖 MySQL、Redis、Kafka 等外部服务。Docker 容器启动顺序不保证依赖服务一定先就绪。entrypoint.sh 可以在启动 Java 进程前，循环探测依赖服务的端口是否可连接：

```bash
# 等待 MySQL 的 3306 端口可以建立 TCP 连接
until nc -z ${MYSQL_HOST} 3306; do
  echo "Waiting for MySQL..."
  sleep 2
done
```

如果没有这个等待步骤，Java 应用可能在启动时因连接不上数据库而抛异常，直接崩溃退出。

**3. 动态参数注入**

JVM 堆内存大小、GC 算法、远程调试端口等参数，往往需要根据容器分配的资源动态调整。entrypoint.sh 从环境变量读取这些参数，拼装成最终的 `java` 命令：

```bash
# 根据环境变量动态设置 JVM 堆内存
# docker run -e JAVA_OPTS="-Xms512m -Xmx512m" myapp
exec java ${JAVA_OPTS} -jar /app/app.jar
```

**4. 初始化操作**

某些服务在首次启动时需要执行一次性操作：创建数据目录、初始化数据库表结构、生成自签名证书、注册服务发现等：

```bash
# 首次启动时创建必要目录
mkdir -p /app/logs /app/data

# 如果数据目录为空，执行初始化 SQL
if [ -z "$(ls -A /app/data)" ]; then
  java -cp /app/init.jar com.example.InitDB
fi
```

### 不需要 entrypoint.sh 的场景

如果你的 Java 服务满足以下**所有**条件，直接 `java -jar` 就够了，不需要 entrypoint.sh：

```dockerfile
# 最简模式：无需 entrypoint.sh
FROM eclipse-temurin:17-jre-alpine
COPY target/app.jar /app/app.jar
EXPOSE 8080
CMD ["java", "-jar", "/app/app.jar"]
```

满足的条件：
- 不需要动态替换配置文件（所有配置通过 Spring 环境变量 `SPRING_DATASOURCE_URL` 等注入）
- 不需要等待依赖服务（应用自身有重试机制，或依赖通过编排工具保证就绪）
- 不需要动态 JVM 参数（使用固定参数即可，或在 Dockerfile 中预设合理的默认值）
- 不需要启动前的初始化操作

**判断原则**：如果 `CMD` 那一行能写完所有启动逻辑，就不需要 entrypoint.sh。一旦你需要 `if/else`、循环、多步操作，就需要 entrypoint.sh。

---

## 4.2 Java 服务 entrypoint.sh 完整示例

下面是一个 70 行的完整 entrypoint.sh，覆盖了 Java 服务最常见的四类需求。**每一行都有详细中文注释**：

```bash
#!/bin/bash
###############################################################################
# entrypoint.sh - Java 服务容器启动脚本
# 功能：动态 JVM 参数 / 配置替换 / 等待依赖 / 启动应用
###############################################################################

set -e                  # 任何命令返回非零状态码，立即退出脚本，避免错误被忽略

# ===================== 第一部分：动态 JVM 参数注入 =====================

# 从环境变量 JAVA_OPTS 读取 JVM 参数，如果未设置则使用默认值
# 默认值说明：
#   -Xms256m        初始堆内存 256MB
#   -Xmx512m        最大堆内存 512MB
#   -XX:+UseG1GC    使用 G1 垃圾收集器（适合大多数服务端应用）
#   -XX:+HeapDumpOnOutOfMemoryError  OOM 时自动生成堆转储文件，方便事后分析
#   -XX:HeapDumpPath=/app/logs/heapdump.hprof  堆转储文件存放路径
# 语法 ${VAR:-default} 表示：如果 VAR 未设置或为空，则使用 default
JAVA_OPTS="${JAVA_OPTS:--Xms256m -Xmx512m -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/app/logs/heapdump.hprof}"

# 从环境变量读取远程调试参数，默认为空（不开启调试）
# 使用方式：docker run -e JAVA_DEBUG="-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005" myapp
JAVA_DEBUG="${JAVA_DEBUG:-}"

# ===================== 第二部分：配置文件变量替换 =====================

# 方式一：使用 sed 逐个替换配置文件中的占位符
# application.yml 中的占位符格式为 {{MYSQL_HOST}}，用 sed 替换为环境变量的值
# -i 表示直接修改文件（in-place）
# 双引号中的 ${MYSQL_HOST} 会被 bash 展开为环境变量的值
# 注意：如果环境变量值包含 / 等特殊字符，需要转义或换用其他分隔符
# 以下语法确保 MYSQL_HOST 有默认值 localhost
sed -i "s/{{MYSQL_HOST}}/${MYSQL_HOST:-localhost}/g" /app/config/application.yml
sed -i "s/{{MYSQL_PORT}}/${MYSQL_PORT:-3306}/g" /app/config/application.yml
sed -i "s/{{REDIS_HOST}}/${REDIS_HOST:-localhost}/g" /app/config/application.yml

# 方式二：使用 envsubst 批量替换（适合占位符数量多的场景）
# envsubst 会将文件中所有 $VAR 或 ${VAR} 格式的占位符替换为对应环境变量的值
# 1. 先将模板文件定义为后缀 .tmpl（不直接被 Spring Boot 加载）
# 2. envsubst 读取模板，替换变量，输出到正式配置文件
# 3. 用花括号限定只替换哪些变量，防止误替换 Spring 自身的 ${} 表达式
#
# 示例模板文件 application.yml.tmpl 内容：
#   server:
#     port: ${SERVER_PORT}
#   spring:
#     datasource:
#       url: jdbc:mysql://${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DB}
#
# envsubst 命令格式：envsubst '$SERVER_PORT $MYSQL_HOST $MYSQL_PORT $MYSQL_DB' < 模板 > 输出
#   只替换列出的变量，Spring 的 ${spring.profiles.active} 等不会被处理
envsubst '$SERVER_PORT $MYSQL_HOST $MYSQL_PORT $MYSQL_DB' \
  < /app/config/application.yml.tmpl \
  > /app/config/application.yml

# ===================== 第三部分：等待依赖服务就绪 =====================

# 定义等待函数：循环探测目标主机的指定端口，直到可以建立 TCP 连接或超时
# 参数：$1=主机名  $2=端口号  $3=服务名称（仅用于日志显示）  $4=超时秒数（默认60）
wait_for_service() {
    local host="$1"         # 目标主机名或 IP
    local port="$2"         # 目标端口号
    local name="$3"         # 服务的可读名称，用于日志
    local timeout="${4:-60}" # 超时时间，默认 60 秒
    local elapsed=0         # 已经等待的秒数

    echo ">>> 等待 ${name} (${host}:${port}) 就绪..."

    # 循环条件：nc (netcat) 尝试连接，-z 表示只探测端口不发送数据，连接成功返回 0
    while ! nc -z "$host" "$port" 2>/dev/null; do
        # 检查是否超时
        if [ "$elapsed" -ge "$timeout" ]; then
            echo "!!! 错误：等待 ${name} 超时（${timeout}秒），容器退出"
            exit 1        # 超时退出，返回非零状态码，Docker 会标记容器为失败
        fi
        echo "    ${name} 未就绪，${elapsed}/${timeout}s，2秒后重试..."
        sleep 2            # 每次重试间隔 2 秒
        elapsed=$((elapsed + 2))  # 累加已等待时间
    done

    echo "<<< ${name} (${host}:${port}) 已就绪，耗时 ${elapsed}s"
}

# 等待 MySQL 就绪：从环境变量读取地址，超时 90 秒
# docker run -e MYSQL_HOST=mysql-server -e MYSQL_PORT=3306 myapp
wait_for_service "${MYSQL_HOST:-localhost}" "${MYSQL_PORT:-3306}" "MySQL" 90

# 等待 Redis 就绪：从环境变量读取地址，超时 60 秒
# docker run -e REDIS_HOST=redis-server -e REDIS_PORT=6379 myapp
wait_for_service "${REDIS_HOST:-localhost}" "${REDIS_PORT:-6379}" "Redis" 60

# ===================== 第四部分：打印启动信息 =====================

echo "========================================"
echo " 容器启动信息"
echo "========================================"
echo "主机名       : $(hostname)"                       # 容器的主机名，即容器 ID 前 12 位
echo "容器 ID      : $(cat /etc/hostname 2>/dev/null)"  # 从 /etc/hostname 读取
echo "Java 版本    : $(java -version 2>&1 | head -1)"   # java -version 输出到 stderr，需 2>&1 重定向
echo "JVM 参数     : ${JAVA_OPTS}"                      # 打印实际生效的 JVM 参数，方便排查问题
echo "调试参数     : ${JAVA_DEBUG:-未启用}"               # 打印调试参数，未设置则显示"未启用"
echo "工作目录     : $(pwd)"                             # 当前工作目录
echo "应用配置     : /app/config/application.yml"
echo "时间(UTC)    : $(date -u '+%Y-%m-%d %H:%M:%S')"   # UTC 时间，避免时区混淆
echo "========================================"

# ===================== 第五部分：启动 Java 应用 =====================

# exec 的作用极其关键：
#   exec 会用 java 进程替换当前 bash 进程，使 java 成为 PID 1
#   PID 1 是容器的 init 进程，负责接收和处理信号（SIGTERM、SIGINT）
#   如果不用 exec，bash 是 PID 1，java 是子进程
#     - docker stop 发送 SIGTERM 给 PID 1 (bash)
#     - bash 不会转发信号给子进程 java
#     - java 收不到 SIGTERM，10秒后被 SIGKILL 强杀，无法优雅关闭
#   用了 exec 之后：
#     - java 直接成为 PID 1
#     - docker stop 的 SIGTERM 直接发给 java
#     - Spring Boot 的 Graceful Shutdown 正常工作
exec java ${JAVA_OPTS} ${JAVA_DEBUG} -jar /app/app.jar
```

### 关键知识点详解

**`set -e` 的含义**：脚本中任何一行命令失败（返回非零退出码），整个脚本立即终止。这避免了"某个 sed 替换失败但脚本继续执行，最终用错误配置启动应用"的情况。

**`nc -z` 的工作原理**：`nc`（netcat）是一个网络工具，`-z` 选项表示只扫描端口不发送数据。如果目标端口可以建立 TCP 连接，返回 0；否则返回非零。这是检测服务是否就绪的轻量级方式。如果镜像中没有 `nc`，可以用 bash 内置的方式替代：

```bash
# 替代 nc -z 的纯 bash 方式（不需要额外安装 netcat）
while ! (echo > /dev/tcp/"$host"/"$port") 2>/dev/null; do
    sleep 2
done
```

**`exec` 为什么必须**：这是 Docker 容器中最常见的陷阱之一。以下对比说明了差异：

```bash
# 错误写法：不用 exec
java ${JAVA_OPTS} -jar /app/app.jar
# 进程树：bash(PID 1) -> java(PID 7)
# docker stop -> SIGTERM 发给 bash -> bash 退出 -> java 成为孤儿进程 -> 10秒后 SIGKILL 强杀

# 正确写法：用 exec
exec java ${JAVA_OPTS} -jar /app/app.jar
# 进程树：java(PID 1)
# docker stop -> SIGTERM 发给 java -> Spring Boot 优雅关闭 -> 应用正常退出
```

---

## 4.3 Dockerfile 中嵌入 entrypoint.sh

### COPY 方式（推荐）

将 entrypoint.sh 作为独立文件放在项目目录中，Dockerfile 构建时复制进镜像：

```dockerfile
# ---- 第一阶段：构建 ----
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -B          # 先下载依赖（利用 Docker 缓存层）
COPY src ./src
RUN mvn package -DskipTests -B            # 打包，跳过测试以加速构建

# ---- 第二阶段：运行 ----
FROM eclipse-temurin:17-jre-alpine

# 安装 netcat（entrypoint.sh 中 nc -z 等待依赖需要用到）
# --no-cache 表示不保留包管理器的缓存索引，减小镜像体积
RUN apk add --no-cache netcat-openbsd bash

WORKDIR /app

# 先复制 entrypoint.sh，再复制 JAR 包
# 这样如果只修改了代码而没改脚本，entrypoint.sh 的缓存层不需要重建
COPY entrypoint.sh /app/entrypoint.sh

# 关键步骤：赋予执行权限
# chmod +x 让 entrypoint.sh 可以被直接执行（./entrypoint.sh）
# 如果不做这一步，Docker 运行时会报 "Permission denied" 错误
# 注意：不能在宿主机 chmod 再 COPY 进来，因为 COPY 会保留宿主机的权限
#       但在 Windows 上开发时，文件可能没有执行权限位，所以必须在镜像内设置
RUN chmod +x /app/entrypoint.sh

# 从构建阶段复制 JAR 包
COPY --from=builder /build/target/*.jar /app/app.jar

# 创建日志和数据目录
RUN mkdir -p /app/logs /app/data /app/config

# 声明端口
EXPOSE 8080

# 设置 ENTRYPOINT 指向 entrypoint.sh
# 使用列表格式（exec 格式），不经过 shell 解释器
ENTRYPOINT ["/app/entrypoint.sh"]
```

项目目录结构：

```
my-project/
├── Dockerfile
├── entrypoint.sh          # 与 Dockerfile 同级
├── pom.xml
└── src/
```

**为什么 COPY + RUN chmod 是推荐方式**：

| 对比项 | COPY + chmod | 直接 COPY | 宿主机 chmod |
|--------|-------------|-----------|-------------|
| 权限可靠性 | 始终可靠 | 可能无执行权限 | Windows 上不可靠 |
| 可维护性 | 脚本独立文件，方便编辑 | - | - |
| Docker 缓存 | 脚本单独一层，改代码不影响脚本缓存 | - | - |
| 代码审查友好 | 脚本变更在 git 中可见 | - | - |

### RUN echo/cat 方式（内联小脚本）

当脚本非常短（5-10行以内），可以直接在 Dockerfile 中用 `RUN echo` 或 `RUN cat` 写入，不需要维护单独的文件：

```dockerfile
# 方式一：RUN echo 逐行写入
# 每一行 echo '...' >> /app/entrypoint.sh 追加一行内容
# 注意：单引号内的内容原样写入，不会做变量替换
RUN echo '#!/bin/bash' > /app/entrypoint.sh && \
    echo 'set -e' >> /app/entrypoint.sh && \
    echo 'exec java ${JAVA_OPTS:--Xmx512m} -jar /app/app.jar' >> /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

# 方式二：RUN cat + heredoc（更清晰，Docker BuildKit 支持）
# <<'EOF' 中的单引号表示不展开变量（原样写入文件）
RUN <<'EOF'
cat > /app/entrypoint.sh << 'SCRIPT'
#!/bin/bash
set -e
exec java ${JAVA_OPTS:--Xmx512m} -jar /app/app.jar
SCRIPT
chmod +x /app/entrypoint.sh
EOF
```

**适用判断**：脚本超过 15 行或有复杂逻辑时，必须用 COPY 方式。内联方式难以维护、难以调试、无法做语法高亮。

### 权限处理详解

Docker 中文件权限有几个容易踩的坑：

```dockerfile
# 坑 1：Windows 上 COPY 的文件可能没有执行权限
# Windows 文件系统（NTFS）没有 Linux 的执行权限位概念
# COPY entrypoint.sh /app/entrypoint.sh 之后的文件权限可能是 644（rw-r--r--）
# 所以必须加 RUN chmod +x

# 坑 2：以 root 复制的文件属于 root，非 root 用户无法写入
# 如果容器以非 root 用户运行，挂载的日志目录可能写入失败
# 解决：在 Dockerfile 中预先修改目录所有权
RUN addgroup -S appgroup && adduser -S appuser -G appgroup  # alpine 创建用户
RUN chown -R appuser:appgroup /app/logs /app/data /app/config
USER appuser                                                 # 切换到非 root 用户
COPY entrypoint.sh /app/entrypoint.sh
# 注意：COPY 在 USER 指令之后执行时，文件所有者仍然是 root
#       必须在 COPY 之后再 chown，或者用 --chown 参数
COPY --chown=appuser:appgroup entrypoint.sh /app/entrypoint.sh

# 坑 3：挂载卷的权限问题
# docker run -v /host/logs:/app/logs 时，/app/logs 的权限取决于宿主机 /host/logs
# 如果宿主机目录属于 root:root，容器内 appuser 无法写入
# 解决：在 entrypoint.sh 中动态修复权限
#   if [ "$(id -u)" = "0" ]; then chown -R appuser:appgroup /app/logs; fi
```

---

## 4.4 CMD vs ENTRYPOINT 深度对比

### 语法区别

Dockerfile 中 `CMD` 和 `ENTRYPOINT` 都支持三种书写格式：

```dockerfile
# 格式一：shell 格式
# Docker 会自动在前面加 /bin/sh -c 执行
# 问题：/bin/sh 成为 PID 1，你的命令是 /bin/sh 的子进程，收不到信号
CMD java -jar /app/app.jar
ENTRYPOINT java -jar /app/app.jar

# 格式二：exec 格式（列表格式，推荐）
# 直接执行指定程序，没有中间 shell 进程
# java 进程就是 PID 1，可以正确接收信号
CMD ["java", "-jar", "/app/app.jar"]
ENTRYPOINT ["java", "-jar", "/app/app.jar"]

# 格式三：与 shell 配合的 exec 格式
# 通过 exec 让命令替换 shell 进程
CMD ["sh", "-c", "exec java ${JAVA_OPTS} -jar /app/app.jar"]
# 用途：需要 shell 展开 ${JAVA_OPTS} 环境变量时使用
```

**推荐使用 exec 格式（列表格式）**，除非你需要 shell 变量展开功能。

### docker run 传参行为差异

```bash
# ---- CMD 场景 ----
# Dockerfile：
#   CMD ["java", "-jar", "/app/app.jar", "--server.port=8080"]
#
# 正常启动：
docker run myapp
# 实际执行：java -jar /app/app.jar --server.port=8080

# docker run 后面加参数，会完全覆盖 CMD
docker run myapp --server.port=9090
# 实际执行：--server.port=9090
# 注意！这里不是追加参数，而是替换整个 CMD
# 结果：docker 尝试执行 "--server.port=9090" 这个命令，会报错 "executable file not found"

# 正确覆盖方式：必须写完整命令
docker run myapp java -jar /app/app.jar --server.port=9090
# 实际执行：java -jar /app/app.jar --server.port=9090

# ---- ENTRYPOINT 场景 ----
# Dockerfile：
#   ENTRYPOINT ["java", "-jar", "/app/app.jar"]
#
# 正常启动：
docker run myapp
# 实际执行：java -jar /app/app.jar

# docker run 后面加参数，会追加到 ENTRYPOINT 后面
docker run myapp --server.port=9090
# 实际执行：java -jar /app/app.jar --server.port=9090
# 参数被追加，这正是 Spring Boot 命令行参数的工作方式

# 覆盖 ENTRYPOINT 需要显式使用 --entrypoint
docker run --entrypoint sh myapp -c "echo hello"
# 实际执行：sh -c "echo hello"
```

### 组合使用的 3 种模式

**模式一：仅 CMD — 灵活，docker run 可覆盖**

```dockerfile
FROM eclipse-temurin:17-jre-alpine
COPY target/app.jar /app/app.jar
CMD ["java", "-jar", "/app/app.jar"]
```

```bash
# 默认启动
docker run myapp
# 执行：java -jar /app/app.jar

# 完全覆盖，启动调试模式
docker run myapp java -jar /app/app.jar --debug
# 执行：java -jar /app/app.jar --debug

# 甚至换成完全不同的命令（调试用）
docker run myapp sh -c "ls /app"
# 执行：sh -c "ls /app"
```

适用场景：开发环境、工具类镜像（需要灵活改变执行命令）。

**模式二：仅 ENTRYPOINT — 强制执行，docker run 传参追加**

```dockerfile
FROM eclipse-temurin:17-jre-alpine
COPY target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

```bash
# 默认启动
docker run myapp
# 执行：java -jar /app/app.jar

# 追加 Spring Boot 参数
docker run myapp --server.port=9090 --spring.profiles.active=prod
# 执行：java -jar /app/app.jar --server.port=9090 --spring.profiles.active=prod

# 不小心写错也没关系，参数只是追加，不会破坏入口点
docker run myapp oops
# 执行：java -jar /app/app.jar oops
# Spring Boot 会报错 "Unknown option: oops"，但不会执行错误命令
```

适用场景：生产环境服务镜像、确保入口点不被意外覆盖。

**模式三：ENTRYPOINT + CMD — 执行器 + 默认参数**

```dockerfile
FROM eclipse-temurin:17-jre-alpine
COPY target/app.jar /app/app.jar
# ENTRYPOINT 定义"执行器"（谁来执行）
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
# CMD 定义"默认参数"（传什么参数）
CMD ["--server.port=8080", "--spring.profiles.active=dev"]
```

```bash
# 默认启动（使用 CMD 的默认参数）
docker run myapp
# 执行：java -jar /app/app.jar --server.port=8080 --spring.profiles.active=dev

# docker run 的参数会替换 CMD，但保留 ENTRYPOINT
docker run myapp --spring.profiles.active=prod
# 执行：java -jar /app/app.jar --spring.profiles.active=prod
# CMD 的默认参数被替换，ENTRYPOINT 的执行器保留

# 完全覆盖 ENTRYPOINT 需要 --entrypoint
docker run --entrypoint sh myapp
# 执行：sh（CMD 的参数也会追加：sh --server.port=8080 --spring.profiles.active=dev）
```

适用场景：需要提供合理默认值但允许覆盖的镜像。

### Java 服务推荐用法

```dockerfile
# 推荐：ENTRYPOINT 指向 entrypoint.sh，CMD 提供默认参数
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--spring.profiles.active=dev"]
```

理由：
1. `ENTRYPOINT` 指向 entrypoint.sh 保证了启动前缀逻辑（等待依赖、配置替换）一定会执行，不会被 `docker run` 的参数意外覆盖
2. `CMD` 提供了合理的默认参数，不同环境可以通过 `docker run` 追加参数覆盖
3. `docker run myapp --spring.profiles.active=prod` 的效果是：先执行 entrypoint.sh 中的所有初始化逻辑，然后 `exec java ... --spring.profiles.active=prod`

### 完整对比表格

| 对比项 | CMD | ENTRYPOINT |
|--------|-----|------------|
| **用途** | 定义默认命令及参数 | 定义容器的主执行程序 |
| **docker run 传参** | **替换**整个 CMD | **追加**到 ENTRYPOINT 后 |
| **覆盖方式** | `docker run image 新命令` | `docker run --entrypoint 新命令 image` |
| **Dockerfile 中可出现次数** | 最后一个生效 | 最后一个生效 |
| **是否必须** | 否（有默认 /bin/sh） | 否（有默认 /bin/sh -c） |
| **与 CMD 组合时** | 作为 ENTRYPOINT 的默认参数 | 作为执行器，CMD 是参数 |
| **PID 1 行为（shell格式）** | /bin/sh 是 PID 1 | /bin/sh 是 PID 1 |
| **PID 1 行为（exec格式）** | 指定命令是 PID 1 | 指定命令是 PID 1 |
| **信号处理** | shell格式下信号不转发 | shell格式下信号不转发 |
| **适用场景** | 灵活可覆盖的命令 | 固定入口点，参数可变 |
| **生产推荐度** | 单独使用不推荐 | 推荐与 CMD 组合使用 |

---

## 4.5 配置文件外部化挂载策略

### Spring Boot 配置挂载

Spring Boot 默认按以下顺序加载配置（后者覆盖前者）：

```
1. /config/application.yml          （jar 包外 /config 目录）
2. /config/application-{profile}.yml
3. /application.yml                 （jar 包外根目录）
4. /application-{profile}.yml
5. classpath:/application.yml       （jar 包内）
6. classpath:/application-{profile}.yml
```

利用这个机制，可以通过 `-v` 挂载外部配置文件覆盖镜像内默认配置：

```bash
# 挂载单个配置文件
# 把宿主机 /opt/myapp/application-prod.yml 挂载到容器的 /app/config/application-prod.yml
# Spring Boot 会自动识别 /app/config/ 下的配置文件（前提是 WORKDIR 为 /app）
docker run -d \
  -v /opt/myapp/application-prod.yml:/app/config/application-prod.yml:ro \
  -e SPRING_PROFILES_ACTIVE=prod \
  myapp:latest

# 挂载整个配置目录
# 将宿主机 /opt/myapp/config 目录挂载到容器的 /app/config
# 目录中的所有配置文件都会被 Spring Boot 加载
docker run -d \
  -v /opt/myapp/config:/app/config:ro \
  -e SPRING_PROFILES_ACTIVE=prod \
  myapp:latest
```

### 日志目录挂载

```bash
# 挂载日志目录
docker run -d \
  -v /var/log/myapp:/app/logs \
  myapp:latest
```

### 数据目录挂载

```bash
# 挂载数据目录
docker run -d \
  -v /data/myapp:/app/data \
  myapp:latest
```

### 只读挂载（:ro）vs 读写挂载

```bash
# :ro = read-only，容器内进程只能读取，不能写入
# 适用于配置文件，防止应用意外修改配置
docker run -d \
  -v /opt/myapp/config:/app/config:ro \
  myapp:latest

# 默认（省略 :ro）= read-write，可读可写
# 适用于日志目录、数据目录
docker run -d \
  -v /var/log/myapp:/app/logs \
  -v /data/myapp:/app/data \
  myapp:latest
```

| 挂载类型 | 适用内容 | 示例 |
|----------|---------|------|
| `:ro` 只读 | 配置文件、证书、公钥 | `-v /opt/config:/app/config:ro` |
| 读写（默认） | 日志、数据、临时文件 | `-v /var/log:/app/logs` |

### 挂载的注意事项

**1. 文件权限问题**

```bash
# 宿主机目录的 uid:gid 决定了容器内的访问权限
# 解决方案一：修改宿主机目录所有权
sudo chown -R 1000:1000 /opt/myapp/config /var/log/myapp /data/myapp

# 解决方案二：在 entrypoint.sh 中以 root 修复权限后切换用户
# if [ "$(id -u)" = "0" ]; then
#   chown -R appuser:appgroup /app/logs /app/data
#   exec su-exec appuser "$0" "$@"
# fi
```

**2. 目录必须存在**

```bash
# 如果宿主机目录不存在，docker run 会自动创建它
# 但是！自动创建的目录属于 root:root，权限为 755
# 最佳实践：手动创建并设置权限
sudo mkdir -p /opt/myapp/config /var/log/myapp /data/myapp
sudo chown -R 1000:1000 /var/log/myapp /data/myapp
```

**3. 挂载覆盖机制**

```bash
# 规则：-v 挂载会覆盖容器内对应路径的所有内容
# 如果挂载的目录为空，镜像内的文件会"消失"
# 解决方案：把镜像内需要的所有配置文件都复制到宿主机挂载目录中
# 或者在 entrypoint.sh 中把默认配置复制到挂载目录（如果为空）
```

```bash
# entrypoint.sh 中处理挂载目录为空的情况
CONFIG_DIR="/app/config"
CONFIG_TEMPLATE_DIR="/app/config-template"  # 镜像内置的默认配置模板

# 如果配置目录为空（首次挂载），从模板复制默认配置
if [ -z "$(ls -A ${CONFIG_DIR} 2>/dev/null)" ]; then
    echo "配置目录为空，复制默认配置..."
    cp -r ${CONFIG_TEMPLATE_DIR}/* ${CONFIG_DIR}/
fi
```

---

## 4.6 多环境配置管理

### Spring Profile + 环境变量组合

Spring Profile 是管理多环境配置的基础机制，容器化环境中通常通过环境变量激活：

```bash
# 方式一：通过 SPRING_PROFILES_ACTIVE 环境变量
docker run -d \
  -e SPRING_PROFILES_ACTIVE=prod \
  myapp:latest

# 方式二：通过命令行参数（配合 ENTRYPOINT 追加）
docker run -d \
  myapp:latest --spring.profiles.active=prod
```

Spring Boot 的环境变量覆盖机制非常强大，任何 `application.yml` 中的属性都可以通过环境变量覆盖：

```bash
# 对应的环境变量命名规则：
# 将 . 和 - 替换为 _，全大写
# spring.datasource.url  -> SPRING_DATASOURCE_URL
# spring.datasource.username -> SPRING_DATASOURCE_USERNAME
# server.port -> SERVER_PORT

# 通过环境变量覆盖所有数据库配置
docker run -d \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SPRING_DATASOURCE_URL="jdbc:mysql://prod-mysql:3306/mydb?useSSL=true" \
  -e SPRING_DATASOURCE_USERNAME=app_user \
  -e SPRING_DATASOURCE_PASSWORD=ProdP@ssw0rd \
  -e SERVER_PORT=8443 \
  myapp:latest
```

### .env 文件管理

当环境变量很多时，直接写在 `docker run` 命令中不现实，使用 `.env` 文件集中管理：

```bash
# .env.dev 文件（开发环境）
SPRING_PROFILES_ACTIVE=dev
SPRING_DATASOURCE_URL=jdbc:mysql://dev-mysql:3306/mydb
SPRING_DATASOURCE_USERNAME=dev_user
SPRING_DATASOURCE_PASSWORD=dev_pass
JAVA_OPTS=-Xms256m -Xmx512m
SERVER_PORT=8080

# .env.prod 文件（生产环境）
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:mysql://prod-mysql:3306/mydb?useSSL=true
SPRING_DATASOURCE_USERNAME=prod_user
SPRING_DATASOURCE_PASSWORD=StrongPr0dP@ss!
JAVA_OPTS=-Xms1g -Xmx2g -XX:+UseG1GC
SERVER_PORT=8443
```

```bash
# docker run 使用 --env-file 加载
docker run -d --env-file .env.dev myapp:latest
docker run -d --env-file .env.prod myapp:latest

# 可以指定多个 --env-file，后面的文件中同名变量会覆盖前面的
docker run -d \
  --env-file .env.base \
  --env-file .env.prod \
  myapp:latest
```

**`.env` 文件的安全注意事项**：

```bash
# .env 文件包含敏感信息，绝对不能提交到 Git！
echo ".env*" >> .gitignore

# 提供模板文件，不含真实值
cat > .env.example << 'EOF'
SPRING_PROFILES_ACTIVE=dev
SPRING_DATASOURCE_URL=jdbc:mysql://localhost:3306/mydb
SPRING_DATASOURCE_USERNAME=REPLACE_ME
SPRING_DATASOURCE_PASSWORD=REPLACE_ME
JAVA_OPTS=-Xms256m -Xmx512m
EOF
```

### 配置中心与容器化配合

**Nacos 配合**：

```bash
# 开发环境启动
docker run -d \
  -e NACOS_SERVER_ADDR=nacos-dev:8848 \
  -e NACOS_NAMESPACE=dev-namespace-id \
  myapp:latest

# 生产环境启动
docker run -d \
  -e NACOS_SERVER_ADDR=nacos-prod:8848 \
  -e NACOS_NAMESPACE=prod-namespace-id \
  -e NACOS_GROUP=PROD_GROUP \
  myapp:latest

# Nacos 命名空间实现环境隔离的原理：
#   dev-namespace-id  -> 只能看到 dev 环境的配置
#   prod-namespace-id -> 只能看到 prod 环境的配置
```

**Apollo 配合**：

```bash
# 开发环境启动
docker run -d \
  -e APOLLO_APP_ID=myapp \
  -e APOLLO_META_SERVER=http://apollo-dev:8080 \
  -e APOLLO_NAMESPACES=application \
  myapp:latest

# 生产环境启动
docker run -d \
  -e APOLLO_APP_ID=myapp \
  -e APOLLO_META_SERVER=http://apollo-prod:8080 \
  -e APOLLO_NAMESPACES=application,rpc-config,db-config \
  -e env=PRO \
  myapp:latest
```

### 敏感信息处理

**核心原则：不在镜像中硬编码任何敏感信息**（密码、密钥、Token 等）。

**方案一：环境变量注入**（最简单，适合开发/测试）

```bash
docker run -d \
  -e SPRING_DATASOURCE_PASSWORD=MyPr0dP@ssw0rd \
  myapp:latest
```

**方案二：--env-file**（避免密码出现在命令行历史中）

```bash
docker run -d --env-file .env.prod myapp:latest
```

**方案三：挂载文件方式**（更安全，不出现在 docker inspect 中）

```bash
# 宿主机上创建密码文件
echo "MyPr0dP@ssw0rd" > /opt/secrets/db_password.txt
chmod 400 /opt/secrets/db_password.txt

# 启动容器时挂载
docker run -d \
  -v /opt/secrets/db_password.txt:/run/secrets/db_password:ro \
  -e SPRING_DATASOURCE_PASSWORD_FILE=/run/secrets/db_password \
  myapp:latest
```

**方案四：Docker Secrets（Swarm 模式）**

```bash
echo "MyPr0dP@ssw0rd" | docker secret create db_password -
docker service create --name myapp --secret db_password myapp:latest
```

**方案选择对比**：

| 方案 | 安全级别 | 复杂度 | 适用场景 |
|------|---------|--------|---------|
| 环境变量注入 | 低 | 最低 | 开发/测试环境 |
| --env-file | 中低 | 低 | 测试环境 |
| 挂载文件 | 中 | 中 | 生产环境，无编排工具 |
| Docker Secrets | 中高 | 中 | Docker Swarm 生产环境 |
| K8s Secret | 高 | 高 | Kubernetes 生产环境 |

---

# 第五章：Docker Compose 编排 Java 服务

## 5.1 Compose 文件语法详解

Docker Compose 使用 YAML 文件定义多容器应用。文件默认名称为 `docker-compose.yml`，核心结构由四大顶层元素组成。

### 5.1.1 四大顶层元素

```yaml
# 顶层元素一：version
# 指定 Compose 文件格式版本
# 常用值："3.8"（最广泛支持）、"2.4"（支持一些 v3 不支持的配置如 depends_on condition）
# 注意：Compose V2 已废弃 version 字段，但为了兼容性仍建议保留
version: "3.8"

# 顶层元素二：services
# 定义各个容器服务，是最核心的部分
services:
  app:
    image: my-app:latest
  db:
    image: mysql:8.0

# 顶层元素三：networks
# 定义自定义网络，service 通过此名称引用
# 不显式定义时，Compose 会自动创建一个默认桥接网络
networks:
  frontend:        # 自定义网络名称
    driver: bridge # 网络驱动，默认 bridge
  backend:
    driver: bridge
    internal: true # 内部网络，不允许外部访问

# 顶层元素四：volumes
# 定义命名数据卷，service 通过此名称引用
# 不显式定义时，service 中声明的卷也会自动创建，但显式声明可配置驱动等选项
volumes:
  db-data:
    driver: local  # 本地驱动，默认值
  redis-data:
    driver: local
```

### 5.1.2 service 常用配置项详解

#### image —— 指定镜像

```yaml
services:
  app:
    # 语法：image: <镜像名>:<标签>
    # 标签省略时默认为 latest
    image: openjdk:11-jre-slim

    # 使用官方镜像仓库中的镜像
    image: mysql:8.0

    # 使用私有仓库镜像
    image: registry.example.com/my-app:v1.2.0

    # 使用摘要（最精确，防止镜像被覆盖）
    image: openjdk:11-jre-slim@sha256:abc123def456...
```

#### build —— 构建配置

```yaml
services:
  app:
    # 简写：指定 Dockerfile 所在目录
    build: .

    # 完整写法
    build:
      context: .                          # 构建上下文路径
      dockerfile: Dockerfile.prod         # 指定 Dockerfile 名称，默认为 Dockerfile
      args:                               # 构建参数，等同于 docker build --build-arg
        JAR_FILE: app.jar
        BUILD_ENV: production
      cache_from:                         # 缓存来源镜像
        - my-app:latest
      target: production                  # 多阶段构建的目标阶段
      labels:                             # 构建时添加的元数据
        com.example.description: "My App"

    # image 和 build 同时使用时：
    # 构建出的镜像会打上 image 指定的标签
    image: my-app:latest
    build: .
```

#### container_name —— 容器名称

```yaml
services:
  app:
    # 语法：container_name: <名称>
    # 不指定时，Compose 自动生成：<项目名>_<服务名>_<序号>
    # 指定后容器名固定，无法水平扩展（docker-compose up --scale 不生效）
    container_name: my-app-server
```

#### ports —— 端口映射

```yaml
services:
  app:
    # 简写：宿主机端口:容器端口（都使用数字）
    ports:
      - "8080:8080"

    # 完整写法
    ports:
      - target: 8080          # 容器端口
        published: 8080       # 宿主机端口
        protocol: tcp         # 协议：tcp 或 udp
        mode: ingress         # 模式：ingress（负载均衡）或 host

    # 映射多个端口
    ports:
      - "8080:8080"           # HTTP
      - "8443:8443"           # HTTPS
      - "5005:5005"           # Java 远程调试
      - "9010:9010"           # JMX

    # 仅绑定宿主机指定 IP
    ports:
      - "127.0.0.1:8080:8080"  # 仅本机可访问
      - "0.0.0.0:8080:8080"    # 所有网卡可访问
```

#### environment —— 环境变量

```yaml
services:
  app:
    # 写法一：键值对（推荐）
    environment:
      SPRING_PROFILES_ACTIVE: prod
      JAVA_OPTS: "-Xms256m -Xmx512m"
      SERVER_PORT: 8080

    # 写法二：等号字符串
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - JAVA_OPTS=-Xms256m -Xmx512m
      - SERVER_PORT=8080

    # 包含特殊字符时，键值对写法更安全
    environment:
      SPRING_DATASOURCE_URL: "jdbc:mysql://mysql:3306/mydb?useSSL=false&serverTimezone=Asia/Shanghai"
```

#### env_file —— 从文件加载环境变量

```yaml
services:
  app:
    # 单个文件
    env_file: .env

    # 多个文件（后面的文件变量覆盖前面的）
    env_file:
      - .env.base
      - .env.prod

    # 指定路径
    env_file:
      - ./config/app.env
      - ./config/database.env

    # env 文件格式示例（.env 文件内容）：
    # 注释以 # 开头
    # KEY=VALUE 格式，不要加引号
    # SPRING_PROFILES_ACTIVE=prod
    # JAVA_OPTS=-Xms256m -Xmx512m
    # DB_HOST=mysql
    # DB_PORT=3306
```

#### volumes —— 数据卷挂载

```yaml
services:
  app:
    volumes:
      # 命名卷：卷名:容器路径
      - app-data:/data/app

      # 绑定挂载：宿主机路径:容器路径
      - ./config:/app/config

      # 只读挂载：加 :ro 后缀
      - ./config:/app/config:ro

      # 匿名卷：仅容器路径
      - /tmp

      # 完整写法
      - type: bind                # volume（命名卷）、bind（绑定挂载）、tmpfs
        source: ./config          # 宿主机路径（bind）或卷名（volume）
        target: /app/config       # 容器内路径
        read_only: true           # 只读
        consistency: cached       # 一致性：consistent(默认)、cached、delegated

      # 常见 Java 服务挂载
      - ./logs:/app/logs          # 日志目录挂载到宿主机
      - ./config/application.yml:/app/config/application.yml:ro  # 配置文件

volumes:
  app-data:  # 在顶层声明命名卷
```

#### networks —— 网络配置

```yaml
services:
  app:
    networks:
      # 加入单个网络
      - frontend

      # 加入多个网络
      - frontend
      - backend

      # 带别名的网络
      networks:
        frontend:
          aliases:
            - app-service       # 在 frontend 网络中的别名
        backend:
          aliases:
            - app-backend       # 在 backend 网络中的别名

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true              # 内部网络，不暴露端口到宿主机
```

#### depends_on —— 服务依赖

```yaml
services:
  app:
    # 简写：只控制启动顺序
    depends_on:
      - mysql
      - redis

    # 完整写法（v2.4 格式或 Compose V2 的 long syntax）：
    # condition 可选值：
    #   service_started  - 服务已启动（默认，等同简写）
    #   service_healthy  - 服务健康检查通过
    #   service_completed_successfully - 服务执行完成且成功退出
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_started

    # 完整写法还支持 restart 和 profiles（Compose V2）
    depends_on:
      mysql:
        condition: service_healthy
        restart: true            # 依赖服务重启时，此服务也重启
```

#### restart —— 重启策略

```yaml
services:
  app:
    # 可选值：
    # "no"       - 不自动重启（默认）
    # always     - 总是重启（包括手动 stop 后 daemon 重启也会自动启动）
    # on-failure - 仅非零退出码时重启
    # unless-stopped - 类似 always，但手动 stop 后不会随 daemon 重启而启动
    restart: unless-stopped

    # on-failure 可指定最大重试次数
    restart: "on-failure:5"

    # 生产环境推荐 unless-stopped 或 always
    restart: always
```

#### healthcheck —— 健康检查

```yaml
services:
  app:
    healthcheck:
      # 检查命令，返回 0 为健康，非 0 为不健康
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]

      # 也可以用 shell 格式
      # test: curl -f http://localhost:8080/actuator/health || exit 1

      interval: 30s     # 每次检查的间隔，默认 30s
      timeout: 10s      # 单次检查超时时间，默认 30s
      retries: 3        # 连续失败次数后标记为 unhealthy，默认 3
      start_period: 40s # 容器启动后的初始化宽限期，此期间检查失败不计入 retries，默认 0s

    # 禁用健康检查（继承自镜像的健康检查会被覆盖）
    healthcheck:
      disable: true

  mysql:
    # MySQL 定方镜像自带的健康检查
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p$$MYSQL_ROOT_PASSWORD"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

#### deploy —— 部署配置（Swarm 模式）

```yaml
services:
  app:
    deploy:
      # 副本数
      replicas: 3

      # 资源限制（docker-compose up 时也生效，需 Compose V2）
      resources:
        limits:
          cpus: "1.0"         # 最多使用 1 个 CPU 核心
          memory: 512M        # 最多使用 512MB 内存
        reservations:
          cpus: "0.5"         # 预留 0.5 个 CPU 核心
          memory: 256M        # 预留 256MB 内存

      # 重启策略
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s

      # 更新策略（滚动更新）
      update_config:
        parallelism: 1         # 每次更新 1 个副本
        delay: 10s             # 更新间隔
        failure_action: rollback  # 失败时回滚
        order: start-first     # 先启动新再停旧

      # 放置约束
      placement:
        constraints:
          - node.role == manager
```

#### logging —— 日志配置

```yaml
services:
  app:
    logging:
      # 日志驱动
      driver: json-file       # 默认驱动，日志以 JSON 格式存储

      # 驱动选项
      options:
        max-size: "10m"       # 单个日志文件最大 10MB
        max-file: "3"         # 最多保留 3 个日志文件
        tag: "my-app"         # 日志标签，用于 syslog/fluentd 驱动

    # syslog 驱动示例
    logging:
      driver: syslog
      options:
        syslog-address: "tcp://192.168.0.42:514"
        syslog-facility: "daemon"
        tag: "my-app"

    # local 驱动示例（更高效的压缩存储）
    logging:
      driver: local
      options:
        max-size: "10m"
        max-file: "5"
```

#### labels —— 标签

```yaml
services:
  app:
    # 键值对写法
    labels:
      com.example.description: "My Java Application"
      com.example.version: "1.0.0"
      com.example.environment: "production"

    # 数组写法
    labels:
      - "com.example.description=My Java Application"
      - "com.example.version=1.0.0"

    # 用途：在监控、运维工具中筛选和组织容器
```

## 5.2 Java 服务 + MySQL + Redis + Nginx 完整编排

以下是一个生产级 Spring Boot 应用完整编排方案，每个配置行都附有详细注释。

### 5.2.1 目录结构

```
project/
├── docker-compose.yml          # 主编排文件
├── .env                        # 环境变量文件
├── app/
│   ├── Dockerfile              # Spring Boot 构建文件
│   └── target/
│       └── my-app.jar          # 构建产物
├── mysql/
│   ├── conf/
│   │   └── my.cnf              # MySQL 自定义配置
│   └── init/
│       └── init.sql            # 初始化 SQL 脚本
├── redis/
│   └── redis.conf              # Redis 配置文件
└── nginx/
    ├── nginx.conf              # Nginx 主配置
    ├── conf.d/
    │   └── default.conf        # 站点配置
    └── html/
        └── index.html          # 静态文件
```

### 5.2.2 完整 docker-compose.yml

```yaml
# ============================================================
# Docker Compose 完整编排：Spring Boot + MySQL + Redis + Nginx
# ============================================================

version: "3.8"

# -------------------- 服务定义 --------------------
services:

  # ==================== Spring Boot 应用 ====================
  app:
    # 使用当前目录的 Dockerfile 构建镜像
    build:
      context: ./app                    # 构建上下文：app 目录
      dockerfile: Dockerfile            # Dockerfile 名称
      args:
        JAR_FILE: target/my-app.jar     # 构建参数：JAR 文件路径
    # 构建后打上此标签，方便后续引用
    image: my-app:latest
    # 容器名称，便于日志查看和管理
    container_name: my-app
    # 端口映射：宿主机端口:容器端口
    ports:
      - "8080:8080"                     # 应用 HTTP 端口
    # 环境变量：Spring Boot 配置通过环境变量注入
    environment:
      # 激活的 Spring Profile
      SPRING_PROFILES_ACTIVE: prod
      # JVM 启动参数
      JAVA_OPTS: >-
        -Xms512m
        -Xmx512m
        -XX:+UseG1GC
        -XX:+HeapDumpOnOutOfMemoryError
        -XX:HeapDumpPath=/app/logs/heapdump.hprof
      # 数据库连接配置：主机名使用 Compose 服务名 mysql
      SPRING_DATASOURCE_URL: "jdbc:mysql://mysql:3306/mydb?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai&characterEncoding=utf8mb4"
      SPRING_DATASOURCE_USERNAME: root
      SPRING_DATASOURCE_PASSWORD: ${MYSQL_ROOT_PASSWORD}  # 从 .env 文件读取
      # Redis 连接配置：主机名使用 Compose 服务名 redis
      SPRING_REDIS_HOST: redis
      SPRING_REDIS_PORT: 6379
      SPRING_REDIS_PASSWORD: ${REDIS_PASSWORD}              # 从 .env 文件读取
      # 时区设置
      TZ: Asia/Shanghai
    # 从 .env 文件加载额外环境变量
    env_file:
      - .env
    # 数据卷挂载
    volumes:
      - ./app/logs:/app/logs             # 日志目录挂载到宿主机，便于查看和持久化
    # 加入的网络
    networks:
      - app-network                      # 加入自定义网络
    # 依赖的服务：确保 mysql 和 redis 先启动且健康
    depends_on:
      mysql:
        condition: service_healthy       # 等待 mysql 健康检查通过
      redis:
        condition: service_healthy       # 等待 redis 健康检查通过
    # 重启策略
    restart: unless-stopped              # 异常退出时自动重启
    # 健康检查：通过 Spring Boot Actuator 端点
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
      interval: 30s                      # 每 30 秒检查一次
      timeout: 10s                       # 超时时间 10 秒
      retries: 3                         # 连续 3 次失败标记为不健康
      start_period: 60s                  # 启动宽限期 60 秒（Java 应用启动较慢）
    # 日志配置
    logging:
      driver: json-file
      options:
        max-size: "10m"                  # 单个日志文件最大 10MB
        max-file: "5"                    # 最多保留 5 个日志文件
    # 资源限制
    deploy:
      resources:
        limits:
          memory: 1G                     # 内存上限 1GB（需大于 JVM 堆内存 + 非堆内存）
          cpus: "1.0"                    # CPU 上限 1 核

  # ==================== MySQL 数据库 ====================
  mysql:
    # 使用 MySQL 8.0 官方镜像
    image: mysql:8.0
    # 容器名称
    container_name: my-mysql
    # 端口映射：仅本机可访问，不对外暴露
    ports:
      - "127.0.0.1:3306:3306"            # 仅本机可连接
    # 环境变量
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}  # root 密码，从 .env 读取
      MYSQL_DATABASE: mydb                          # 自动创建的数据库
      MYSQL_USER: appuser                           # 应用用户
      MYSQL_PASSWORD: ${MYSQL_APP_PASSWORD}         # 应用用户密码
      TZ: Asia/Shanghai                             # 时区
    # 数据卷挂载
    volumes:
      # 数据持久化：命名卷存储 MySQL 数据文件
      - mysql-data:/var/lib/mysql
      # 挂载初始化 SQL 脚本（仅首次启动时执行）
      - ./mysql/init:/docker-entrypoint-initdb.d
      # 挂载自定义 MySQL 配置
      - ./mysql/conf/my.cnf:/etc/mysql/conf.d/my.cnf:ro
    # 网络
    networks:
      - app-network
    # 重启策略
    restart: unless-stopped
    # 健康检查：使用 mysqladmin ping 检测
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p$$MYSQL_ROOT_PASSWORD"]
      interval: 10s                      # 每 10 秒检查一次
      timeout: 5s                        # 超时 5 秒
      retries: 5                         # 连续 5 次失败标记为不健康
      start_period: 30s                  # MySQL 启动较慢，宽限期 30 秒
    # 日志配置
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"
    # 命令：覆盖默认启动命令，添加自定义参数
    command: >
      --default-authentication-plugin=mysql_native_password
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --max-connections=200
      --innodb-buffer-pool-size=256M

  # ==================== Redis 缓存 ====================
  redis:
    # 使用 Redis 7 Alpine 版本（轻量）
    image: redis:7-alpine
    # 容器名称
    container_name: my-redis
    # 端口映射：仅本机可访问
    ports:
      - "127.0.0.1:6379:6379"
    # 数据卷挂载
    volumes:
      # 数据持久化：命名卷存储 Redis 数据
      - redis-data:/data
      # 挂载 Redis 配置文件
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
    # 网络
    networks:
      - app-network
    # 重启策略
    restart: unless-stopped
    # 健康检查：使用 redis-cli ping
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "$$REDIS_PASSWORD", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    # 日志配置
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "2"
    # 启动命令：指定配置文件启动
    command: redis-server /usr/local/etc/redis/redis.conf

  # ==================== Nginx 反向代理 ====================
  nginx:
    # 使用 Nginx Alpine 版本
    image: nginx:1.25-alpine
    # 容器名称
    container_name: my-nginx
    # 端口映射：对外暴露 HTTP 和 HTTPS
    ports:
      - "80:80"                           # HTTP
      - "443:443"                         # HTTPS（如需 SSL）
    # 数据卷挂载
    volumes:
      # 挂载 Nginx 主配置文件
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      # 挂载站点配置
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      # 挂载静态文件目录
      - ./nginx/html:/usr/share/nginx/html:ro
      # 挂载 SSL 证书目录（如需 HTTPS）
      - ./nginx/ssl:/etc/nginx/ssl:ro
      # 挂载日志目录
      - ./nginx/logs:/var/log/nginx
    # 网络
    networks:
      - app-network
    # 依赖 app 服务
    depends_on:
      app:
        condition: service_healthy
    # 重启策略
    restart: unless-stopped
    # 健康检查
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    # 日志配置
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

# -------------------- 网络定义 --------------------
networks:
  app-network:
    driver: bridge                        # 桥接网络
    name: my-app-network                  # 自定义网络名称（默认为 项目名_网络名）
    ipam:                                 # IP 地址管理（可选）
      config:
        - subnet: 172.28.0.0/16           # 子网范围

# -------------------- 数据卷定义 --------------------
volumes:
  mysql-data:
    name: my-mysql-data                   # 自定义卷名
  redis-data:
    name: my-redis-data                   # 自定义卷名
```

### 5.2.3 配套文件

**.env 文件**（与 docker-compose.yml 同目录）：

```bash
# .env - 环境变量文件
# 此文件不应提交到版本控制（加入 .gitignore）

# MySQL 配置
MYSQL_ROOT_PASSWORD=Str0ng!Root#Pass2024
MYSQL_APP_PASSWORD=AppUser!Pass2024

# Redis 配置
REDIS_PASSWORD=Redis!Pass2024

# 应用配置
SPRING_PROFILES_ACTIVE=prod
```

**MySQL 初始化 SQL**（`./mysql/init/init.sql`）：

```sql
-- 此脚本仅在 MySQL 首次启动时执行（数据目录为空时）
-- 如果需要每次启动都执行，需使用其他方式

-- 创建数据库（如果 MYSQL_DATABASE 环境变量已设置则不需要）
CREATE DATABASE IF NOT EXISTS mydb DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 授权应用用户（如果 MYSQL_USER 已设置则不需要）
-- GRANT ALL PRIVILEGES ON mydb.* TO 'appuser'@'%';
-- FLUSH PRIVILEGES;

-- 创建业务表
USE mydb;

CREATE TABLE IF NOT EXISTS t_user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
    username VARCHAR(50) NOT NULL COMMENT '用户名',
    email VARCHAR(100) NOT NULL COMMENT '邮箱',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
```

**Redis 配置文件**（`./redis/redis.conf`）：

```conf
# Redis 配置文件

# 绑定地址（容器内允许所有连接，网络安全由 Docker 网络控制）
bind 0.0.0.0

# 密码认证
requirepass Redis!Pass2024

# 持久化方式：RDB + AOF 混合
save 900 1
save 300 10
save 60 10000

# 开启 AOF
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec

# AOF 重写时使用 RDB 前缀（混合持久化，Redis 4.0+）
aof-use-rdb-preamble yes

# 最大内存限制（根据实际情况调整）
maxmemory 256mb
maxmemory-policy allkeys-lru

# 日志级别
loglevel notice
```

**Nginx 站点配置**（`./nginx/conf.d/default.conf`）：

```nginx
upstream app_backend {
    # 使用 Compose 服务名 "app" 作为主机名
    # Docker 内部 DNS 会自动解析为 app 容器的 IP
    server app:8080;
    # 如果有多个 app 实例，可以添加多个 server
    # server app:8081;
}

server {
    listen 80;
    server_name localhost;

    # 静态文件
    location /static/ {
        alias /usr/share/nginx/html/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # API 请求反向代理到 Spring Boot
    location /api/ {
        proxy_pass http://app_backend/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（如果需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 60s;

        # 缓冲设置
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    # 健康检查端点
    location /health {
        proxy_pass http://app_backend/actuator/health;
        access_log off;
    }

    # 默认转发到应用
    location / {
        proxy_pass http://app_backend/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Spring Boot Dockerfile**（`./app/Dockerfile`）：

```dockerfile
# 第一阶段：构建
FROM maven:3.9-eclipse-temurin-11 AS builder
WORKDIR /build
ARG JAR_FILE=target/my-app.jar
# 先复制 pom.xml，利用缓存下载依赖
COPY pom.xml .
RUN mvn dependency:go-offline -B
# 再复制源码并构建
COPY src ./src
RUN mvn package -DskipTests -B

# 第二阶段：运行
FROM eclipse-temurin:11-jre-alpine
WORKDIR /app
# 从构建阶段复制 JAR
COPY --from=builder /build/target/*.jar app.jar
# 创建非 root 用户
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
RUN chown -R appuser:appgroup /app
USER appuser
# 暴露端口
EXPOSE 8080
# 入口点
ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS} -jar app.jar"]
```

## 5.3 服务依赖与启动顺序

### 5.3.1 depends_on 的局限

```yaml
# depends_on 只保证启动顺序，不保证服务就绪
# 例如：MySQL 进程启动了，但还没完成初始化，app 连接会失败
services:
  app:
    depends_on:
      - mysql    # Compose 会先启动 mysql，再启动 app
                  # 但 mysql 可能还在执行初始化脚本，尚未就绪
```

**问题示例**：

```
# 启动顺序：
# 1. Compose 启动 mysql 容器 → 进程已运行（但还在初始化）
# 2. Compose 启动 app 容器 → app 尝试连接 mysql
# 3. mysql 正在执行 docker-entrypoint-initdb.d 中的 SQL
# 4. app 连接被拒绝 → 启动失败！
```

### 5.3.2 healthcheck + depends_on condition: service_healthy

这是 Compose 原生推荐的方式，确保依赖服务真正就绪：

```yaml
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: mydb
    # 定义健康检查
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p$$MYSQL_ROOT_PASSWORD"]
      interval: 5s          # 每 5 秒检查一次
      timeout: 3s           # 超时 3 秒
      retries: 10           # 最多重试 10 次（即最多等待 50 秒）
      start_period: 30s     # 启动后 30 秒内不检查（给 MySQL 初始化时间）

  app:
    image: my-app:latest
    # 使用 condition 等待健康检查通过
    depends_on:
      mysql:
        condition: service_healthy   # 直到 mysql 健康检查通过后才启动 app
```

**注意事项**：

- `condition: service_healthy` 在 Compose 文件 version 3 中不支持（仅 v2.4 支持），但 Docker Compose V2 CLI 已恢复支持
- 如果使用旧版本，需要用下面的替代方案

### 5.3.3 wait-for-it.sh 脚本方式

`wait-for-it.sh` 是一个经典的等待脚本，它会轮询指定端口直到可连接：

```bash
# 下载 wait-for-it.sh
curl -O https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh
chmod +x wait-for-it.sh
```

**在 Dockerfile 中集成**：

```dockerfile
FROM eclipse-temurin:11-jre-alpine

# 安装 bash（wait-for-it.sh 需要）
RUN apk add --no-cache bash

# 复制 wait-for-it.sh
COPY wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh

WORKDIR /app
COPY target/my-app.jar app.jar

# 先等待 mysql:3306 可连接，再启动 Java 应用
# -t 60 表示最多等待 60 秒
ENTRYPOINT ["/usr/local/bin/wait-for-it.sh", "mysql:3306", "-t", "60", "--", \
            "java", "-jar", "app.jar"]
```

**在 docker-compose.yml 中使用**：

```yaml
services:
  app:
    image: my-app:latest
    # 覆盖入口点，先等待多个服务
    entrypoint: >
      /usr/local/bin/wait-for-it.sh mysql:3306 -t 60 --
      /usr/local/bin/wait-for-it.sh redis:6379 -t 60 --
      java -jar app.jar
```

**wait-for-it.sh 的局限**：只能检查端口是否可连接，不能验证服务是否真正就绪（例如 MySQL 端口可连接但还在初始化）。

### 5.3.4 自定义等待脚本

更精确的等待脚本可以验证服务逻辑是否就绪：

```bash
#!/bin/bash
# wait-for-services.sh - 自定义服务等待脚本

set -e

# 等待 MySQL 就绪的函数
wait_for_mysql() {
    local host="${1:-mysql}"
    local port="${2:-3306}"
    local user="${3:-root}"
    local password="${4:-$MYSQL_ROOT_PASSWORD}"
    local max_attempts="${5:-30}"
    local attempt=0

    echo "等待 MySQL (${host}:${port}) 就绪..."

    while [ $attempt -lt $max_attempts ]; do
        # 尝试执行一条简单 SQL 查询来验证 MySQL 是否真正就绪
        if mysqladmin ping -h "$host" -P "$port" -u "$user" -p"$password" --silent 2>/dev/null; then
            echo "MySQL 已就绪！"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "MySQL 未就绪，第 ${attempt}/${max_attempts} 次重试，等待 2 秒..."
        sleep 2
    done

    echo "错误：等待 MySQL 超时（${max_attempts} 次重试后仍未就绪）"
    return 1
}

# 等待 Redis 就绪的函数
wait_for_redis() {
    local host="${1:-redis}"
    local port="${2:-6379}"
    local password="${3:-$REDIS_PASSWORD}"
    local max_attempts="${4:-30}"
    local attempt=0

    echo "等待 Redis (${host}:${port}) 就绪..."

    while [ $attempt -lt $max_attempts ]; do
        # 尝试执行 PING 命令验证 Redis 是否就绪
        if redis-cli -h "$host" -p "$port" -a "$password" ping 2>/dev/null | grep -q PONG; then
            echo "Redis 已就绪！"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "Redis 未就绪，第 ${attempt}/${max_attempts} 次重试，等待 2 秒..."
        sleep 2
    done

    echo "错误：等待 Redis 超时"
    return 1
}

# 通用 TCP 端口等待函数
wait_for_port() {
    local host="$1"
    local port="$2"
    local max_attempts="${3:-30}"
    local attempt=0

    echo "等待 ${host}:${port} 可连接..."

    while [ $attempt -lt $max_attempts ]; do
        # 使用 bash 内置的 /dev/tcp 检测端口
        if (echo > /dev/tcp/"$host"/"$port") 2>/dev/null; then
            echo "${host}:${port} 可连接！"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "${host}:${port} 不可连接，第 ${attempt}/${max_attempts} 次重试..."
        sleep 2
    done

    echo "错误：等待 ${host}:${port} 超时"
    return 1
}

# 执行等待
wait_for_mysql mysql 3306 root "$MYSQL_ROOT_PASSWORD" 30
wait_for_redis redis 6379 "$REDIS_PASSWORD" 30

echo "所有依赖服务已就绪，启动应用..."
exec java $JAVA_OPTS -jar app.jar
```

**在 docker-compose.yml 中使用**：

```yaml
services:
  app:
    image: my-app:latest
    volumes:
      - ./scripts/wait-for-services.sh:/usr/local/bin/wait-for-services.sh:ro
    entrypoint: ["/usr/local/bin/wait-for-services.sh"]
    # 如果 Dockerfile 中已定义 ENTRYPOINT，这里会覆盖
```

### 5.3.5 Spring Boot 自身的重试机制

Spring Boot 应用本身可以配置连接重试，即使依赖服务启动慢也能最终连上：

```yaml
# application.yml - Spring Boot 数据源重试配置
spring:
  datasource:
    url: jdbc:mysql://mysql:3306/mydb?useSSL=false&serverTimezone=Asia/Shanghai
    username: root
    password: ${MYSQL_ROOT_PASSWORD}
    # Tomcat 连接池重试配置（Spring Boot 默认使用 Tomcat 连接池）
    tomcat:
      initial-size: 0               # 初始连接数为 0（启动时不立即创建连接）
      min-idle: 5                    # 最小空闲连接数
      max-active: 20                 # 最大活跃连接数
      max-wait: 10000                # 获取连接最大等待时间（毫秒）
      # 关键：连接验证查询
      validation-query: SELECT 1
      test-on-borrow: true           # 借出连接时验证
      test-while-idle: true          # 空闲时验证
      time-between-eviction-runs-millis: 30000  # 每 30 秒检查空闲连接
    # HikariCP 连接池重试配置（如果使用 HikariCP）
    hikari:
      connection-timeout: 30000      # 连接超时 30 秒
      maximum-pool-size: 20
      minimum-idle: 5
      connection-test-query: SELECT 1
```

**Spring Boot 2.5+ 自动重试**（需添加 spring-retry 依赖）：

```xml
<!-- pom.xml -->
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-aspects</artifactId>
</dependency>
```

```java
// 启用重试
@EnableRetry
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

```java
// 在数据源配置上添加重试
@Service
public class DatabaseInitService {

    // 最多重试 5 次，每次间隔 3 秒
    @Retryable(value = {SQLException.class, DataAccessException.class},
               maxAttempts = 5,
               backoff = @Backoff(delay = 3000, multiplier = 2))
    public void executeInitQuery() {
        jdbcTemplate.execute("SELECT 1");
    }
}
```

**推荐组合方案**：

```
healthcheck + depends_on (condition: service_healthy)  →  Docker 层面保证就绪
+ Spring Boot 连接池重试配置                             →  应用层面容错
+ 自定义等待脚本（可选）                                 →  额外保障
```

## 5.4 环境变量管理

### 5.4.1 .env 文件语法和优先级

`.env` 文件位于 `docker-compose.yml` 同目录下，用于存放 Compose 变量替换的默认值。

```bash
# .env 文件语法

# 注释以 # 开头
# 键值对格式：KEY=VALUE，不要加引号（除非值本身包含引号）
MYSQL_ROOT_PASSWORD=MyStr0ng!Pass
MYSQL_DATABASE=mydb
APP_VERSION=1.0.0

# 值中包含空格时不需要加引号，但建议加引号以明确
JAVA_OPTS=-Xms512m -Xmx512m

# 值中包含 # 时必须加引号
SPECIAL_VALUE="value#with#hash"

# 支持多行值（较少使用）
MULTILINE="line1
line2
line3"

# 变量引用（不支持的！.env 不会做变量展开）
# 以下写法是错误的，BASE_URL 不会被替换：
# BASE_URL=http://localhost
# FULL_URL=${BASE_URL}/api   ← 这不会生效！
```

**在 docker-compose.yml 中引用 .env 变量**：

```yaml
services:
  app:
    image: my-app:${APP_VERSION}               # 引用 .env 中的 APP_VERSION
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}  # 引用 .env 中的变量
      # 带默认值的变量引用
      SERVER_PORT: ${SERVER_PORT:-8080}            # 如果 SERVER_PORT 未设置，使用 8080
      # 必需变量（未设置时报错）
      DB_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD is required}
```

**优先级**（从高到低）：

```
1. docker compose run -e VAR=value           # 命令行 -e 参数，最高优先级
2. Shell 环境变量（export VAR=value）         # Shell 中已设置的变量
3. .env 文件                                  # Compose 目录下的 .env 文件
4. docker-compose.yml 中的 environment        # environment 中的硬编码值（最低）
```

**验证方式**：

```bash
# 查看变量替换后的 Compose 配置
docker compose config

# 查看某个服务的环境变量
docker compose exec app env
```

### 5.4.2 environment / env_file 区别

```yaml
services:
  app:
    # ---- environment ----
    # 直接在 Compose 文件中定义环境变量
    # 优点：一目了然，变量值与配置在同一文件
    # 缺点：敏感信息会暴露在 Compose 文件中
    environment:
      SERVER_PORT: 8080
      SPRING_PROFILES_ACTIVE: prod
      # 以下敏感信息不应硬编码在 Compose 文件中！
      # DB_PASSWORD: mysecretpassword   ← 错误做法

    # ---- env_file ----
    # 从外部文件加载环境变量
    # 优点：敏感信息与配置分离，.env 文件可加入 .gitignore
    # 缺点：需要额外维护文件
    env_file:
      - .env                    # 从 .env 加载变量
      - .env.prod               # 可以加载多个文件

    # ---- 推荐组合方式 ----
    # 非敏感配置用 environment
    # 敏感配置用 env_file 或 ${VAR} 引用 .env
    environment:
      SERVER_PORT: 8080
      SPRING_PROFILES_ACTIVE: prod
      DB_PASSWORD: ${DB_PASSWORD}   # 从 .env 引用敏感变量
    env_file:
      - .env.secrets               # 额外的密钥文件
```

**env_file 文件格式**：

```bash
# .env 文件和 env_file 引用的文件格式相同
# 每行一个 KEY=VALUE

# .env.secrets 文件示例
DB_PASSWORD=MySecretPassword123
REDIS_PASSWORD=RedisSecret456
JWT_SECRET_KEY=eyJhbGciOiJIUzI1NiJ9...
```

### 5.4.3 环境变量优先级完整说明

```
优先级从高到低：

┌──────────────────────────────────────────────────────────────────┐
│ 1. docker compose run -e VAR=value                               │
│    命令行直接指定，最高优先级                                       │
│    示例：docker compose run -e SPRING_PROFILES_ACTIVE=dev app     │
│                                                                  │
│ 2. Shell 环境变量                                                 │
│    在执行 docker compose 命令前已 export 的变量                    │
│    示例：export MYSQL_ROOT_PASSWORD=newpass && docker compose up  │
│                                                                  │
│ 3. .env 文件（Compose 目录下）                                    │
│    用于 docker-compose.yml 中 ${VAR} 的变量替换                   │
│    注意：.env 文件的变量不会自动传入容器！                          │
│    需要通过 environment 或 env_file 显式引用                      │
│                                                                  │
│ 4. env_file 指定的文件                                            │
│    文件中的变量会直接注入容器环境                                   │
│                                                                  │
│ 5. environment 中的硬编码值                                       │
│    Compose 文件中直接写的值                                        │
│                                                                  │
│ 6. Dockerfile 中的 ENV 指令                                      │
│    镜像构建时设置的默认值，最低优先级                               │
└──────────────────────────────────────────────────────────────────┘
```

**重要注意**：`.env` 文件和 `env_file` 是两个不同的概念！

```yaml
services:
  app:
    image: my-app:${APP_VERSION}  # .env 中的变量用于 Compose 变量替换
    env_file:
      - .env.app                   # env_file 中的变量注入到容器内环境
    environment:
      APP_VERSION: ${APP_VERSION}  # .env 中的 APP_VERSION 替换后注入容器
```

### 5.4.4 Spring Boot 环境变量注入

Spring Boot 支持"宽松绑定"（Relaxed Binding），环境变量名可以自动映射到配置属性：

**下划线转点号规则**：

```
环境变量名                        →  Spring Boot 属性名
─────────────────────────────────────────────────────────────
SPRING_DATASOURCE_URL             →  spring.datasource.url
SPRING_DATASOURCE_USERNAME        →  spring.datasource.username
SPRING_REDIS_HOST                 →  spring.redis.host
SERVER_PORT                       →  server.port
SPRING_PROFILES_ACTIVE            →  spring.profiles.active
JAVA_OPTS                         →  无自动映射（自定义变量）
```

**转换规则**：
1. 全部大写 → 全部小写
2. 下划线 `_` → 点号 `.`
3. 如果需要连字符 `-`，使用下划线包裹：`MY_PROPERTY` → `my.property`，`MY__PROPERTY` → `my-property`（双下划线）

**也可使用 SPRING_APPLICATION_JSON 一次性注入多个属性**：

```yaml
services:
  app:
    environment:
      # 方式一：逐个设置（推荐，清晰明了）
      SPRING_DATASOURCE_URL: "jdbc:mysql://mysql:3306/mydb"
      SPRING_DATASOURCE_USERNAME: root
      SPRING_DATASOURCE_PASSWORD: ${DB_PASSWORD}
      SPRING_REDIS_HOST: redis
      SPRING_REDIS_PORT: 6379

      # 方式二：使用 SPRING_APPLICATION_JSON（适合大量配置）
      SPRING_APPLICATION_JSON: '{
        "spring": {
          "datasource": {
            "url": "jdbc:mysql://mysql:3306/mydb",
            "username": "root",
            "password": "secret"
          },
          "redis": {
            "host": "redis",
            "port": 6379
          }
        }
      }'
```

**不同配置源优先级**（从高到低）：

```
1. 命令行参数                  java -jar app.jar --server.port=9090
2. SPRING_APPLICATION_JSON     环境变量中的 JSON
3. 环境变量                    SPRING_DATASOURCE_URL=...
4. 外部配置文件                /config/application.yml
5. 内部配置文件                classpath:application.yml
6. @PropertySource            代码中指定的配置源
7. 默认值                      代码中的 @Value("default")
```

## 5.5 常用 Compose 命令

### 5.5.1 核心命令

```bash
# ==== up - 创建并启动所有服务 ====
# 最常用的命令
docker compose up                    # 前台启动，日志输出到终端，Ctrl+C 停止
docker compose up -d                 # 后台启动（detached 模式）
docker compose up --build            # 启动前重新构建镜像
docker compose up --force-recreate   # 强制重建容器（即使配置没变）
docker compose up --no-deps app      # 只启动 app，不启动其依赖
docker compose up -d mysql redis     # 只启动指定服务（及其依赖）
docker compose up --scale app=3      # 启动 3 个 app 实例（注意端口冲突）

# ==== down - 停止并删除容器、网络 ====
docker compose down                  # 停止并删除容器和网络
docker compose down -v               # 同时删除数据卷（危险！数据会丢失）
docker compose down --rmi all        # 同时删除镜像
docker compose down --remove-orphans # 删除 Compose 文件中已不存在的服务的容器

# ==== ps - 查看服务状态 ====
docker compose ps                    # 查看所有服务状态
docker compose ps app                # 查看指定服务状态

# ==== logs - 查看日志 ====
docker compose logs                  # 查看所有服务日志
docker compose logs app              # 查看指定服务日志
docker compose logs -f               # 实时跟踪日志（follow）
docker compose logs -f app           # 实时跟踪指定服务日志
docker compose logs --tail 100 app   # 查看最后 100 行日志
docker compose logs --since 30m app  # 查看最近 30 分钟的日志
docker compose logs -t app           # 显示时间戳

# ==== exec - 在运行中的容器内执行命令 ====
docker compose exec app bash         # 在 app 容器中打开交互式 shell
docker compose exec app sh           # Alpine 镜像没有 bash，使用 sh
docker compose exec mysql mysql -u root -p  # 在 mysql 容器中执行 mysql 命令
docker compose exec app jstack 1     # 在 app 容器中执行 jstack

# ==== restart - 重启服务 ====
docker compose restart               # 重启所有服务
docker compose restart app           # 重启指定服务
docker compose restart -t 30 app     # 重启前等待 30 秒（默认 10 秒）

# ==== pull - 拉取镜像 ====
docker compose pull                  # 拉取所有服务的镜像
docker compose pull app              # 拉取指定服务镜像
docker compose pull --ignore-pull-failures  # 忽略拉取失败继续

# ==== build - 构建镜像 ====
docker compose build                 # 构建所有服务的镜像
docker compose build app             # 构建指定服务镜像
docker compose build --no-cache      # 不使用缓存构建
docker compose build --parallel      # 并行构建

# ==== 其他常用命令 ====
docker compose config                # 验证并查看 Compose 文件（变量替换后的结果）
docker compose config --services     # 列出所有服务名
docker compose top                   # 查看容器内进程
docker compose images                # 查看服务使用的镜像
docker compose pause app             # 暂停服务（不停止，冻结进程）
docker compose unpause app           # 恢复暂停的服务
docker compose rm                    # 删除已停止的容器
docker compose cp app:/app/logs ./   # 从容器复制文件到宿主机
```

### 5.5.2 多环境 Compose 文件覆盖

Docker Compose 支持通过多文件覆盖实现不同环境配置：

**文件结构**：

```
project/
├── docker-compose.yml              # 基础配置（所有环境共用）
├── docker-compose.override.yml     # 开发环境覆盖（自动加载，无需 -f 指定）
├── docker-compose.prod.yml         # 生产环境覆盖
└── docker-compose.test.yml         # 测试环境覆盖
```

**基础配置**（`docker-compose.yml`）：

```yaml
services:
  app:
    build: .
    environment:
      SPRING_PROFILES_ACTIVE: default
      SERVER_PORT: 8080
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

**开发环境覆盖**（`docker-compose.override.yml`，自动加载）：

```yaml
services:
  app:
    # 开发环境：挂载源码、开启调试端口
    environment:
      SPRING_PROFILES_ACTIVE: dev
      JAVA_OPTS: "-Xms256m -Xmx256m -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005"
    ports:
      - "8080:8080"
      - "5005:5005"          # 调试端口
    volumes:
      - ./app/src:/app/src   # 挂载源码（热重载）
```

**生产环境覆盖**（`docker-compose.prod.yml`，需 -f 指定）：

```yaml
services:
  app:
    # 生产环境：使用构建好的镜像，不做源码挂载
    image: registry.example.com/my-app:${APP_VERSION:-latest}
    environment:
      SPRING_PROFILES_ACTIVE: prod
      JAVA_OPTS: "-Xms1g -Xmx1g -XX:+UseG1GC"
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "2.0"
    restart: always
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "10"
```

**使用方式**：

```bash
# 开发环境（自动加载 override 文件）
docker compose up -d
# 等同于：docker compose -f docker-compose.yml -f docker-compose.override.yml up -d

# 生产环境（指定 prod 文件，不加载 override）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 测试环境
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d

# 验证合并后的配置
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

**覆盖规则**：

```
1. environment：合并，相同 key 以后面的文件为准
2. ports / volumes：追加（不会覆盖，两个文件的映射都会生效）
3. image / build：后面的文件覆盖前面的
4. depends_on：合并
5. networks：合并
```

## 5.6 Java 微服务编排示例

### 5.6.1 多个 Spring Boot 服务编排

```yaml
# ============================================================
# Java 微服务编排：Gateway + User-Service + Order-Service
# ============================================================

version: "3.8"

services:
  # ==================== API 网关 ====================
  gateway:
    image: my-gateway:latest
    container_name: my-gateway
    ports:
      - "80:8080"                         # 对外暴露统一入口
    environment:
      SPRING_PROFILES_ACTIVE: prod
      JAVA_OPTS: "-Xms256m -Xmx256m"
      # 网关路由配置：下游服务使用 Compose 服务名
      SPRING_CLOUD_GATEWAY_ROUTES_0_ID: user-service
      SPRING_CLOUD_GATEWAY_ROUTES_0_URI: http://user-service:8080
      SPRING_CLOUD_GATEWAY_ROUTES_0_PREDICATES_0: Path=/api/users/**
      SPRING_CLOUD_GATEWAY_ROUTES_1_ID: order-service
      SPRING_CLOUD_GATEWAY_ROUTES_1_URI: http://order-service:8080
      SPRING_CLOUD_GATEWAY_ROUTES_1_PREDICATES_0: Path=/api/orders/**
      # Nacos 注册中心地址
      SPRING_CLOUD_NACOS_DISCOVERY_SERVER_ADDR: nacos:8848
      TZ: Asia/Shanghai
    networks:
      - app-network
    depends_on:
      nacos:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  # ==================== 用户服务 ====================
  user-service:
    image: user-service:latest
    container_name: user-service
    ports:
      - "8081:8080"                       # 仅调试用，生产环境不暴露
    environment:
      SPRING_PROFILES_ACTIVE: prod
      JAVA_OPTS: "-Xms256m -Xmx256m"
      SPRING_APPLICATION_NAME: user-service
      # 数据库连接：每个服务独享数据库
      SPRING_DATASOURCE_URL: "jdbc:mysql://mysql:3306/user_db?useSSL=false&serverTimezone=Asia/Shanghai&characterEncoding=utf8mb4"
      SPRING_DATASOURCE_USERNAME: root
      SPRING_DATASOURCE_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      # Redis 连接
      SPRING_REDIS_HOST: redis
      SPRING_REDIS_PORT: 6379
      SPRING_REDIS_PASSWORD: ${REDIS_PASSWORD}
      # Nacos 注册中心
      SPRING_CLOUD_NACOS_DISCOVERY_SERVER_ADDR: nacos:8848
      TZ: Asia/Shanghai
    networks:
      - app-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      nacos:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  # ==================== 订单服务 ====================
  order-service:
    image: order-service:latest
    container_name: order-service
    ports:
      - "8082:8080"                       # 仅调试用
    environment:
      SPRING_PROFILES_ACTIVE: prod
      JAVA_OPTS: "-Xms256m -Xmx256m"
      SPRING_APPLICATION_NAME: order-service
      # 订单服务有自己独立的数据库
      SPRING_DATASOURCE_URL: "jdbc:mysql://mysql:3306/order_db?useSSL=false&serverTimezone=Asia/Shanghai&characterEncoding=utf8mb4"
      SPRING_DATASOURCE_USERNAME: root
      SPRING_DATASOURCE_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      # Redis 连接
      SPRING_REDIS_HOST: redis
      SPRING_REDIS_PORT: 6379
      SPRING_REDIS_PASSWORD: ${REDIS_PASSWORD}
      # Nacos 注册中心
      SPRING_CLOUD_NACOS_DISCOVERY_SERVER_ADDR: nacos:8848
      # 调用用户服务的地址（通过 Nacos 服务发现，也可直连）
      # 直连方式：USER_SERVICE_URL=http://user-service:8080
      TZ: Asia/Shanghai
    networks:
      - app-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      nacos:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  # ==================== Nacos 注册中心 ====================
  nacos:
    image: nacos/nacos-server:v2.2.3
    container_name: my-nacos
    ports:
      - "8848:8848"                       # Nacos API 端口
      - "9848:9848"                       # Nacos gRPC 端口（2.x 需要）
    environment:
      MODE: standalone                    # 单机模式
      SPRING_DATASOURCE_PLATFORM: mysql   # 使用 MySQL 持久化
      MYSQL_SERVICE_HOST: mysql
      MYSQL_SERVICE_PORT: 3306
      MYSQL_SERVICE_DB_NAME: nacos_config
      MYSQL_SERVICE_USER: root
      MYSQL_SERVICE_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      JVM_XMS: 256m
      JVM_XMX: 256m
      TZ: Asia/Shanghai
    volumes:
      - nacos-logs:/home/nacos/logs
    networks:
      - app-network
    depends_on:
      mysql:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8848/nacos/v1/console/health/readiness"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  # ==================== MySQL（共享数据库服务） ====================
  mysql:
    image: mysql:8.0
    container_name: my-mysql
    ports:
      - "127.0.0.1:3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      TZ: Asia/Shanghai
    volumes:
      - mysql-data:/var/lib/mysql
      # 初始化多个数据库
      - ./mysql/init:/docker-entrypoint-initdb.d
    networks:
      - app-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p$$MYSQL_ROOT_PASSWORD"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

  # ==================== Redis（共享缓存服务） ====================
  redis:
    image: redis:7-alpine
    container_name: my-redis
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis-data:/data
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
    networks:
      - app-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "$$REDIS_PASSWORD", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: redis-server /usr/local/etc/redis/redis.conf

networks:
  app-network:
    driver: bridge

volumes:
  mysql-data:
  redis-data:
  nacos-logs:
```

### 5.6.2 服务间调用配置

微服务间通过 Nacos 服务发现调用，无需硬编码地址：

```java
// 使用 OpenFeign 声明式调用（推荐）
@FeignClient(name = "user-service")  // name 对应 Nacos 中的服务名
public interface UserClient {

    @GetMapping("/api/users/{id}")
    UserDTO getUserById(@PathVariable("id") Long id);
}

// 在 order-service 中使用
@Service
public class OrderService {

    @Autowired
    private UserClient userClient;  // Nacos 自动发现 user-service 实例

    public OrderVO getOrderWithUser(Long orderId) {
        Order order = orderRepository.findById(orderId);
        UserDTO user = userClient.getUserById(order.getUserId());  // 通过 Nacos 调用
        return new OrderVO(order, user);
    }
}
```

```yaml
# application.yml - 通用微服务配置
spring:
  application:
    name: user-service             # 服务名，注册到 Nacos
  cloud:
    nacos:
      discovery:
        server-addr: ${SPRING_CLOUD_NACOS_DISCOVERY_SERVER_ADDR:nacos:8848}
        namespace: ${NACOS_NAMESPACE:public}
        group: ${NACOS_GROUP:DEFAULT_GROUP}
    # 负载均衡
    loadbalancer:
      ribbon:
        enabled: false             # 禁用 Ribbon，使用 Spring Cloud LoadBalancer

# Feign 配置
feign:
  client:
    config:
      default:
        connectTimeout: 5000
        readTimeout: 10000
  # 开启 Sentinel 熔断（可选）
  sentinel:
    enabled: true
```

### 5.6.3 统一网关配置

```yaml
# gateway 服务的 application.yml
server:
  port: 8080

spring:
  application:
    name: gateway
  cloud:
    nacos:
      discovery:
        server-addr: nacos:8848
    gateway:
      # 路由配置
      routes:
        # 用户服务路由
        - id: user-service
          uri: lb://user-service           # lb:// 表示从注册中心获取实例
          predicates:
            - Path=/api/users/**
          filters:
            - StripPrefix=0                # 不去掉前缀
            - AddRequestHeader=X-Gateway, gateway

        # 订单服务路由
        - id: order-service
          uri: lb://order-service
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=0

      # 全局跨域配置
      globalcors:
        cors-configurations:
          '[/**]':
            allowedOrigins: "*"
            allowedMethods: "*"
            allowedHeaders: "*"

      # 默认过滤器
      default-filters:
        - AddResponseHeader=X-Response-Gateway, my-gateway
```

---

# 第六章：生产环境实战模式

## 6.1 日志管理

### 6.1.1 stdout/stderr 日志 vs 文件日志

```
┌─────────────────┬──────────────────────────────┬──────────────────────────────┐
│                 │  stdout/stderr（推荐）         │  文件日志                     │
├─────────────────┼──────────────────────────────┼──────────────────────────────┤
│ Docker 集成     │ docker logs 直接查看           │ 需挂载卷或 exec 进入容器       │
│ 日志轮转        │ Docker 原生支持                │ 应用自行管理（logback 等）      │
│ 日志收集        │ 日志驱动直接对接收集系统         │ 需额外 Filebeat/Flume         │
│ 容器迁移        │ 日志随容器删除而丢失             │ 挂载卷可持久化                  │
│ 多行日志        │ 可能被截断                      │ 完整保存                      │
│ 结构化日志      │ 需要 JSON 格式化               │ 自由格式                      │
│ 推荐场景        │ 云原生 / K8s / 集中式日志系统    │ 传统部署 / 需要日志文件审计      │
└─────────────────┴──────────────────────────────┴──────────────────────────────┘

推荐：stdout/stderr 为主 + 文件日志为辅（挂载卷持久化关键日志）
```

### 6.1.2 Docker 日志驱动

```bash
# 查看当前日志驱动
docker info --format '{{.LoggingDriver}}'

# 查看容器使用的日志驱动
docker inspect --format '{{.HostConfig.LogConfig.Type}}' my-app
```

```yaml
# json-file 驱动（默认）
# 日志以 JSON 格式存储在 /var/lib/docker/containers/<容器ID>/下
# 优点：docker logs 命令直接可用
# 缺点：不限制大小时会无限增长，占用磁盘
services:
  app:
    logging:
      driver: json-file
      options:
        max-size: "10m"        # 单个日志文件最大 10MB
        max-file: "3"          # 最多 3 个文件
        compress: "true"       # 旋转后的旧文件压缩存储
        labels: "production"   # 为日志添加标签
        tag: "{{.Name}}/{{.ID}}"  # 日志标签模板

# local 驱动（推荐替代 json-file）
# 使用更高效的压缩存储，日志文件更小
services:
  app:
    logging:
      driver: local
      options:
        max-size: "10m"
        max-file: "5"

# syslog 驱动
# 将日志发送到 syslog 守护进程
services:
  app:
    logging:
      driver: syslog
      options:
        syslog-address: "tcp://192.168.1.100:514"
        syslog-facility: "daemon"
        tag: "my-app"

# fluentd 驱动
# 将日志发送到 Fluentd 收集器
services:
  app:
    logging:
      driver: fluentd
      options:
        fluentd-address: "localhost:24224"
        tag: "my-app"
        fluentd-async: "true"  # 异步发送，不阻塞应用
```

### 6.1.3 日志轮转配置

```bash
# docker run 方式配置日志轮转
docker run -d \
  --name my-app \
  --log-driver json-file \
  --log-opt max-size=10m \         # 单个文件最大 10MB
  --log-opt max-file=3 \           # 最多保留 3 个文件
  --log-opt compress=true \        # 压缩旧文件
  my-app:latest

# 全局默认配置（/etc/docker/daemon.json）
# 所有容器默认使用此配置，除非容器单独指定
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3",
    "compress": "true"
  }
}

# 修改 daemon.json 后重启 Docker
systemctl restart docker
```

### 6.1.4 Compose 中配置日志轮转

```yaml
services:
  app:
    image: my-app:latest
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
        compress: "true"

  mysql:
    image: mysql:8.0
    logging:
      driver: json-file
      options:
        max-size: "20m"          # 数据库日志可以大一些
        max-file: "3"

  nginx:
    image: nginx:alpine
    logging:
      driver: json-file
      options:
        max-size: "50m"          # Nginx 访问日志量可能很大
        max-file: "10"
```

### 6.1.5 Spring Boot 日志配置最佳实践

**logback-spring.xml 配置（输出到 stdout）**：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <!-- 从 Spring 环境中读取日志路径，默认为 ./logs -->
    <springProperty scope="context" name="LOG_PATH" source="logging.file.path" defaultValue="./logs"/>
    <springProperty scope="context" name="APP_NAME" source="spring.application.name" defaultValue="app"/>

    <!-- 控制台输出（stdout）—— Docker 日志驱动会捕获 -->
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <!-- JSON 格式输出，便于日志收集系统解析 -->
            <pattern>
                {"timestamp":"%d{yyyy-MM-dd'T'HH:mm:ss.SSSZ}","level":"%level","service":"${APP_NAME}","traceId":"%X{traceId:-}","spanId":"%X{spanId:-}","thread":"%thread","logger":"%logger{36}","message":"%msg","exception":"%ex{full}"}
            </pattern>
        </encoder>
    </appender>

    <!-- 文件输出（挂载卷持久化）—— 作为备份 -->
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOG_PATH}/${APP_NAME}.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${LOG_PATH}/${APP_NAME}.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>50MB</maxFileSize>
            <maxHistory>30</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- 错误日志单独输出 -->
    <appender name="ERROR_FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOG_PATH}/${APP_NAME}-error.log</file>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${LOG_PATH}/${APP_NAME}-error.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>50MB</maxFileSize>
            <maxHistory>90</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- 生产环境：同时输出到控制台和文件 -->
    <springProfile name="prod">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="FILE"/>
            <appender-ref ref="ERROR_FILE"/>
        </root>
    </springProfile>

    <!-- 开发环境：仅输出到控制台 -->
    <springProfile name="dev">
        <root level="DEBUG">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

**Docker Compose 中日志目录挂载**：

```yaml
services:
  app:
    image: my-app:latest
    volumes:
      - ./logs/app:/app/logs    # 挂载日志目录到宿主机
    environment:
      LOGGING_FILE_PATH: /app/logs  # 指定日志路径
```

## 6.2 健康检查

### 6.2.1 HEALTHCHECK 指令详解

```dockerfile
# Dockerfile 中的 HEALTHCHECK 指令

# 基本语法
HEALTHCHECK [选项] CMD <命令>

# 完整示例
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1

# 参数详解：
# --interval=30s       健康检查间隔，默认 30s
# --timeout=10s        单次检查超时时间，默认 30s
# --retries=3          连续失败次数后标记 unhealthy，默认 3
# --start-period=40s   容器启动后的宽限期，此期间检查失败不计入 retries，默认 0s

# 禁用健康检查（覆盖基础镜像中的 HEALTHCHECK）
HEALTHCHECK NONE
```

**健康状态**：

```
starting  → 容器刚启动，在 start-period 内
healthy   → 健康检查连续通过
unhealthy → 健康检查连续失败 retries 次
```

### 6.2.2 Spring Boot Actuator /actuator/health 集成

```xml
<!-- pom.xml - 添加 Actuator 依赖 -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

```yaml
# application.yml - Actuator 配置
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus  # 暴露的端点
  endpoint:
    health:
      show-details: when-authorized  # 显示详细健康信息
      probes:
        enabled: true                # 启用 liveness/readiness 探针（Spring Boot 2.3+）
  health:
    defaults:
      enabled: true
    db:
      enabled: true                  # 数据库健康检查
    redis:
      enabled: true                  # Redis 健康检查
    diskspace:
      enabled: true                  # 磁盘空间检查
      threshold: 10MB               # 磁盘空间阈值
```

**Dockerfile 中使用 Actuator 健康检查**：

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1
```

**Spring Boot 2.3+ Liveness/Readiness 探针**：

```yaml
# application.yml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: always

# 启用后提供两个端点：
# /actuator/health/liveness   - 存活探针（应用是否运行中）
# /actuator/health/readiness  - 就绪探针（应用是否可以接收流量）
```

```dockerfile
# 区分存活和就绪检查
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health/liveness || exit 1
```

### 6.2.3 curl 健康检查脚本

```bash
#!/bin/sh
# healthcheck.sh - 完整的健康检查脚本

# 检查应用 HTTP 端点
check_http() {
    local url="${1:-http://localhost:8080/actuator/health}"
    local timeout="${2:-5}"

    # 使用 curl 检查，-f 表示 HTTP 错误时返回非零
    # -s 静默模式，-S 显示错误，-m 超时时间
    http_code=$(curl -sf -o /dev/null -w "%{http_code}" -m "$timeout" "$url" 2>/dev/null)

    if [ "$http_code" = "200" ]; then
        return 0
    else
        echo "Health check failed: HTTP $http_code for $url"
        return 1
    fi
}

# 检查进程是否存在
check_process() {
    local process_name="${1:-java}"
    if pgrep -f "$process_name" > /dev/null 2>&1; then
        return 0
    else
        echo "Process $process_name not found"
        return 1
    fi
}

# 检查磁盘空间
check_disk() {
    local path="${1:-/}"
    local threshold="${2:-90}"  # 使用率阈值百分比

    usage=$(df "$path" | tail -1 | awk '{print $5}' | tr -d '%')
    if [ "$usage" -lt "$threshold" ]; then
        return 0
    else
        echo "Disk usage ${usage}% exceeds threshold ${threshold}%"
        return 1
    fi
}

# 执行所有检查
main() {
    check_process java || return 1
    check_http "http://localhost:8080/actuator/health" 5 || return 1
    check_disk "/" 90 || return 1
    return 0
}

main
```

### 6.2.4 docker run --health-cmd 方式

```bash
# 使用 curl 检查
docker run -d \
  --name my-app \
  --health-cmd="curl -f http://localhost:8080/actuator/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=60s \
  my-app:latest

# 使用 wget 检查（Alpine 镜像没有 curl）
docker run -d \
  --name my-app \
  --health-cmd="wget --no-verbose --tries=1 --spider http://localhost:8080/actuator/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=60s \
  my-app:latest

# 查看健康检查状态
docker inspect --format='{{.State.Health.Status}}' my-app

# 查看健康检查日志
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' my-app
```

### 6.2.5 健康检查参数调优建议

```
场景                          interval  timeout  retries  start-period
─────────────────────────────────────────────────────────────────────────
Spring Boot 应用（启动慢）      30s       10s      3        60-120s
MySQL（初始化慢）               10s       5s       5        30-60s
Redis（启动快）                 10s       3s       3        10s
Nginx（启动快）                 30s       5s       3        10s
Nacos（启动较慢）               10s       5s       10       30s

调优原则：
1. start-period 必须大于应用最慢启动时间
2. interval × retries 应小于故障检测容忍时间
3. timeout 应小于 interval，避免检查堆积
4. 轻量级服务用较短间隔，重量级服务用较长间隔
5. 健康检查命令应尽可能轻量（避免占用应用资源）
```

## 6.3 JVM 监控与诊断

### 6.3.1 JMX 远程连接

```bash
# 完整的 JMX 远程连接 JAVA_OPTS 配置
JAVA_OPTS="-Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=<宿主机IP>"

# 参数详解：
# -Dcom.sun.management.jmxremote              启用 JMX 远程连接
# -Dcom.sun.management.jmxremote.port=9010     JMX 端口
# -Dcom.sun.management.jmxremote.rmi.port=9010 RMI 端口（建议与 JMX 端口相同，简化端口映射）
# -Dcom.sun.management.jmxremote.authenticate=false  不使用认证（生产环境应启用）
# -Dcom.sun.management.jmxremote.ssl=false     不使用 SSL（生产环境应启用）
# -Djava.rmi.server.hostname=<宿主机IP>        RMI 回连地址（必须设为宿主机可达的 IP）

# docker run 启动时暴露 JMX 端口
docker run -d \
  --name my-app \
  -p 8080:8080 \
  -p 9010:9010 \
  -e JAVA_OPTS="-Dcom.sun.management.jmxremote \
    -Dcom.sun.management.jmxremote.port=9010 \
    -Dcom.sun.management.jmxremote.rmi.port=9010 \
    -Dcom.sun.management.jmxremote.authenticate=false \
    -Dcom.sun.management.jmxremote.ssl=false \
    -Djava.rmi.server.hostname=192.168.1.100" \
  my-app:latest

# Docker Compose 配置
services:
  app:
    image: my-app:latest
    ports:
      - "8080:8080"
      - "9010:9010"          # JMX 端口
    environment:
      JAVA_OPTS: >-
        -Dcom.sun.management.jmxremote
        -Dcom.sun.management.jmxremote.port=9010
        -Dcom.sun.management.jmxremote.rmi.port=9010
        -Dcom.sun.management.jmxremote.authenticate=false
        -Dcom.sun.management.jmxremote.ssl=false
        -Djava.rmi.server.hostname=192.168.1.100
```

**使用 JConsole 连接**：

```
1. 本地安装 JDK，启动 jconsole
2. 在"远程进程"中输入：192.168.1.100:9010
3. 如果启用了认证，输入用户名和密码
4. 连接成功后可查看内存、线程、类、MBean 等
```

**使用 VisualVM 连接**：

```
1. 启动 VisualVM
2. 文件 → 添加 JMX 连接
3. 输入：192.168.1.100:9010
4. 勾选"不要求 SSL 连接"（如果未启用 SSL）
```

### 6.3.2 Arthas 在容器中使用

Arthas 是阿里巴巴开源的 Java 诊断工具，可以在不修改应用代码的情况下进行在线诊断。

```bash
# 方式一：docker exec 运行 Arthas（推荐）
# 1. 先下载 Arthas 到宿主机
curl -O https://arthas.aliyun.com/arthas-boot.jar

# 2. 将 Arthas 复制到容器中
docker cp arthas-boot.jar my-app:/tmp/

# 3. 进入容器执行 Arthas
docker exec -it my-app java -jar /tmp/arthas-boot.jar

# 4. Arthas 会列出容器中的 Java 进程，选择要诊断的进程编号
# 5. 连接成功后即可使用各种诊断命令

# 方式二：挂载 Arthas 目录
# 1. 在宿主机解压 Arthas
mkdir -p /opt/arthas
curl -O https://arthas.aliyun.com/arthas-boot.jar
# 首次运行会自动下载到 ~/.arthas/ 目录

# 2. 启动容器时挂载 Arthas
docker run -d \
  --name my-app \
  -v /opt/arthas:/opt/arthas \
  my-app:latest

# 3. 进入容器使用
docker exec -it my-app java -jar /opt/arthas/arthas-boot.jar

# 方式三：构建包含 Arthas 的诊断镜像
```

```dockerfile
# Dockerfile - 包含 Arthas 的诊断镜像
FROM my-app:latest

# 切换到 root 安装工具
USER root
RUN apk add --no-cache curl

# 下载 Arthas
RUN mkdir -p /opt/arthas && \
    cd /opt/arthas && \
    curl -O https://arthas.aliyun.com/arthas-boot.jar

# 切换回应用用户
USER appuser
```

**Arthas 常用命令**：

```bash
# 查看 Dashboard（线程、内存、GC 等概览）
dashboard

# 查看线程信息
thread                          # 列出所有线程
thread -n 3                     # CPU 使用率最高的 3 个线程
thread -b                       # 查找死锁

# 查看方法调用
watch com.example.UserService getUser '{params, returnObj, throwExp}' -x 2

# 查看方法调用路径和耗时
trace com.example.UserService getUser

# 查看已加载的类
sc -d com.example.UserService

# 查看方法参数和返回值
monitor com.example.UserService getUser -c 10

# 查看 JVM 信息
jvm

# 查看内存使用
memory

# 查看 Spring Bean
ognl '@com.example.ApplicationContextProvider@getBean("userService")'

# 反编译类
jad com.example.UserService

# 退出 Arthas（不影响应用）
quit        # 退出当前 session
stop        # 彻底销毁 Arthas 服务端
```

### 6.3.3 Heap Dump 导出

```bash
# 方式一：使用 jmap 命令（容器内）
# 1. 找到 Java 进程 PID
docker exec my-app jps -l
# 输出：1 my-app.jar

# 2. 导出 Heap Dump
docker exec my-app jmap -dump:format=b,file=/app/logs/heapdump.hprof 1

# 3. 将 Dump 文件从容器复制到宿主机
docker cp my-app:/app/logs/heapdump.hprof ./heapdump.hprof

# 方式二：挂载宿主机目录（自动保存 Dump 文件）
docker run -d \
  --name my-app \
  -v /data/dumps:/app/dumps \
  -e JAVA_OPTS="-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/app/dumps/heapdump.hprof" \
  my-app:latest

# 方式三：使用 Arthas 导出
docker exec -it my-app java -jar /opt/arthas/arthas-boot.jar
# 在 Arthas 控制台中：
heapdump /app/logs/heapdump.hprof           # 导出完整堆
heapdump --live /app/logs/heapdump-live.hprof  # 仅导出存活对象

# 方式四：自动 HeapDump 配置
# 在 JAVA_OPTS 中配置，OOM 时自动导出
-XX:+HeapDumpOnOutOfMemoryError                    # OOM 时自动生成 Heap Dump
-XX:HeapDumpPath=/app/logs/heapdump.hprof          # Dump 文件路径
-XX:+HeapDumpBeforeFullGC                          # Full GC 前也生成 Dump（可选，影响性能）
```

**Docker Compose 完整配置**：

```yaml
services:
  app:
    image: my-app:latest
    volumes:
      - ./dumps:/app/dumps               # 挂载 Dump 目录
      - ./logs:/app/logs                 # 挂载日志目录
    environment:
      JAVA_OPTS: >-
        -Xms512m
        -Xmx512m
        -XX:+HeapDumpOnOutOfMemoryError
        -XX:HeapDumpPath=/app/dumps/heapdump.hprof
        -XX:ErrorFile=/app/logs/hs_err_pid%p.log
```

### 6.3.4 Thread Dump 导出

```bash
# 方式一：使用 jstack 命令
docker exec my-app jstack 1 > threaddump.txt

# 方式二：使用 kill -3（发送 SIGQUIT 信号）
# 线程 Dump 会输出到 stdout（被 Docker 日志捕获）
docker kill --signal=SIGQUIT my-app
# 然后查看日志
docker logs my-app | tail -200 > threaddump.txt

# 方式三：多次 Thread Dump（间隔 5 秒，共 3 次，用于分析线程状态变化）
for i in 1 2 3; do
  docker exec my-app jstack 1 >> threaddump_$i.txt
  sleep 5
done

# 方式四：使用 Arthas
docker exec -it my-app java -jar /opt/arthas/arthas-boot.jar
# 在 Arthas 控制台中：
thread -n 5                    # 查看最忙的 5 个线程
thread --state BLOCKED         # 查看阻塞的线程
thread --state WAITING         # 查看等待的线程
```

### 6.3.5 GC 日志配置与查看

```bash
# Java 8 GC 日志配置
JAVA_OPTS="-XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -XX:+PrintGCApplicationStoppedTime \
  -XX:+PrintHeapAtGC \
  -Xloggc:/app/logs/gc.log \
  -XX:+UseGCLogFileRotation \
  -XX:NumberOfGCLogFiles=5 \
  -XX:GCLogFileSize=10M"

# Java 11+ GC 日志配置（Xlog 统一日志框架）
JAVA_OPTS="-Xlog:gc*:file=/app/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=10M"

# Xlog 语法：-Xlog:what:output:decorators:output-options
# what        - 日志标签，gc* 表示所有 GC 相关日志
# output      - 输出位置，file=/app/logs/gc.log
# decorators  - 附加信息，time(时间), uptime(JVM启动后时间), level(级别), tags(标签)
# output-options - filecount=5(最多5个文件), filesize=10M(每个10MB)
```

**Docker Compose 配置**：

```yaml
services:
  app:
    image: my-app:latest
    volumes:
      - ./logs:/app/logs
    environment:
      # Java 11+ GC 日志配置
      JAVA_OPTS: >-
        -Xms512m
        -Xmx512m
        -XX:+UseG1GC
        -Xlog:gc*:file=/app/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=10M
        -XX:+HeapDumpOnOutOfMemoryError
        -XX:HeapDumpPath=/app/dumps/
```

**GC 日志分析工具**：

```
1. GCEasy（在线）：https://gceasy.io/ - 上传 gc.log 即可分析
2. GCViewer（离线）：开源 GC 日志分析工具
3. JDK Mission Control（JMC）：JDK 自带的分析工具
```

### 6.3.6 Prometheus JMX Exporter 集成

JMX Exporter 将 JMX 指标转换为 Prometheus 格式，便于监控：

```yaml
# 方式一：作为 Java Agent 运行（推荐）
services:
  app:
    image: my-app:latest
    ports:
      - "8080:8080"
      - "9404:9404"          # JMX Exporter 暴露的 metrics 端口
    volumes:
      - ./monitoring/jmx-exporter-config.yaml:/app/jmx-exporter-config.yaml:ro
      - ./monitoring/jmx_prometheus_javaagent.jar:/app/jmx_prometheus_javaagent.jar:ro
    environment:
      # JMX Exporter 作为 Java Agent 启动
      # 格式：-javaagent:jmx_exporter.jar=端口号:配置文件
      JAVA_OPTS: >-
        -javaagent:/app/jmx_prometheus_javaagent.jar=9404:/app/jmx-exporter-config.yaml
        -Xms512m -Xmx512m
```

**JMX Exporter 配置文件**（`jmx-exporter-config.yaml`）：

```yaml
# JMX Exporter 配置 - 采集常用 JVM 指标
startDelaySeconds: 0
ssl: false
lowercaseOutputName: true
lowercaseOutputLabelNames: true
rules:
  # 内存指标
  - pattern: 'java.lang<type=Memory><HeapMemoryUsage>used'
    name: jvm_heap_memory_used
    type: GAUGE
  - pattern: 'java.lang<type=Memory><HeapMemoryUsage>max'
    name: jvm_heap_memory_max
    type: GAUGE
  # GC 指标
  - pattern: 'java.lang<type=GarbageCollector, name=(.+)><>CollectionCount'
    name: jvm_gc_collection_count
    labels:
      gc: "$1"
    type: COUNTER
  - pattern: 'java.lang<type=GarbageCollector, name=(.+)><>CollectionTime'
    name: jvm_gc_collection_time_ms
    labels:
      gc: "$1"
    type: COUNTER
  # 线程指标
  - pattern: 'java.lang<type=Threading><>ThreadCount'
    name: jvm_thread_count
    type: GAUGE
  - pattern: 'java.lang<type=Threading><>DeadlockedThreads'
    name: jvm_deadlocked_threads
    type: GAUGE
```

**Prometheus 采集配置**：

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'my-app'
    static_configs:
      - targets: ['app:9404']    # Compose 服务名:JMX Exporter 端口
```

## 6.4 优雅停机

### 6.4.1 Spring Boot 2.3+ graceful shutdown 配置

```yaml
# application.yml - 优雅停机配置
server:
  shutdown: graceful                # 启用优雅停机，默认 immediate（立即关闭）

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s  # 优雅停机超时时间，默认 30s
                                     # 超时后强制关闭（即使还有请求未完成）

# 工作原理：
# 1. 收到 SIGTERM 信号
# 2. Web 服务器停止接收新请求
# 3. 等待正在处理的请求完成
# 4. 超时后强制关闭剩余请求
# 5. 关闭 Spring 容器
```

### 6.4.2 docker stop 超时机制

```bash
# docker stop 工作流程：
# 1. 向容器主进程（PID 1）发送 SIGTERM 信号
# 2. 等待指定超时时间（默认 10 秒）
# 3. 如果进程仍未退出，发送 SIGKILL 信号强制终止

# 默认超时 10 秒
docker stop my-app

# 自定义超时时间（与 Spring Boot 的 shutdown timeout 配合）
# Docker 超时应大于 Spring Boot 优雅停机超时
docker stop -t 60 my-app          # 等待 60 秒

# docker compose 中配置
docker compose stop -t 60 app     # 等待 60 秒

# docker compose down 中配置
docker compose down -t 60         # 等待 60 秒
```

```yaml
# Docker Compose 中配置 stop_grace_period
services:
  app:
    image: my-app:latest
    # stop_grace_period：Docker 发送 SIGTERM 后等待多长时间再发 SIGKILL
    # 应大于 spring.lifecycle.timeout-per-shutdown-phase
    stop_grace_period: 60s
```

### 6.4.3 STOPSIGNAL 与 SIGTERM 处理

```dockerfile
# Dockerfile 中指定停止信号
# 默认是 SIGTERM，可以改为其他信号
STOPSIGNAL SIGTERM

# 如果使用 shell 形式的 ENTRYPOINT，需要用 exec 确保应用是 PID 1
# 错误：shell 是 PID 1，应用收不到 SIGTERM
ENTRYPOINT java -jar app.jar

# 正确方式一：exec 形式（推荐）
ENTRYPOINT ["java", "-jar", "app.jar"]

# 正确方式二：shell 形式中使用 exec
ENTRYPOINT exec java -jar app.jar

# 正确方式三：使用启动脚本时用 exec
# entrypoint.sh
#!/bin/sh
echo "Starting application..."
exec java $JAVA_OPTS -jar app.jar   # exec 使 java 进程替代 sh 成为 PID 1
```

**使用启动脚本时的正确写法**：

```bash
#!/bin/sh
# entrypoint.sh - 正确处理信号的启动脚本

# 捕获 SIGTERM 信号并转发给 Java 进程
# 这在使用 shell 形式的 ENTRYPOINT 时很重要

# 启动 Java 应用（后台运行）
java $JAVA_OPTS -jar app.jar &
JAVA_PID=$!

# 信号处理函数
shutdown() {
    echo "Received shutdown signal, forwarding to Java process $JAVA_PID"
    kill -TERM "$JAVA_PID"
    wait "$JAVA_PID"
    exit $?
}

# 注册信号处理
trap shutdown TERM INT

# 等待 Java 进程结束
wait "$JAVA_PID"
```

### 6.4.4 PrePost Hook（K8s 简要提及）

在 Kubernetes 中，PreStop Hook 可以在容器终止前执行操作：

```yaml
# Kubernetes Pod 配置（仅作参考）
spec:
  containers:
    - name: app
      lifecycle:
        preStop:
          exec:
            # 在收到 SIGTERM 前执行，等待一段时间让负载均衡器摘除 Pod
            command: ["/bin/sh", "-c", "sleep 15"]
      # 优雅终止宽限期
      terminationGracePeriodSeconds: 60
```

**Docker 环境中的替代方案**：

```bash
# Docker 本身不支持 PreStop Hook
# 可以通过启动脚本模拟类似行为

#!/bin/sh
# entrypoint.sh with pre-stop logic

# PreStop 逻辑：通知服务注册中心下线
pre_stop() {
    echo "Executing pre-stop hook..."
    # 通知 Nacos/Eureka 下线
    curl -X PUT "http://nacos:8848/nacos/v1/ns/instance?serviceName=my-app&ip=${HOST_IP}&port=8080&enabled=false"
    # 等待一段时间让网关刷新路由
    sleep 10
}

# 启动应用
java $JAVA_OPTS -jar app.jar &
JAVA_PID=$!

shutdown() {
    pre_stop                      # 执行 PreStop 逻辑
    kill -TERM "$JAVA_PID"        # 发送 SIGTERM
    wait "$JAVA_PID"
    exit $?
}

trap shutdown TERM INT
wait "$JAVA_PID"
```

### 6.4.5 完整配置示例

```dockerfile
# Dockerfile - 支持优雅停机
FROM eclipse-temurin:11-jre-alpine

WORKDIR /app
COPY target/my-app.jar app.jar
COPY entrypoint.sh entrypoint.sh

RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app \
    && chmod +x entrypoint.sh

USER appuser

EXPOSE 8080

# 确保使用 exec 形式，Java 进程为 PID 1
ENTRYPOINT ["./entrypoint.sh"]

# 指定停止信号
STOPSIGNAL SIGTERM
```

```bash
#!/bin/sh
# entrypoint.sh
set -e

echo "Starting application..."

# 直接 exec，使 Java 进程成为 PID 1，可以直接接收 SIGTERM
exec java ${JAVA_OPTS} -jar app.jar
```

```yaml
# docker-compose.yml - 完整优雅停机配置
services:
  app:
    build: .
    image: my-app:latest
    stop_grace_period: 60s             # Docker 等待 60 秒再 SIGKILL
    environment:
      JAVA_OPTS: >-
        -Xms512m
        -Xmx512m
      # Spring Boot 优雅停机配置
      SERVER_SHUTDOWN: graceful                    # 启用优雅停机
      SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE: 30s  # 最多等 30 秒处理完请求
```

## 6.5 镜像版本管理与回滚策略

### 6.5.1 镜像 tag 命名规范

```
推荐格式：<镜像名>:<日期>-<commit短hash>
示例：my-app:20240115-a1b2c3d

其他命名方式：
1. 日期+commit短hash（推荐，信息最全）
   my-app:20240115-a1b2c3d

2. 语义版本号
   my-app:1.2.0
   my-app:1.2.1-hotfix

3. 分支名+构建号
   my-app:main-123
   my-app:release-1.2-45

4. Git Tag
   my-app:v1.2.0

latest 的坑：
- latest 只是默认标签，不代表"最新版本"
- 多次推送 latest 会覆盖之前的镜像，无法回溯
- 不同人推送的 latest 可能指向不同版本
- 拉取 latest 的结果不可预期
- 生产环境绝对不要使用 latest
```

**CI/CD 中自动打标签示例**：

```bash
# GitLab CI 示例
docker build -t registry.example.com/my-app:$CI_COMMIT_SHORT_SHA .
docker tag registry.example.com/my-app:$CI_COMMIT_SHORT_SHA \
             registry.example.com/my-app:$CI_COMMIT_TAG
docker push registry.example.com/my-app --all-tags

# GitHub Actions 示例
docker build -t my-app:${{ github.sha }} .
docker tag my-app:${{ github.sha }} my-app:$(date +%Y%m%d)-${GITHUB_SHA:0:7}
```

### 6.5.2 版本回滚流程

```bash
# 场景：新版本 v2.0.0 出问题，需要回滚到 v1.9.0

# 步骤一：查看历史版本
docker images my-app --format "{{.Tag}} {{.CreatedAt}}"
# 输出：
# v2.0.0  2024-01-15 10:30:00
# v1.9.0  2024-01-10 14:20:00
# v1.8.0  2024-01-05 09:15:00

# 步骤二：拉取旧版本镜像（如果本地没有）
docker pull registry.example.com/my-app:v1.9.0

# 步骤三：停止当前版本
docker stop my-app
docker rm my-app

# 步骤四：启动旧版本
docker run -d \
  --name my-app \
  -p 8080:8080 \
  registry.example.com/my-app:v1.9.0

# Docker Compose 回滚
# 1. 修改 docker-compose.yml 中的镜像版本
#    image: my-app:v1.9.0  ← 从 v2.0.0 改为 v1.9.0
# 2. 重新启动
docker compose up -d app

# 或者不修改文件，直接指定版本
IMAGE_VERSION=v1.9.0 docker compose up -d app
```

**自动化回滚脚本**：

```bash
#!/bin/bash
# rollback.sh - 自动回滚脚本

APP_NAME="my-app"
REGISTRY="registry.example.com"
CURRENT_VERSION=$(docker inspect --format='{{.Config.Image}}' $APP_NAME 2>/dev/null)

echo "当前版本: $CURRENT_VERSION"

# 回滚到指定版本
TARGET_VERSION=$1

if [ -z "$TARGET_VERSION" ]; then
    echo "用法: ./rollback.sh <目标版本号>"
    echo "示例: ./rollback.sh v1.9.0"
    exit 1
fi

TARGET_IMAGE="$REGISTRY/$APP_NAME:$TARGET_VERSION"
echo "回滚到: $TARGET_IMAGE"

# 拉取目标版本
docker pull "$TARGET_IMAGE"
if [ $? -ne 0 ]; then
    echo "错误：拉取镜像 $TARGET_IMAGE 失败"
    exit 1
fi

# 停止当前容器
docker stop -t 60 "$APP_NAME"
docker rm "$APP_NAME"

# 启动目标版本
docker run -d \
  --name "$APP_NAME" \
  --restart unless-stopped \
  -p 8080:8080 \
  "$TARGET_IMAGE"

echo "回滚完成！当前版本: $TARGET_IMAGE"
```

### 6.5.3 蓝绿 / 金丝雀发布简述

**蓝绿发布**：

```
原理：同时运行两个完全相同的环境（蓝/绿），切换流量

┌──────────┐     ┌──────────┐
│   蓝环境  │ ←── │  Nginx   │ ←── 用户流量
│ v1.9.0   │     │ (当前指向蓝)│
└──────────┘     └──────────┘
┌──────────┐
│   绿环境  │     切换后：Nginx 指向绿
│ v2.0.0   │
└──────────┘

Docker Compose 实现：
1. 启动绿环境（新版本）
2. 验证绿环境健康
3. 切换 Nginx 上游到绿
4. 停止蓝环境（保留一段时间以便回滚）
```

```yaml
# docker-compose.yml - 蓝绿发布
services:
  app-blue:
    image: my-app:v1.9.0
    environment:
      SERVER_PORT: 8081
    networks:
      - app-network

  app-green:
    image: my-app:v2.0.0
    environment:
      SERVER_PORT: 8082
    networks:
      - app-network

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx/nginx-blue.conf:/etc/nginx/conf.d/default.conf:ro  # 当前指向蓝
    networks:
      - app-network
    ports:
      - "80:80"

# 切换到绿环境：修改 nginx 配置指向 app-green，然后 nginx -s reload
```

**金丝雀发布**：

```
原理：先将少量流量导入新版本，逐步增加

用户流量 → Nginx → 90% → 旧版本 (v1.9.0)
                → 10% → 新版本 (v2.0.0)

验证指标正常后逐步扩大新版本流量比例

Docker Compose 实现较复杂，通常需要服务网格（Istio）或专用工具
```

## 6.6 安全加固

### 6.6.1 非 root 用户运行

```dockerfile
# Dockerfile - 非 root 用户运行

FROM eclipse-temurin:11-jre-alpine

# 创建非 root 用户和组
# -S 创建系统用户，-G 指定组
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

# 复制应用文件
COPY target/my-app.jar app.jar

# 关键：先创建目录并设置权限，再切换用户
# 必须在 USER 指令之前完成权限设置
RUN mkdir -p /app/logs /app/config /app/dumps && \
    chown -R appuser:appgroup /app

# 切换到非 root 用户
USER appuser

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
```

```bash
# 验证容器运行用户
docker exec my-app whoami
# 输出：appuser

docker exec my-app id
# 输出：uid=100(appuser) gid=101(appgroup) groups=101(appgroup)
```

**挂载卷的权限问题**：

```bash
# 挂载卷时，宿主机目录的 uid/gid 必须与容器内用户匹配
# appuser 的 uid 是 100，所以宿主机目录也要 uid=100 可写

# 创建宿主机目录并设置权限
mkdir -p ./logs ./config
chown -R 100:101 ./logs ./config    # 100 是 appuser 的 uid

# 或者在 Dockerfile 中使用与宿主机相同的 uid/gid
RUN addgroup -g 1000 appgroup && \
    adduser -u 1000 -G appgroup -S appuser
```

### 6.6.2 最小镜像原则

```dockerfile
# ---- Alpine 基础镜像（约 5MB） ----
FROM eclipse-temurin:11-jre-alpine
# Alpine 使用 musl libc（不是 glibc）
# 某些 Java 库可能不兼容
# 需要额外安装依赖时使用 apk add

# ---- Distroless 基础镜像（约 30MB） ----
# Google 出品，只包含应用运行时最小依赖
# 没有 shell、没有包管理器、没有常用命令
FROM gcr.io/distroless/java11-debian11
# 优点：攻击面极小
# 缺点：无法 exec 进入容器调试，没有 curl/wget
# 调试时可以复制一个 shell 进去：
# docker cp /bin/sh my-app:/bin/sh

# ---- 多阶段构建（最推荐） ----
# 第一阶段：构建（使用完整的 JDK 镜像）
FROM maven:3.9-eclipse-temurin-11 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B

# 第二阶段：运行（只使用 JRE 镜像）
FROM eclipse-temurin:11-jre-alpine
WORKDIR /app
COPY --from=builder /build/target/*.jar app.jar
RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]

# 镜像大小对比：
# openjdk:11                约 670MB  （完整 JDK + Debian）
# eclipse-temurin:11-jre    约 450MB  （JRE + Debian）
# eclipse-temurin:11-jre-alpine  约 170MB  （JRE + Alpine）
# gcr.io/distroless/java11  约 200MB  （JRE + 最小依赖）
# 多阶段构建后的最终镜像     约 170MB  （只含 JRE + JAR）
```

### 6.6.3 敏感信息处理

```dockerfile
# ---- 错误做法 ----
# 在 Dockerfile 中硬编码密码
ENV DB_PASSWORD=mysecretpassword          # 危险！会留在镜像层中
ENV API_KEY=sk-1234567890abcdef          # 危险！即使后续删除也能从层中恢复

# 即使在后续层中删除，仍然可以通过 docker history 或 dive 工具看到
ENV DB_PASSWORD=mysecretpassword
RUN unset DB_PASSWORD                     # 无效！变量仍在前面的层中

# 在 ARG 中使用敏感信息也需要注意
ARG DB_PASSWORD=mysecretpassword          # 会留在镜像历史中

# ---- 正确做法 ----
# 1. 运行时通过环境变量注入
docker run -e DB_PASSWORD=$DB_PASSWORD my-app:latest

# 2. 运行时通过 env_file 注入
docker run --env-file .secrets my-app:latest

# 3. 使用 Docker Secrets（Swarm 模式）
docker secret create db_password -

# 4. 使用 HashiCorp Vault 等密钥管理工具

# 5. 如果构建时必须使用敏感信息（如私有仓库认证）
# 使用 BuildKit 的 --mount=type=secret
DOCKER_BUILDKIT=1 docker build \
  --secret id=npmrc,src=.npmrc \
  -t my-app .
```

```dockerfile
# 使用 BuildKit Secret 的 Dockerfile
# syntax=docker/dockerfile:1

FROM node:18 AS builder
# 使用 --mount=type=secret 挂载敏感文件，不会留在镜像层中
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm install

# 第二阶段不包含任何敏感信息
FROM node:18-alpine
COPY --from=builder /app/node_modules ./node_modules
```

### 6.6.4 网络隔离

```yaml
# docker-compose.yml - 网络隔离设计
services:
  # 对外暴露的服务
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    networks:
      - frontend          # 仅在前端网络
    depends_on:
      - app

  # 应用服务：连接前端和后端
  app:
    image: my-app:latest
    ports:
      - "127.0.0.1:8080:8080"   # 仅本机可访问，不对外
    networks:
      - frontend          # 与 nginx 通信
      - backend           # 与数据库通信
    depends_on:
      - mysql
      - redis

  # 数据库服务：仅在后端网络
  mysql:
    image: mysql:8.0
    # 不映射端口！只通过内部网络访问
    networks:
      - backend
    volumes:
      - mysql-data:/var/lib/mysql

  # 缓存服务：仅在后端网络
  redis:
    image: redis:7-alpine
    # 不映射端口！
    networks:
      - backend
    volumes:
      - redis-data:/data

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true        # 内部网络，不允许端口映射到宿主机
```

### 6.6.5 只读文件系统

```bash
# docker run 使用只读文件系统
docker run -d \
  --name my-app \
  --read-only \                     # 根文件系统只读
  --tmpfs /tmp \                    # /tmp 使用 tmpfs（内存文件系统，可写）
  --tmpfs /app/logs:size=100m \     # 日志目录使用 tmpfs，限制 100MB
  -v app-config:/app/config:ro \    # 配置文件只读挂载
  my-app:latest
```

```yaml
# Docker Compose 中配置只读文件系统
services:
  app:
    image: my-app:latest
    read_only: true                    # 根文件系统只读
    tmpfs:                             # 需要写入的目录使用 tmpfs
      - /tmp
      - /app/logs:size=100m
    volumes:
      - app-config:/app/config:ro      # 配置只读挂载
```

### 6.6.6 镜像漏洞扫描

```bash
# ---- Docker Scout（Docker 官方） ----
# 扫描本地镜像
docker scout cves my-app:latest

# 扫描并只显示高严重性漏洞
docker scout cves --only-severity high,critical my-app:latest

# 比较两个版本的漏洞差异
docker scout compare --to my-app:v1.9.0 my-app:v2.0.0

# ---- Trivy（开源，推荐） ----
# 安装 Trivy
# Windows: choco install trivy
# Linux: apt-get install trivy

# 扫描镜像
trivy image my-app:latest

# 只显示高严重性漏洞
trivy image --severity HIGH,CRITICAL my-app:latest

# 输出 JSON 格式
trivy image --format json my-app:latest > scan-report.json

# 扫描并生成报告
trivy image --format table --output scan-report.txt my-app:latest

# CI/CD 中集成（扫描失败则构建失败）
trivy image --exit-code 1 --severity HIGH,CRITICAL my-app:latest
```

---

# 第七章：故障排查手册

## 7.1 容器启动失败

### 7.1.1 Exit Code 含义速查表

| Exit Code | 含义 | 常见原因 | 排查方向 |
|-----------|------|----------|----------|
| 0 | 正常退出 | 应用主动调用 `System.exit(0)` 或进程正常结束 | 检查是否误设了 `--rm` 导致容器退出后被删除 |
| 1 | 应用错误 | Java 应用抛出未捕获异常、配置错误、启动失败 | 查看 `docker logs` 中的异常堆栈 |
| 137 | OOMKilled | 容器内存超限被内核 OOM Killer 杀死 | 检查内存限制和 JVM 堆内存配置 |
| 139 | Segmentation Fault | 内存访问越界、native 库崩溃 | 检查 JNI 调用、native 依赖 |
| 143 | SIGTERM 终止 | `docker stop` 正常停止容器 | 正常现象，检查停机逻辑是否完整 |
| 126 | 权限不足 | 可执行文件无执行权限 | 检查 `chmod +x` |
| 127 | 命令不存在 | Dockerfile 中 CMD/ENTRYPOINT 指定的命令找不到 | 检查命令路径、是否安装了所需工具 |
| 125 | Docker 守护进程错误 | 守护进程启动容器失败 | 检查 Docker 配置、磁盘空间 |
| 128+n | 信号退出 | 128 + 信号编号，如 128+9=137 (SIGKILL) | 根据信号编号判断原因 |

### 7.1.2 日志查看方法

```bash
# 查看容器日志（最常用）
docker logs my-app                     # 查看所有日志
docker logs -f my-app                  # 实时跟踪日志
docker logs --tail 100 my-app          # 最后 100 行
docker logs --since 30m my-app         # 最近 30 分钟
docker logs --since "2024-01-15T10:00:00" my-app  # 指定时间之后
docker logs -t my-app                  # 显示时间戳

# 查看 Docker 事件流
docker events --filter container=my-app --filter event=die
# 实时监控容器事件：创建、启动、停止、死亡、OOM 等

# 查看容器详细信息
docker inspect my-app                  # 完整 JSON 输出
docker inspect --format='{{.State.Status}}' my-app          # 容器状态
docker inspect --format='{{.State.ExitCode}}' my-app        # 退出码
docker inspect --format='{{.State.Error}}' my-app           # 错误信息
docker inspect --format='{{.State.OOMKilled}}' my-app       # 是否 OOM
docker inspect --format='{{.NetworkSettings.IPAddress}}' my-app  # IP 地址

# 查看容器内进程
docker top my-app                      # 查看容器内进程列表
docker stats my-app                    # 实时资源使用统计
docker stats --no-stream my-app        # 一次性输出资源使用

# 查看容器文件系统变化
docker diff my-app                     # A=新增, C=修改, D=删除
```

### 7.1.3 常见原因与解决方案

**场景 1：Java 应用启动报数据库连接失败**

```bash
# 症状
docker logs my-app
# 输出：com.mysql.cj.jdbc.exceptions.CommunicationsException: Communications link failure

# 排查步骤
# 1. 检查 MySQL 容器是否运行
docker ps | grep mysql

# 2. 检查两个容器是否在同一网络
docker network inspect my-app-network

# 3. 尝试从 app 容器连接 MySQL
docker exec my-app ping mysql
docker exec my-app nc -zv mysql 3306

# 4. 检查 MySQL 是否就绪
docker exec my-mysql mysqladmin ping -h localhost -u root -p$MYSQL_ROOT_PASSWORD

# 解决方案：
# - 确保 depends_on + healthcheck 正确配置
# - 增大 start_period 或添加等待脚本
# - 检查网络连接
```

**场景 2：端口冲突**

```bash
# 症状
docker compose up
# 错误：Bind for 0.0.0.0:8080 failed: port is already allocated

# 排查：查看谁占用了端口
netstat -tlnp | grep 8080            # Linux
# 或
Get-NetTCPConnection -LocalPort 8080  # Windows PowerShell

# 解决方案：
# - 停止占用端口的服务
# - 修改 Compose 文件中的宿主机端口映射
# - 使用 127.0.0.1:8080:8080 限制绑定地址
```

**场景 3：磁盘空间不足**

```bash
# 症状
# 错误：no space left on device

# 排查
df -h                                 # 查看磁盘使用
docker system df                      # 查看 Docker 磁盘使用
docker system df -v                   # 详细信息

# 清理
docker system prune                   # 清理未使用的资源（容器、网络、镜像、构建缓存）
docker system prune --volumes         # 同时清理数据卷（危险！）
docker system prune -a                # 清理所有未使用的镜像（不仅是悬空镜像）
docker volume prune                   # 清理未使用的数据卷
docker builder prune                  # 清理构建缓存
```

**场景 4：权限被拒绝**

```bash
# 症状
# 错误：Permission denied

# 排查
docker exec my-app ls -la /app/logs   # 查看目录权限
docker exec my-app id                 # 查看当前用户

# 解决方案：
# - Dockerfile 中 chown 目录给正确用户
# - 宿主机目录权限与容器内用户 uid/gid 匹配
# - 挂载卷时指定 :z 或 :Z SELinux 标签（RHEL/CentOS）
```

**场景 5：OOMKilled**

```bash
# 症状
docker inspect my-app --format='{{.State.OOMKilled}}'
# 输出：true

# 排查
docker inspect my-app --format='{{.HostConfig.Memory}}'  # 容器内存限制
free -h                                                  # 宿主机内存
docker stats --no-stream my-app                          # 当前内存使用

# 解决方案：
# - 增大容器内存限制
# - 减小 JVM 堆内存（-Xmx）
# - 确保容器内存限制 > JVM 堆内存 + 非堆内存 + 系统开销
# - 规则：容器内存 ≥ -Xmx × 1.5
```

**场景 6：镜像拉取失败**

```bash
# 症状
# 错误：pull access denied / image not found

# 排查
docker pull my-app:latest              # 手动拉取测试

# 解决方案：
# - 检查镜像名和标签是否正确
# - 检查是否需要登录私有仓库：docker login registry.example.com
# - 检查网络连接和 DNS
# - 检查镜像是否存在于仓库中
```

**场景 7：容器启动后立即退出**

```bash
# 症状
docker ps -a
# STATUS: Exited (1) 5 seconds ago

# 排查
docker logs my-app                     # 查看退出日志
docker inspect my-app --format='{{.State.ExitCode}}'  # 退出码

# 常见原因：
# - ENTRYPOINT/CMD 命令错误
# - Java 应用启动异常
# - 配置文件缺失或格式错误
# - 环境变量未设置
```

**场景 8：Dockerfile 构建失败**

```bash
# 排查
docker build --no-cache --progress=plain .  # 详细输出构建过程

# 常见原因：
# - COPY 的文件路径不存在
# - RUN 命令返回非零退出码
# - 依赖下载失败（网络问题）
# - 磁盘空间不足
```

## 7.2 端口不通

### 7.2.1 端口映射检查

```bash
# 查看容器的端口映射
docker port my-app
# 输出：8080/tcp -> 0.0.0.0:8080

# 通过 inspect 查看详细端口映射
docker inspect my-app --format='{{json .NetworkSettings.Ports}}' | python -m json.tool

# 检查宿主机端口是否在监听
netstat -tlnp | grep 8080              # Linux
Get-NetTCPConnection -LocalPort 8080   # Windows

# 从容器内部验证端口是否在监听
docker exec my-app netstat -tlnp | grep 8080
# 或
docker exec my-app curl -s http://localhost:8080/actuator/health
```

### 7.2.2 网络模式排查

```bash
# 查看容器的网络模式
docker inspect my-app --format='{{.HostConfig.NetworkMode}}'
# 输出：bridge / host / none / container:xxx

# 各模式说明：
# bridge  - 默认模式，需要 -p 映射端口
# host    - 直接使用宿主机网络，无需 -p，端口直接可用
# none    - 无网络
# container:xxx - 与另一个容器共享网络命名空间

# host 模式常见误解：
# 使用 host 模式时，-p 参数无效（也无需指定）
# 应用直接监听宿主机端口
docker run -d --network host my-app:latest
# 应用在 8080 端口监听 → 直接通过宿主机 IP:8080 访问
```

### 7.2.3 防火墙/iptables 排查

```bash
# Linux 防火墙排查

# 查看 iptables 规则
sudo iptables -L -n -v
sudo iptables -t nat -L -n -v       # NAT 表（Docker 端口映射使用）

# 查看 Docker 添加的 iptables 规则
sudo iptables -L DOCKER -n -v
sudo iptables -t nat -L DOCKER -n -v

# 检查 firewalld 状态
sudo firewall-cmd --state
sudo firewall-cmd --list-all

# 开放端口（如果被防火墙拦截）
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload

# 检查 ufw 状态（Ubuntu）
sudo ufw status
sudo ufw allow 8080/tcp

# 检查 SELinux 状态（RHEL/CentOS）
getenforce
# 如果是 Enforcing，可能需要设置布尔值
sudo setsebool -P httpd_can_network_connect 1
```

### 7.2.4 同一网络内服务间通信排查

```bash
# 1. 确认两个容器在同一网络
docker network inspect my-app-network
# 查看 Containers 部分，确认两个服务都在其中

# 2. 从一个容器 ping 另一个容器（使用服务名）
docker exec my-app ping mysql
docker exec my-app ping redis

# 3. 测试端口连通性
docker exec my-app nc -zv mysql 3306
docker exec my-app nc -zv redis 6379

# 4. 测试 HTTP 连通性
docker exec my-app curl -v http://user-service:8080/actuator/health

# 5. DNS 解析测试
docker exec my-app nslookup mysql
docker exec my-app cat /etc/resolv.conf

# 6. 如果使用 Compose，确保服务名拼写正确
# Compose 服务名 = docker-compose.yml 中的 services 键名
# 而不是 container_name！
# Docker 内部 DNS 使用服务名解析，而非 container_name
```

### 7.2.5 完整排查命令序列

```bash
# 端口不通完整排查流程

# 步骤 1：确认容器运行状态
docker ps | grep my-app

# 步骤 2：确认端口映射
docker port my-app

# 步骤 3：从容器内验证服务监听
docker exec my-app curl -s http://localhost:8080/actuator/health

# 步骤 4：从宿主机验证端口
curl -s http://localhost:8080/actuator/health
curl -s http://127.0.0.1:8080/actuator/health
curl -s http://$(hostname -I | awk '{print $1}'):8080/actuator/health

# 步骤 5：检查网络模式
docker inspect my-app --format='{{.HostConfig.NetworkMode}}'

# 步骤 6：检查 iptables
sudo iptables -t nat -L DOCKER -n -v | grep 8080

# 步骤 7：检查防火墙
sudo firewall-cmd --list-ports
sudo ufw status

# 步骤 8：检查容器日志
docker logs --tail 50 my-app

# 步骤 9：检查健康检查状态
docker inspect my-app --format='{{.State.Health.Status}}'
```

## 7.3 OOM 排查

### 7.3.1 容器层 OOMKilled 识别

```bash
# 方法一：docker inspect 查看 OOMKilled 字段
docker inspect my-app --format='{{.State.OOMKilled}}'
# true 表示被 OOM Killer 杀死

# 方法二：docker inspect 查看完整状态
docker inspect my-app --format='{{json .State}}' | python -m json.tool
# 重点关注：
# "OOMKilled": true
# "ExitCode": 137

# 方法三：dmesg 查看内核日志
dmesg | grep -i "oom\|killed process"
# 输出类似：Killed process 12345 (java) total-vm:2048000kB, anon-rss:512000kB

# 方法四：docker events 监控
docker events --filter event=oom
```

### 7.3.2 JVM 层 OOM 排查

Java 的 `OutOfMemoryError` 有多种子类，含义不同：

```
┌──────────────────────────────────┬────────────────────────────────────────────┐
│ OOM 子类                          │ 含义与原因                                  │
├──────────────────────────────────┼────────────────────────────────────────────┤
│ Java heap space                  │ 堆内存不足，对象太多                         │
│                                  │ 解决：增大 -Xmx 或排查内存泄漏               │
├──────────────────────────────────┼────────────────────────────────────────────┤
│ Metaspace                        │ 元空间不足，加载的类太多                      │
│                                  │ 解决：增大 -XX:MaxMetaspaceSize             │
├──────────────────────────────────┼────────────────────────────────────────────┤
│ GC overhead limit exceeded       │ GC 花费了超过 98% 的时间回收了不到 2% 的内存   │
│                                  │ 解决：增大堆内存或排查内存泄漏                 │
├──────────────────────────────────┼────────────────────────────────────────────┤
│ Unable to create new native      │ 无法创建新线程，线程数太多                    │
│ thread                           │ 解决：减少线程数或增大进程限制                 │
├──────────────────────────────────┼────────────────────────────────────────────┤
│ Direct buffer memory             │ NIO 直接内存不足                            │
│                                  │ 解决：增大 -XX:MaxDirectMemorySize          │
├──────────────────────────────────┼────────────────────────────────────────────┤
│ Requested array size exceeds     │ 尝试创建超过 JVM 限制的数组                   │
│ VM limit                         │ 通常是代码 bug                              │
└──────────────────────────────────┴────────────────────────────────────────────┘
```

### 7.3.3 容器内存限制 vs JVM 堆内存配置不匹配

```bash
# 查看容器内存限制
docker inspect my-app --format='{{.HostConfig.Memory}}'
# 输出：536870912（即 512MB = 512 * 1024 * 1024）

# 查看 JVM 堆内存配置
docker exec my-app jcmd 1 VM.flags | grep -i heap
# 或
docker exec my-app java -XX:+PrintFlagsFinal -version | grep -i heapsize

# 查看实际内存使用
docker stats --no-stream my-app
```

**内存配置关系**：

```
容器内存限制（docker -m）
├── JVM 堆内存（-Xmx）         ← 最大值，不是实际占用
├── JVM 非堆内存
│   ├── Metaspace              ← 默认无上限！
│   ├── Code Cache
│   ├── Thread Stacks          ← 每线程约 1MB
│   ├── Direct Memory          ← NIO 使用
│   └── GC 内部数据
├── JVM 自身开销               ← 约 30-50MB
└── 容器系统开销               ← 约 10-20MB

规则：容器内存限制 ≥ -Xmx × 1.5（至少 1.3 倍）
示例：
  -Xmx512m → 容器内存 ≥ 768m（推荐 1G）
  -Xmx1g   → 容器内存 ≥ 1.5g（推荐 2G）
```

**常见配置错误**：

```yaml
# 错误：堆内存等于容器内存限制
services:
  app:
    deploy:
      resources:
        limits:
          memory: 512M           # 容器限制 512MB
    environment:
      JAVA_OPTS: "-Xmx512m"      # 堆内存 512MB
      # 非堆内存 + 系统开销无处安放 → OOMKilled！

# 正确：堆内存约容器内存的 60-70%
services:
  app:
    deploy:
      resources:
        limits:
          memory: 1G             # 容器限制 1G
    environment:
      JAVA_OPTS: "-Xmx640m"      # 堆内存 640MB（约 62%）
```

### 7.3.4 Heap Dump 分析流程

```bash
# 步骤 1：导出 Heap Dump
# 方式一：自动导出（推荐，提前配置）
# 在 JAVA_OPTS 中添加 -XX:+HeapDumpOnOutOfMemoryError

# 方式二：手动导出
docker exec my-app jmap -dump:format=b,file=/app/dumps/heapdump.hprof 1

# 方式三：使用 Arthas
docker exec my-app java -jar /opt/arthas/arthas-boot.jar
# Arthas 控制台中：heapdump /app/dumps/heapdump.hprof

# 步骤 2：将 Dump 文件从容器复制到宿主机
docker cp my-app:/app/dumps/heapdump.hprof ./heapdump.hprof

# 步骤 3：使用 MAT（Memory Analyzer Tool）分析
# 下载 MAT：https://eclipse.dev/mat/
# 打开 heapdump.hprof 文件
# 查看 Leak Suspects（泄漏嫌疑）报告
# 查看 Dominator Tree（支配树）
# 查看 Histogram（对象统计）

# 步骤 4：重点关注的指标
# - Retained Heap 最大的对象
# - 重复创建的对象类
# - 集合类中的对象数量
# - Thread Local 中的数据
# - Class Loader 泄漏
```

## 7.4 镜像构建慢

### 7.4.1 层缓存原理

```
Docker 镜像由多个只读层组成，每条 Dockerfile 指令产生一个层：

FROM eclipse-temurin:11-jre-alpine   ← 层 0（基础镜像层）
COPY pom.xml .                        ← 层 1
RUN mvn dependency:go-offline         ← 层 2（最耗时！）
COPY src ./src                        ← 层 3
RUN mvn package                       ← 层 4

缓存规则：
1. 如果某层的指令和上下文未变，使用缓存
2. 一旦某层缓存失效，后续所有层都重建
3. COPY 指令：只要文件内容变化，缓存就失效
4. 因此：把变化少的指令放在前面，变化多的放在后面

错误顺序（每次代码改动都重新下载依赖）：
COPY . .                              ← 代码变了，缓存失效
RUN mvn package                       ← 依赖也要重新下载！

正确顺序（代码变动不影响依赖缓存）：
COPY pom.xml .                        ← pom.xml 很少变
RUN mvn dependency:go-offline         ← 依赖下载被缓存
COPY src ./src                        ← 代码变动只影响从这里开始
RUN mvn package                       ← 只重新编译，不重新下载依赖
```

### 7.4.2 Dockerfile 优化

```dockerfile
# ---- 优化一：指令顺序优化 ----
# 把变化少的放前面

# 差
COPY . /app
RUN cd /app && mvn package

# 好
COPY pom.xml /app/pom.xml
RUN cd /app && mvn dependency:go-offline
COPY src /app/src
RUN cd /app && mvn package -DskipTests

# ---- 优化二：合并 RUN 指令 ----
# 每个 RUN 产生一个层，合并减少层数

# 差（3 个层）
RUN apk add --no-cache curl
RUN apk add --no-cache bash
RUN apk add --no-cache wget

# 好（1 个层）
RUN apk add --no-cache curl bash wget

# 清理在同一层完成
# 差（下载缓存在层中，即使后续删除）
RUN apk add --no-cache python3
RUN pip install flask
RUN apk del python3          # 层1已包含python3，删除不减小镜像大小

# 好（安装和清理在同一层）
RUN apk add --no-cache python3 && \
    pip install flask && \
    apk del python3

# ---- 优化三：.dockerignore ----
# .dockerignore 文件排除不需要的文件，减小构建上下文
# .dockerignore 示例：
.git
.gitignore
.idea
*.iml
target/
node_modules/
*.md
.env
docker-compose*.yml
logs/
```

### 7.4.3 多阶段构建优化

```dockerfile
# 多阶段构建：最终镜像只包含运行时必需的文件

# ---- 阶段 1：构建 ----
FROM maven:3.9-eclipse-temurin-11 AS builder
WORKDIR /build

# 利用缓存：先复制 pom.xml，下载
