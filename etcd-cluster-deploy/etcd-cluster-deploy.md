# etcd 三节点集群部署完整教程

> 环境：华为云内网 | 1 跳板机 + 3 节点 | CentOS/Ubuntu | etcd v3.5.13

## 环境规划

| 角色 | IP | 说明 |
|------|-----|------|
| 跳板机 | 可通三台内网 | 操作入口，下载/分发文件 |
| node1 | 192.168.0.168 | etcd 节点1 |
| node2 | 192.168.0.145 | etcd 节点2 |
| node3 | 192.168.0.79 | etcd 节点3 |

三台都是内网机器，跳板机可以 SSH 到三台。

---

## 第一步：跳板机上下载 etcd

```bash
# 下载最新稳定版（amd64）
cd /tmp
curl -L https://github.com/etcd-io/etcd/releases/download/v3.5.13/etcd-v3.5.13-linux-amd64.tar.gz -o etcd-v3.5.13-linux-amd64.tar.gz

# 验证下载完整
ls -lh etcd-v3.5.13-linux-amd64.tar.gz
# 应该看到约 23MB 的文件

# 解压看看里面有什么
tar -tzf etcd-v3.5.13-linux-amd64.tar.gz | head -20
# 应该能看到 etcd、etcdctl 两个二进制
```

**验证点**：文件大小不是 0，解压列表里有 `etcd` 和 `etcdctl`。

> ⚠️ 如果跳板机没法访问 GitHub，就在本地电脑下载后 scp 到跳板机：
> ```bash
> scp etcd-v3.5.13-linux-amd64.tar.gz root@跳板机IP:/tmp/
> ```

---

## 第二步：从跳板机分发到三台主机

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> 正在传输到 $ip ..."
  scp /tmp/etcd-v3.5.13-linux-amd64.tar.gz root@$ip:/opt/
done
```

**验证点**：

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> $ip:"
  ssh root@$ip "ls -lh /opt/etcd-v3.5.13-linux-amd64.tar.gz"
done
# 三台都应该显示文件存在且大小一致
```

---

## 第三步：三台主机上解压 & 安装

在跳板机上远程执行（不用一台台登）：

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> 正在安装 $ip ..."
  ssh root@$ip bash -s <<'SCRIPT'
    # 1. 解压
    cd /opt
    tar -xzf etcd-v3.5.13-linux-amd64.tar.gz

    # 2. 重命名为统一目录名
    mv -f etcd-v3.5.13-linux-amd64 etcd

    # 3. 创建软链接，让 etcd 命令全局可用
    ln -sf /opt/etcd/etcd /usr/local/bin/etcd
    ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl

    # 4. 创建数据目录
    mkdir -p /opt/etcd/data

    echo "安装完成"
SCRIPT
done
```

### 如果提示命令不存在怎么办？

这是因为 `/opt/etcd/` 里的二进制没在 PATH 里。上面已经用 `ln -sf` 链接到了 `/usr/local/bin/`。

如果手动操作时遇到这个问题：

```bash
# 方法1：用绝对路径跑（临时）
/opt/etcd/etcd --version

# 方法2：创建软链接（推荐，永久生效）
ln -sf /opt/etcd/etcd /usr/local/bin/etcd
ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl

# 方法3：把 /opt/etcd 加到 PATH（不推荐，侵入性大）
echo 'export PATH=$PATH:/opt/etcd' >> /etc/profile
source /etc/profile
```

**验证安装**：

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> $ip:"
  ssh root@$ip "etcd --version && etcdctl version"
done
# 三台都应该输出版本号
```

> 💡 **为什么 `etcd` 和 `etcdctl` 查版本的方式不一样？**
> - `etcd` 是服务端，查版本用 `etcd --version`（两个横杠）
> - `etcdctl` 是客户端，查版本用 `etcdctl version`（子命令）
> - 两个是不同的二进制，设计上就不统一，不是 bug

---

## 第四步：创建 etcd 专用用户

生产环境不建议用 root 跑 etcd，创建专用用户更安全。

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> 创建用户 $ip ..."
  ssh root@$ip bash -s <<'SCRIPT'
    # 创建系统用户（不能登录，没有 home 目录）
    useradd -r -s /sbin/nologin -M etcd

    # 把 etcd 目录的归属给这个用户
    chown -R etcd:etcd /opt/etcd/

    echo "用户创建完成"
SCRIPT
done
```

### 验证是否创建成功

```bash
# 检查用户是否存在
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> $ip:"
  ssh root@$ip "id etcd"
done
# 应该输出类似：uid=XXX(etcd) gid=XXX(etcd) 组=XXX(etcd)

