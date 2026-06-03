# etcd 三节点集群部署指南

> 适用环境：华为云 ECS 内网（EulerOS / openEuler）
> 节点 IP：192.168.0.168（node1）、192.168.0.145（node2）、192.168.0.79（node3）
> 证书来源：华为云签发（chain.pem, server.pem, server.key）

---

## 目录

- [一、环境信息](#一环境信息)
- [二、前置检查](#二前置检查)
- [三、方案 A：HTTP 模式（无 TLS）](#三方案-ahttp-模式无-tls)
- [四、方案 B：HTTPS 模式（TLS 加密）](#四方案-bhttps-模式tls-加密)
- [五、验证集群](#五验证集群)
- [六、重启与启动顺序](#六重启与启动顺序)
- [七、为什么要删除 data 目录](#七为什么要删除-data-目录)
- [八、排错手册（实战踩坑记录）](#八排错手册实战踩坑记录)
- [附录A：配置字段速查表](#附录a配置字段速查表)
- [附录B：yml 配置文件踩坑指南](#附录byml-配置文件踩坑指南)

---

## 一、环境信息

| 项 | 值 |
|---|---|
| etcd 二进制 | `/opt/etcd/etcd` |
| etcdctl | `/opt/etcd/etcdctl` |
| 数据目录 | `/opt/etcd/data`（权限必须 700） |
| 证书目录 | `/opt/etcd/ssl/` |
| 证书文件 | `chain.pem`（CA）、`server.pem`（服务端证书）、`server.key`（私钥） |
| 配置文件 | `/opt/etcd/etcd.yml` |
| 服务文件 | `/etc/systemd/system/etcd.service` |

### 证书说明

华为云签发的证书**不需要做 base64 转换，不需要做 PKCS8 转换**。etcd 直接使用原始 PEM 格式。教程里的 base64/PKCS8 转换是给 Java/Nacos 用的，和 etcd 无关。

---

## 二、前置检查

```bash
# 确认 etcd 二进制
/opt/etcd/etcd --version

# 链接到 PATH
ln -sf /opt/etcd/etcd /usr/local/bin/etcd
ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl

# 确认架构匹配
file /opt/etcd/etcd
uname -m

# 确认端口没被占
ss -tlnp | grep -E '2379|2380'

# 杀掉旧进程
pkill etcd 2>/dev/null

# 端口互通测试（三台都跑，所有结果必须 OK）
bash -c 'echo > /dev/tcp/192.168.0.168/2379 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.168/2380 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.145/2379 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.79/2379 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.79/2380 && echo OK || echo FAIL'
```

### 证书检查（HTTPS 模式必做）

```bash
# SAN 包含哪些 IP（必须包含本机节点 IP）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# 证书是否过期
openssl x509 -in /opt/etcd/ssl/server.pem -noout -dates

# 证书和私钥是否匹配（两条 md5 必须一样）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -modulus | md5sum
openssl rsa -in /opt/etcd/ssl/server.key -noout -modulus | md5sum

# CA 是否信任证书
openssl verify -CAfile /opt/etcd/ssl/chain.pem /opt/etcd/ssl/server.pem

# 确认证书文件存在
ls -la /opt/etcd/ssl/
```

**重要**：华为云签发的证书 SAN 中通常不包含 `127.0.0.1`，所以配置中 `listen-client-urls` 不能加 `https://127.0.0.1:2379`，本地访问用实际 IP。

---

## 三、方案 A：HTTP 模式（无 TLS）

> 内网环境推荐先用此方案跑通集群，确认 etcd 本身没问题，再切 HTTPS。

### systemd 服务文件（三台一样）

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
```

### node1 `/opt/etcd/etcd.yml`

```yaml
name: 'node1'
data-dir: /opt/etcd/data
listen-client-urls: 'http://192.168.0.168:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://192.168.0.168:2380'
advertise-client-urls: 'http://192.168.0.168:2379'
initial-advertise-peer-urls: 'http://192.168.0.168:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
```

### node2 `/opt/etcd/etcd.yml`

```yaml
name: 'node2'
data-dir: /opt/etcd/data
listen-client-urls: 'http://192.168.0.145:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://192.168.0.145:2380'
advertise-client-urls: 'http://192.168.0.145:2379'
initial-advertise-peer-urls: 'http://192.168.0.145:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
```

### node3 `/opt/etcd/etcd.yml`

```yaml
name: 'node3'
data-dir: /opt/etcd/data
listen-client-urls: 'http://192.168.0.79:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://192.168.0.79:2380'
advertise-client-urls: 'http://192.168.0.79:2379'
initial-advertise-peer-urls: 'http://192.168.0.79:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
```

### 启动（三台都执行）

```bash
# 清理旧数据
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data

# 写入 yml 后，确保没有 CRLF
perl -i -pe 's/\r$//' /opt/etcd/etcd.yml

# 启动
systemctl daemon-reload
systemctl enable etcd
systemctl start etcd
systemctl status etcd
```

---

## 四、方案 B：HTTPS 模式（TLS 加密）

> **前提**：先用方案 A 跑通集群，再切 HTTPS。

### systemd 服务文件（三台一样）

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
```

### node1 `/opt/etcd/etcd.yml`

> **注意**：`listen-client-urls` 不含 `127.0.0.1`，因为华为云签发的证书 SAN 中没有 127.0.0.1。本地访问用实际 IP `https://192.168.0.168:2379`。

```yaml
name: 'node1'
data-dir: /opt/etcd/data
listen-client-urls: 'https://192.168.0.168:2379'
listen-peer-urls: 'https://192.168.0.168:2380'
advertise-client-urls: 'https://192.168.0.168:2379'
initial-advertise-peer-urls: 'https://192.168.0.168:2380'
initial-cluster: 'node1=https://192.168.0.168:2380,node2=https://192.168.0.145:2380,node3=https://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
client-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: true
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
peer-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: true
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
```

### node2 `/opt/etcd/etcd.yml`

```yaml
name: 'node2'
data-dir: /opt/etcd/data
listen-client-urls: 'https://192.168.0.145:2379'
listen-peer-urls: 'https://192.168.0.145:2380'
advertise-client-urls: 'https://192.168.0.145:2379'
initial-advertise-peer-urls: 'https://192.168.0.145:2380'
initial-cluster: 'node1=https://192.168.0.168:2380,node2=https://192.168.0.145:2380,node3=https://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
client-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: true
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
peer-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: true
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
```

### node3 `/opt/etcd/etcd.yml`

```yaml
name: 'node3'
data-dir: /opt/etcd/data
listen-client-urls: 'https://192.168.0.79:2379'
listen-peer-urls: 'https://192.168.0.79:2380'
advertise-client-urls: 'https://192.168.0.79:2379'
initial-advertise-peer-urls: 'https://192.168.0.79:2380'
initial-cluster: 'node1=https://192.168.0.168:2380,node2=https://192.168.0.145:2380,node3=https://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
client-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: true
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
peer-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: true
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
```

### 启动（三台都执行）

```bash
# 清理旧数据（如果从 HTTP 切过来必须清）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data

# 确保 yml 没有 CRLF
perl -i -pe 's/\r$//' /opt/etcd/etcd.yml

# 启动
systemctl daemon-reload
systemctl enable etcd
systemctl start etcd
systemctl status etcd
```

### 关于 `client-cert-auth` 的取舍

| 设置 | 含义 | 适用场景 |
|------|------|----------|
| `client-cert-auth: true` | 客户端必须提供证书 | etcd 集群内部通信建议开 |
| `client-cert-auth: false` | 客户端不需要证书 | **Nacos 等应用不带客户端证书时必须关掉** |

如果 Nacos 连 etcd 报证书错误，把 `client-transport-security` 段的 `client-cert-auth: true` 改为 `client-cert-auth: false`，**`peer-transport-security` 段保持 `true` 不变**，然后重启 etcd。

---

## 五、验证集群

### HTTP 模式

```bash
ETCDCTL_API=3 etcdctl \
  --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 \
  member list

ETCDCTL_API=3 etcdctl \
  --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 \
  endpoint health

ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379 put testkey hello
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.145:2379 get testkey
```

### HTTPS 模式

```bash
ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  member list

ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  endpoint health

ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.168:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  put testkey hello

ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.145:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  get testkey
```

---

## 六、重启与启动顺序

### 正常重启（不停机维护、配置变更后重启）

**没有严格的启动顺序要求。** etcd 集群使用 Raft 协议，只要最终多数节点（2/3）恢复在线，集群就能正常工作。

但建议按以下顺序操作：

1. **先停后启，间隔 30 秒以上**
2. 一次只停一台，等该节点恢复后再停下一台
3. 每台重启后检查集群健康：
   ```bash
   # HTTP
   ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint health

   # HTTPS
   ETCDCTL_API=3 etcdctl \
     --endpoints=https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379 \
     --cacert=/opt/etcd/ssl/chain.pem --cert=/opt/etcd/ssl/server.pem --key=/opt/etcd/ssl/server.key \
     endpoint health
   ```

### 单节点重启步骤

```bash
# 在要重启的节点上
systemctl restart etcd

# 等待 10 秒
sleep 10

# 检查状态
systemctl status etcd

# 检查集群健康（在任意节点执行）
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint health
```

### 三节点全部重启（如系统维护）

1. **依次停机**：先停 node1，确认停了；再停 node2；最后停 node3
2. **依次启动**：先启 node1，等 10 秒确认启动成功；再启 node2，等 10 秒；最后启 node3

```bash
# node1 上
systemctl start etcd
sleep 10
systemctl status etcd

# 确认 node1 正常后，在 node2 上
systemctl start etcd
sleep 10
systemctl status etcd

# 确认 node2 正常后，在 node3 上
systemctl start etcd
sleep 10
systemctl status etcd
```

### 关键规则

| 场景 | 规则 |
|------|------|
| 正常重启（配置不变） | 不需要清 data-dir，直接 `systemctl restart etcd` |
| 修改配置后重启 | 修改 yml/service 文件 → `systemctl daemon-reload` → `systemctl restart etcd` |
| 从 HTTP 切换到 HTTPS | **必须清 data-dir**，三台都清，三台同时启 |
| 修改 initial-cluster（加减节点） | **必须清 data-dir** 或使用 member add/remove |
| 删除 data-dir 后启动 | 配置中必须是 `initial-cluster-state: new` |
| 整个集群宕机恢复 | 不需要清 data-dir，依次启动即可，etcd 会从 WAL 日志恢复 |

---

## 七、为什么要删除 data 目录

### 什么情况需要删除？

| 场景 | 需要删除吗 | 说明 |
|------|-----------|------|
| 首次部署 | **是** | data-dir 必须为空，`initial-cluster-state: new` 才能成功 |
| 从 HTTP 切换到 HTTPS | **是** | 通信方式变了，旧数据不兼容，必须重建集群 |
| 从 HTTPS 切换到 HTTP | **是** | 同上 |
| 修改了 initial-cluster 成员 | **是** | 集群成员变化，旧数据不一致 |
| `has already been bootstrapped` 报错 | **是** | data-dir 有残留数据，和 `new` 状态冲突 |
| 正常重启（配置不变） | **否** | 直接 `systemctl restart etcd` |
| 修改 yml 中非集群相关配置 | **否** | 如改日志级别、改 data-dir 路径等，不需要清数据 |
| 整个集群宕机恢复 | **否** | etcd 从 WAL 日志恢复数据，不要删 |
| 单节点宕机恢复 | **否** | 该节点重启后会从 leader 同步数据 |

### 为什么 `initial-cluster-state: new` 要求空 data-dir？

etcd 在首次启动（`new`）时会：
1. 检查 data-dir 是否为空
2. 如果为空，初始化一个新的 Raft 集群
3. 如果不为空，说明该节点已经加入过某个集群，拒绝用 `new` 模式启动（防止误操作覆盖数据）

这就是为什么删除 data-dir 是安全的——它只是让 etcd 回到"首次启动"状态。

### 删除 data-dir 的正确步骤

```bash
systemctl stop etcd           # 必须先停
rm -rf /opt/etcd/data         # 删除数据
mkdir -p /opt/etcd/data       # 重建目录
chmod 700 /opt/etcd/data      # 设置权限（etcd 要求 700）
systemctl start etcd           # 启动
```

> **警告**：删除 data-dir 会丢失所有 etcd 数据（包括 Nacos 注册的服务信息等）。如果有重要数据，请先用 etcdctl snapshot save 备份：
> ```bash
> ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379 snapshot save /tmp/etcd-backup.db
> ```

### 不想删 data-dir 时的替代方案

1. 如果集群还活着，用 member remove + `initial-cluster-state: existing` 加入
2. 如果是单节点数据损坏，从其他节点同步恢复（需多数节点存活）

---

## 八、排错手册（实战踩坑记录）

### 问题 1：yml 配置文件格式错误导致静默退出

**现象**：`systemctl start etcd` 报 `exit-code`，journalctl 输出 `yaml did not find expected key`，前台运行也没输出。

**原因**：yml 文件有格式问题（缩进错误、Tab、引号格式、CRLF 等）。etcd 读取 yml 出错后直接退出，有时甚至不报错。

**解决**：

1. 确保 yml 用空格缩进（不用 Tab）
2. 清理 CRLF：`perl -i -pe 's/\r$//' /opt/etcd/etcd.yml`
3. 验证格式：`python3 -c "import yaml; yaml.safe_load(open('/opt/etcd/etcd.yml'))"`
4. 如果还是不行，用命令行参数代替 yml（见附录B）

### 问题 2：`has already been bootstrapped`

**现象**：日志报 `member xxx has already been bootstrapped`

**原因**：data-dir 有旧数据，但 `initial-cluster-state` 设为 `new`。

**解决**：

```bash
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data
systemctl start etcd
```

> **重要**：如果只清了一台的数据，其他节点还保留旧集群数据，会报错。要么三台都清，要么用 member remove 把旧节点移除后用 `existing` 加入。

### 问题 3：data 目录权限警告

**现象**：日志报 `directory /opt/etcd/data exist, but the permission is drwxr-xr-x`

**解决**：

```bash
chmod 700 /opt/etcd/data
systemctl restart etcd
```

如果还报 `permission denied`，检查属主：

```bash
chown -R root:root /opt/etcd/data
chmod 700 /opt/etcd/data
```

### 问题 4：单节点清数据后无法加入集群

**现象**：node1 删了 data-dir 重建，但 node2/node3 还保留旧数据，node1 启动报错。

**解决**（二选一）：

- **方案一**：三台都清数据重建（没有重要数据时推荐）
- **方案二**：在存活的节点上移除旧 node1，再用 `existing` 加入

```bash
# 在 node2 上查看成员
ETCDCTL_API=3 etcdctl --endpoints=https://192.168.0.145:2379 \
  --cacert=/opt/etcd/ssl/chain.pem --cert=/opt/etcd/ssl/server.pem --key=/opt/etcd/ssl/server.key \
  member list

# 移除旧 node1（用查到的 member ID）
ETCDCTL_API=3 etcdctl --endpoints=https://192.168.0.145:2379 \
  --cacert=/opt/etcd/ssl/chain.pem --cert=/opt/etcd/ssl/server.pem --key=/opt/etcd/ssl/server.key \
  member remove <node1_member_id>

# 修改 node1 的 yml：initial-cluster-state: existing
# 然后启动 node1
```

### 问题 5：证书 SAN 不含 127.0.0.1

**现象**：日志报 `x509: certificate is not valid for ... 127.0.0.1`

**原因**：华为云签发的证书 SAN 中没有 127.0.0.1。

**解决**：从 yml 配置的 `listen-client-urls` 中去掉 `https://127.0.0.1:2379`，本地访问用实际 IP。

### 问题 6：Nacos 连接 etcd 报证书错误

**原因**：Nacos 不带客户端证书，但 etcd 配了 `client-cert-auth: true`。

**解决**：将 `client-transport-security` 段的 `client-cert-auth` 改为 `false`，`peer-transport-security` 保持 `true`。

### 问题 7：systemd service 文件 ExecStart 续行问题

**现象**：ExecStart 用 `\` 续行后启动失败，但前台用同样命令能跑。

**原因**：systemd 对 `\` 续行非常敏感，`\` 后面不能有空格、Tab 或 CRLF。从 GitHub/Windows 复制的文件容易带 CRLF。

**解决**：

1. 清理 CRLF：`perl -i -pe 's/\r$//' /etc/systemd/system/etcd.service`
2. 或者把 ExecStart 写成一行（最稳）

### 问题 8：前台运行没输出就退出

**排查**：

```bash
# 直接运行看报错
/opt/etcd/etcd --config-file /opt/etcd/etcd.yml

# 用命令行参数排除 yml 问题
/opt/etcd/etcd --name node1 --data-dir /opt/etcd/data \
  --listen-client-urls http://192.168.0.168:2379 \
  --listen-peer-urls http://192.168.0.168:2380 \
  --advertise-client-urls http://192.168.0.168:2379 \
  --initial-advertise-peer-urls http://192.168.0.168:2380 \
  --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 \
  --initial-cluster-state new --initial-cluster-token etcd-cluster

# 用 strace 追踪
strace -f -o /tmp/etcd.log /opt/etcd/etcd --config-file /opt/etcd/etcd.yml
tail -50 /tmp/etcd.log
```

### 问题 9：只检查到 1 个节点健康

**原因**：2380 端口不通。

**排查**：

```bash
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo OK || echo FAIL'
```

华为云安全组需要放行 2379 和 2380。

### 问题 10：完全重新初始化集群

```bash
# 三台都执行
systemctl stop etcd
pkill etcd 2>/dev/null
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data
systemctl start etcd
```

---

## 附录A：配置字段速查表

### yml 字段对照

| yml 字段 | 命令行参数 | 说明 | 必须 |
|----------|-----------|------|------|
| `name` | `--name` | 节点名称，必须和 initial-cluster 中的 key 匹配 | **必须** |
| `data-dir` | `--data-dir` | 数据目录 | **必须** |
| `listen-client-urls` | `--listen-client-urls` | 客户端监听地址 | **必须** |
| `listen-peer-urls` | `--listen-peer-urls` | 节点间监听地址 | **必须** |
| `advertise-client-urls` | `--advertise-client-urls` | 客户端广播地址 | **必须** |
| `initial-advertise-peer-urls` | `--initial-advertise-peer-urls` | 节点间广播地址 | **必须** |
| `initial-cluster` | `--initial-cluster` | 集群成员列表 | 首次必须 |
| `initial-cluster-state` | `--initial-cluster-state` | `new` 或 `existing` | 首次必须 |
| `initial-cluster-token` | `--initial-cluster-token` | 集群标识 | 建议填 |
| `client-transport-security.cert-file` | `--cert-file` | 服务端证书 | HTTPS 必须 |
| `client-transport-security.key-file` | `--key-file` | 服务端私钥 | HTTPS 必须 |
| `client-transport-security.trusted-ca-file` | `--trusted-ca-file` | 客户端 CA | HTTPS 必须 |
| `client-transport-security.client-cert-auth` | `--client-cert-auth` | 要求客户端证书 | 可选 |
| `peer-transport-security.cert-file` | `--peer-cert-file` | peer 证书 | HTTPS 必须 |
| `peer-transport-security.key-file` | `--peer-key-file` | peer 私钥 | HTTPS 必须 |
| `peer-transport-security.trusted-ca-file` | `--peer-trusted-ca-file` | peer CA | HTTPS 必须 |
| `peer-transport-security.client-cert-auth` | `--peer-client-cert-auth` | 要求 peer 证书 | 建议开 |
| `auto-tls` | `--auto-tls` | 自动生成证书（不推荐生产） | 不推荐 |

---

## 附录B：yml 配置文件踩坑指南

### 常见格式问题

1. **CRLF 换行符**：从 GitHub 或 Windows 编辑器复制到 Linux，会带 `\r\n`。etcd 解析 yml 时会报 `yaml did not find expected key`。
   - 检查：`cat -A /opt/etcd/etcd.yml | head -5`，如果行尾有 `^M$` 就是有 CRLF
   - 修复：`perl -i -pe 's/\r$//' /opt/etcd/etcd.yml`

2. **Tab 缩进**：yml 不允许 Tab，必须用空格。特别是 `client-transport-security:` 下面的子项必须缩进 2 个空格。
   - 检查：用 `cat -A` 查看，Tab 显示为 `^I`
   - 修复：把 Tab 替换为空格

3. **引号格式**：etcd 的 yml 对值引号比较敏感。建议用单引号包裹包含特殊字符的值（如 URL），纯数字/布尔值不引。

4. **缩进层级**：`client-transport-security:` 和 `peer-transport-security:` 是顶级 key，下面的子项要缩进 2 个空格：
   ```yaml
   client-transport-security:
     cert-file: /opt/etcd/ssl/server.pem    # 缩进 2 空格
     key-file: /opt/etcd/ssl/server.key      # 缩进 2 空格
   ```

5. **验证 yml 格式**：
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('/opt/etcd/etcd.yml'))"
   ```
   如果没报错说明格式正确。

### 如果 yml 始终有问题

可以改用命令行参数替代（最稳定的方式），把 service 文件的 ExecStart 写成一行：

**HTTP 模式 node1 示例**：

```ini
ExecStart=/opt/etcd/etcd --name node1 --data-dir /opt/etcd/data --listen-client-urls http://192.168.0.168:2379,http://127.0.0.1:2379 --listen-peer-urls http://192.168.0.168:2380 --advertise-client-urls http://192.168.0.168:2379 --initial-advertise-peer-urls http://192.168.0.168:2380 --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 --initial-cluster-state new --initial-cluster-token etcd-cluster
```

**HTTPS 模式 node1 示例**：

```ini
ExecStart=/opt/etcd/etcd --name node1 --data-dir /opt/etcd/data --listen-client-urls https://192.168.0.168:2379 --listen-peer-urls https://192.168.0.168:2380 --advertise-client-urls https://192.168.0.168:2379 --initial-advertise-peer-urls https://192.168.0.168:2380 --initial-cluster node1=https://192.168.0.168:2380,node2=https://192.168.0.145:2380,node3=https://192.168.0.79:2380 --initial-cluster-state new --initial-cluster-token etcd-cluster --cert-file /opt/etcd/ssl/server.pem --key-file /opt/etcd/ssl/server.key --peer-cert-file /opt/etcd/ssl/server.pem --peer-key-file /opt/etcd/ssl/server.key --trusted-ca-file /opt/etcd/ssl/chain.pem --peer-trusted-ca-file /opt/etcd/ssl/chain.pem --client-cert-auth --peer-client-cert-auth
```

> 注意：HTTPS 的命令行参数版本不含 127.0.0.1，因为证书 SAN 中没有 localhost。