# 检查目录权限
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> $ip:"
  ssh root@$ip "ls -ld /opt/etcd/ /opt/etcd/data/"
done
# 应该显示归属 etcd:etcd
```

> **`useradd` 参数解释**：
> - `-r` = 系统用户（UID < 1000，不会出现在登录界面）
> - `-s /sbin/nologin` = 禁止这个用户登录 shell（安全）
> - `-M` = 不创建 home 目录（不需要）

---

## 第五步：写配置文件

这是最关键的一步。三台的配置文件**大部分相同，少量不同**。

### 配置文件逐项解释

```yaml
# ==============================
# 节点标识（每台不同！）
# ==============================
name: "node1"
# 这个节点在集群里的名字。三台分别叫 node1、node2、node3。
# 不能重复，集群内部靠这个区分谁是谁。

# ==============================
# 数据存储
# ==============================
data-dir: "/opt/etcd/data"
# etcd 的所有数据存这里（键值对、WAL 日志、快照）。
# 这个目录必须存在，且 etcd 用户有读写权限。

# ==============================
# 客户端通信（应用连接 etcd 用的端口）
# ==============================
listen-client-urls: "http://192.168.0.168:2379,http://127.0.0.1:2379"
# etcd 在哪些地址上监听客户端请求。
# 2379 是客户端端口（应用、etcdctl 连这个）。
# 写 127.0.0.1 是让本机的 etcdctl 也能连。
# ⚠️ 每台写自己的 IP！

advertise-client-urls: "http://192.168.0.168:2379"
# 告诉其他节点和客户端"你可以通过这个地址连我"。
# 集群其他节点会用这个 URL 来跟你通信。
# ⚠️ 必须写内网 IP，不能写 127.0.0.1（否则其他节点连不上）。
# ⚠️ 每台写自己的 IP！

# ==============================
# 集群内部通信（节点之间互相同步数据用的端口）
# ==============================
listen-peer-urls: "http://192.168.0.168:2380"
# 在哪个地址上监听其他 etcd 节点的连接。
# 2380 是 peer 端口（节点之间用的）。
# ⚠️ 每台写自己的 IP！

initial-advertise-peer-urls: "http://192.168.0.168:2380"
# 告诉其他节点"你可以通过这个地址跟我同步数据"。
# ⚠️ 每台写自己的 IP！

# ==============================
# 集群拓扑（三台一模一样！）
# ==============================
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
# 集群里有哪些节点，格式：name=peerURL,name=peerURL,...
# 三台必须写完全一样的内容。

initial-cluster-token: "etcd-cluster-1"
# 集群的"身份证号"。同一个集群的节点 token 必须一样。
# 用来防止不同集群的节点意外混在一起。
# 随便取个名就行，三台保持一致。

initial-cluster-state: "new"
# "new" = 全新集群（第一次部署时用）
# "existing" = 往已有集群加节点时用
# 三台第一次部署都写 "new"。
```

### 三台的实际配置

**node1 (192.168.0.168)** — `/opt/etcd/etcd.yml`：

```yaml
name: "node1"
data-dir: "/opt/etcd/data"
listen-client-urls: "http://192.168.0.168:2379,http://127.0.0.1:2379"
advertise-client-urls: "http://192.168.0.168:2379"
listen-peer-urls: "http://192.168.0.168:2380"
initial-advertise-peer-urls: "http://192.168.0.168:2380"
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
initial-cluster-token: "etcd-cluster-1"
initial-cluster-state: "new"
```

**node2 (192.168.0.145)** — `/opt/etcd/etcd.yml`：

```yaml
name: "node2"
data-dir: "/opt/etcd/data"
listen-client-urls: "http://192.168.0.145:2379,http://127.0.0.1:2379"
advertise-client-urls: "http://192.168.0.145:2379"
listen-peer-urls: "http://192.168.0.145:2380"
initial-advertise-peer-urls: "http://192.168.0.145:2380"
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
initial-cluster-token: "etcd-cluster-1"
initial-cluster-state: "new"
```

**node3 (192.168.0.79)** — `/opt/etcd/etcd.yml`：

```yaml
name: "node3"
data-dir: "/opt/etcd/data"
listen-client-urls: "http://192.168.0.79:2379,http://127.0.0.1:2379"
advertise-client-urls: "http://192.168.0.79:2379"
listen-peer-urls: "http://192.168.0.79:2380"
initial-advertise-peer-urls: "http://192.168.0.79:2380"
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
initial-cluster-token: "etcd-cluster-1"
initial-cluster-state: "new"
```

### 总结

只有 5 个地方每台不同：

- `name`
- `listen-client-urls`
- `advertise-client-urls`
- `listen-peer-urls`
- `initial-advertise-peer-urls`

其余全部复制粘贴。

### 从跳板机批量写入

```bash
# node1
ssh root@192.168.0.168 "cat > /opt/etcd/etcd.yml" << 'YAML'
name: "node1"
data-dir: "/opt/etcd/data"
listen-client-urls: "http://192.168.0.168:2379,http://127.0.0.1:2379"
advertise-client-urls: "http://192.168.0.168:2379"
listen-peer-urls: "http://192.168.0.168:2380"
initial-advertise-peer-urls: "http://192.168.0.168:2380"
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
initial-cluster-token: "etcd-cluster-1"
initial-cluster-state: "new"
YAML
ssh root@192.168.0.168 "chown etcd:etcd /opt/etcd/etcd.yml"

# node2
ssh root@192.168.0.145 "cat > /opt/etcd/etcd.yml" << 'YAML'
name: "node2"
data-dir: "/opt/etcd/data"
listen-client-urls: "http://192.168.0.145:2379,http://127.0.0.1:2379"
advertise-client-urls: "http://192.168.0.145:2379"
listen-peer-urls: "http://192.168.0.145:2380"
initial-advertise-peer-urls: "http://192.168.0.145:2380"
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
initial-cluster-token: "etcd-cluster-1"
initial-cluster-state: "new"
YAML
ssh root@192.168.0.145 "chown etcd:etcd /opt/etcd/etcd.yml"

# node3
ssh root@192.168.0.79 "cat > /opt/etcd/etcd.yml" << 'YAML'
name: "node3"
data-dir: "/opt/etcd/data"
listen-client-urls: "http://192.168.0.79:2379,http://127.0.0.1:2379"
advertise-client-urls: "http://192.168.0.79:2379"
listen-peer-urls: "http://192.168.0.79:2380"
initial-advertise-peer-urls: "http://192.168.0.79:2380"
initial-cluster: "node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380"
initial-cluster-token: "etcd-cluster-1"
initial-cluster-state: "new"
YAML
ssh root@192.168.0.79 "chown etcd:etcd /opt/etcd/etcd.yml"
```

---

## 第六步：创建 systemd 服务

`/etc/systemd/system/etcd.service`（三台内容**完全一样**）：

```ini
[Unit]
Description=etcd key-value store
Documentation=https://etcd.io/docs/
After=network.target

[Service]
Type=simple
User=etcd
Group=etcd
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=always
RestartSec=5s
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 每个字段解释

| 字段 | 含义 |
|------|------|
| `Type=simple` | 最简单的服务类型，ExecStart 启动后就算服务就绪。**不要用 `notify`**，notify 需要 etcd 主动发 sd_notify 信号，配置不好会导致启动失败 |
| `User=etcd` | 用 etcd 用户身份运行（不用 root，更安全） |
| `Group=etcd` | 用 etcd 用户组 |
| `ExecStart` | 启动命令，指向 etcd 二进制和配置文件 |
| `Restart=always` | 进程挂了自动重启 |
| `RestartSec=5s` | 挂了之后等 5 秒再重启（防止快速循环崩溃） |
| `LimitNOFILE=65536` | 文件描述符上限，etcd 需要大量连接 |
| `StandardOutput=journal` | 标准输出写到 systemd 日志 |
| `StandardError=journal` | 标准错误写到 systemd 日志 |
| `After=network.target` | 等网络就绪后再启动 |
| `WantedBy=multi-user.target` | 开机自启的目标 |

### 为什么不用 Type=notify？

`Type=notify` 要求进程主动调用 `sd_notify()` 告诉 systemd "我准备好了"。etcd 虽然支持这个机制，但在配置不完善时（比如内网无 TLS、配置文件有误），etcd 可能来不及发通知就崩了，systemd 会认为启动超时。用 `Type=simple` 更稳，不会有这个问题。

### 为什么需要 systemd？

直接前台跑 `/opt/etcd/etcd --config-file /opt/etcd/etcd.yml` 有几个致命问题：

1. **SSH 断了进程就死了** — 终端关了 etcd 就停了
2. **机器重启不会自动拉起** — 得手动再启动
3. **没有统一的管理方式** — 没法用 `systemctl start/stop/restart/status`
4. **日志散落** — 没有统一收集，排查问题靠翻 nohup.out
5. **崩溃不会自动重启** — etcd 挂了就是挂了

systemd 解决了这四个核心问题：**开机自启、崩溃重启、统一管理、日志收集**。

### 从跳板机批量写入

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> 写入 service 到 $ip ..."
  ssh root@$ip "cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd key-value store
Documentation=https://etcd.io/docs/
After=network.target

[Service]
Type=simple
User=etcd
Group=etcd
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=always
RestartSec=5s
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload"
done
```

---

## 第七步：启动集群

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> 启动 $ip ..."
  ssh root@$ip "systemctl enable --now etcd"
done
```

### 验证服务状态

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> $ip:"
  ssh root@$ip "systemctl status etcd --no-pager -l | head -15"
done
# 应该看到 active (running)
```

### 如果启动失败，排错三板斧

```bash
# 1. 看服务状态
systemctl status etcd

# 2. 看日志（最常用）
journalctl -u etcd -n 50 --no-pager

# 3. 前台跑看标准错误（先停掉 systemd）
systemctl stop etcd
/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
# 直接看终端输出的报错信息
```

常见启动失败原因：

| 现象 | 原因 | 解决 |
|------|------|------|
| exit-code, no useful log | Type=notify 但 etcd 没发通知 | 改 `Type=simple` |
| https 相关报错 | 配置文件用了 https 但没有证书 | 改成 `http://` |
| permission denied | 数据目录权限不对 | `chown -R etcd:etcd /opt/etcd/` |
| address already in use | 2379/2380 端口被占用 | `ss -tlnp | grep etcd` 查看 |
| data dir corrupted | 之前的数据残留 | 清空 `rm -rf /opt/etcd/data/*` 后重启 |

---

## 第八步：验证集群

### 8.1 查看集群成员

```bash
etcdctl --endpoints=http://192.168.0.168:2379 member list
```

输出类似：

```
xxxxxxxxx: name=node1 peerURLs=http://192.168.0.168:2380 clientURLs=http://192.168.0.168:2379
yyyyyyyyy: name=node2 peerURLs=http://192.168.0.145:2380 clientURLs=http://192.168.0.145:2379
zzzzzzzzz: name=node3 peerURLs=http://192.168.0.79:2380 clientURLs=http://192.168.0.79:2379
```

应该看到 3 个成员，状态都是 started。

### 8.2 查看集群健康

```bash
etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint health
```

输出：

```
http://192.168.0.168:2379 is healthy: successfully committed proposal
http://192.168.0.145:2379 is healthy: successfully committed proposal
http://192.168.0.79:2379 is healthy: successfully committed proposal
```

三台都是 healthy 就没问题。

### 8.3 读写测试

```bash
# 写入（从任意一台）
etcdctl --endpoints=http://192.168.0.168:2379 put /test/hello "etcd集群运行正常"
# 输出 OK

# 从另一台读（验证数据同步）
etcdctl --endpoints=http://192.168.0.145:2379 get /test/hello
# 输出 etcd集群运行正常

# 从第三台读
etcdctl --endpoints=http://192.168.0.79:2379 get /test/hello
# 输出 etcd集群运行正常

# 清理测试数据
etcdctl --endpoints=http://192.168.0.168:2379 del /test/hello
```

### 8.4 查看集群状态详情

```bash
etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint status --write-out=table
```

输出一个表格，包含每个节点的：

- ID
- 版本号
- 数据库大小
- 是否 leader（只有一个是 leader）
- follower 数量

### 8.5 查看端口监听

```bash
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  echo ">>> $ip:"
  ssh root@$ip "ss -tlnp | grep etcd"
done
```

每台应该看到：

```
LISTEN  0  128  192.168.0.168:2379  0.0.0.0:*  users:(("etcd",...))
LISTEN  0  128  127.0.0.1:2379     0.0.0.0:*  users:(("etcd",...))
LISTEN  0  128  192.168.0.168:2380  0.0.0.0:*  users:(("etcd",...))
```

> **为什么有 127.0.0.1:2379？** 这是正常的。etcd 同时监听本地回环和内网 IP，方便本机的 etcdctl 直接连 `http://127.0.0.1:2379`。

---

## 端口总结

| 端口 | 谁在用 | 作用 |
|------|--------|------|
| **2379** | 客户端端口 | `etcdctl`、你的应用程序连这个端口读写数据 |
| **2380** | 集群端口 | etcd 节点之间互相通信、数据同步、选举 leader |

类比：2379 是"前台"，客户端来这里办事；2380 是"内部电话"，节点之间互相同步。

---

## 关于 HTTPS / 证书

### 当前方案：内网不加密（http）

上面的方案全程用的 `http://`，适用于：

- 内网环境，节点之间互信
- 开发/测试环境
- 不对外暴露的网络

**不需要任何证书**，不需要做任何证书相关的操作。配置文件里所有 URL 都写 `http://` 就行。

### 什么时候需要 HTTPS？

- etcd 暴露在公网
- 多租户环境，防止数据被窃听
- 公司安全规范要求所有服务间通信加密
- Kubernetes 生产环境（很多 K8s 部署工具会强制要求 TLS）

### 如果以后要加 TLS，需要什么证书？

需要一套证书体系（通常用 `cfssl` 或 `openssl` 生成）：

```
ca.pem           ← 根证书（CA），用来签发其他证书
ca-key.pem       ← CA 私钥

server.pem       ← etcd 服务端证书（三台共用或各一份）
server-key.pem   ← 服务端私钥

peer.pem         ← 节点间通信证书（三台共用或各一份）
peer-key.pem     ← 节点间私钥

client.pem       ← 客户端证书（etcdctl 用）
client-key.pem   ← 客户端私钥
```

TLS 模式下的配置文件示例：

```yaml
listen-client-urls: "https://192.168.0.168:2379"
advertise-client-urls: "https://192.168.0.168:2379"
listen-peer-urls: "https://192.168.0.168:2380"
initial-advertise-peer-urls: "https://192.168.0.168:2380"

client-transport-security:
  cert-file: "/opt/etcd/ssl/server.pem"
  key-file: "/opt/etcd/ssl/server-key.pem"
  client-cert-auth: true
  trusted-ca-file: "/opt/etcd/ssl/ca.pem"

peer-transport-security:
  cert-file: "/opt/etcd/ssl/peer.pem"
  key-file: "/opt/etcd/ssl/peer-key.pem"
  client-cert-auth: true
  trusted-ca-file: "/opt/etcd/ssl/ca.pem"
```

### 验证证书是否配置成功

```bash
etcdctl --endpoints=https://192.168.0.168:2379 \
  --cacert=/opt/etcd/ssl/ca.pem \
  --cert=/opt/etcd/ssl/client.pem \
  --key=/opt/etcd/ssl/client-key.pem \
  endpoint health

# 输出 healthy = 证书配置成功
# 如果报证书错误，检查证书里的 SAN（Subject Alternative Name）是否包含所有节点 IP
```

> **结论：内网场景不需要折腾证书，全程 http 就完事了。**

---

## 完整流程速查（从跳板机一条龙）

```bash
# ===== 1. 下载 =====
cd /tmp
curl -L https://github.com/etcd-io/etcd/releases/download/v3.5.13/etcd-v3.5.13-linux-amd64.tar.gz -o etcd.tar.gz

# ===== 2. 分发到三台 =====
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  scp etcd.tar.gz root@$ip:/opt/
done

# ===== 3. 三台解压 + 安装 + 建用户 =====
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  ssh root@$ip bash -s <<'SCRIPT'
    cd /opt && tar -xzf etcd.tar.gz && mv -f etcd-v3.5.13-linux-amd64 etcd
    ln -sf /opt/etcd/etcd /usr/local/bin/etcd
    ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl
    mkdir -p /opt/etcd/data
    useradd -r -s /sbin/nologin -M etcd 2>/dev/null
    chown -R etcd:etcd /opt/etcd/
SCRIPT
done

# ===== 4. 写配置文件（每台不同，见第五步）=====

# ===== 5. 写 systemd 服务（三台一样）+ 启动 =====
for ip in 192.168.0.168 192.168.0.145 192.168.0.79; do
  ssh root@$ip "cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd key-value store
After=network.target
[Service]
Type=simple
User=etcd
Group=etcd
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=always
RestartSec=5s
LimitNOFILE=65536
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now etcd"
done

# ===== 6. 验证 =====
etcdctl --endpoints=http://192.168.0.168:2379 member list
etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint health
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `etcd: command not found` | 二进制不在 PATH | `ln -sf /opt/etcd/etcd /usr/local/bin/etcd` |
| `systemctl start etcd` 报 exit-code | Type=notify 或 https 配置 | 改 `Type=simple`，确认配置文件 URL 是 `http://` |
| journalctl 没有有用信息 | etcd 秒退来不及输出 | 前台跑 `/opt/etcd/etcd --config-file` 看终端输出 |
| permission denied | etcd 用户没有数据目录权限 | `chown -R etcd:etcd /opt/etcd/` |
| 三台端口都看到 2379 | 正常现象 | 每台都监听 2379（客户端）和 2380（集群） |
| 127.0.0.1:2379 出现 | 正常现象 | etcd 同时监听本地回环，方便本机 etcdctl 连接 |
| 集群起不来，一直报 leader election | 三台 initial-cluster 不一致 | 检查三台的 `initial-cluster` 值是否一模一样 |
