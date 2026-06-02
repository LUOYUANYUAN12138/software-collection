# etcd 三节点集群部署指南

> 适用环境：华为云 ECS 内网（EulerOS / openEuler）
> 节点 IP：192.168.0.168（node1）、192.168.0.145（node2）、192.168.0.79（node3）
> 跳板机 1 台，可 SSH 到三台节点

---

## 目录

- [一、前置条件](#一前置条件)
- [二、网络连通性测试](#二网络连通性测试)
- [三、方案 A：HTTP 模式（无 TLS）](#三方案-ahttp-模式无-tls)
- [四、方案 B：HTTPS 模式（TLS 加密）](#四方案-bhttps-模式tls-加密)
- [五、验证集群](#五验证集群)
- [六、跳板机批量部署脚本](#六跳板机批量部署脚本)
- [七、排错手册](#七排错手册)
- [附录：从 HTTP 切换到 HTTPS](#附录从-http-切换到-https)

---

## 一、前置条件

### 1. 确认 etcd 二进制

```bash
ls -la /opt/etcd/etcd
ls -la /opt/etcd/etcdctl
```

如果不在 PATH 中：

```bash
ln -sf /opt/etcd/etcd /usr/local/bin/etcd
ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl

# 验证
etcd --version
ETCDCTL_API=3 etcdctl version
```

### 2. 确认端口未被占用

```bash
ss -tlnp | grep -E '2379|2380'
```

如果有输出，说明端口被占用，需要先停掉旧进程：

```bash
pkill etcd
```

### 3. etcd 版本与 systemd Type 的兼容性

- etcd >= 3.5：支持 `Type=notify`（systemd 能感知 etcd 就绪）
- etcd < 3.5 或不确定：用 `Type=simple` + `TimeoutStartSec=120`

```bash
etcd --version | head -1
```

---

## 二、网络连通性测试

华为云安全组已配置的情况下，确认三台之间 2379、2380 端口互通。

**在每台机器上执行**（用 bash 内置 TCP 测试，不需要 telnet）：

```bash
# node1（192.168.0.168）上测试到 node2、node3
bash -c 'echo > /dev/tcp/192.168.0.145/2379 && echo "145:2379 OK" || echo "145:2379 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo "145:2380 OK" || echo "145:2380 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.79/2379 && echo "79:2379 OK" || echo "79:2379 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.79/2380 && echo "79:2380 OK" || echo "79:2380 FAIL"'

# node2（192.168.0.145）上测试到 node1、node3
bash -c 'echo > /dev/tcp/192.168.0.168/2379 && echo "168:2379 OK" || echo "168:2379 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.168/2380 && echo "168:2380 OK" || echo "168:2380 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.79/2379 && echo "79:2379 OK" || echo "79:2379 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.79/2380 && echo "79:2380 OK" || echo "79:2380 FAIL"'

# node3（192.168.0.79）上测试到 node1、node2
bash -c 'echo > /dev/tcp/192.168.0.168/2379 && echo "168:2379 OK" || echo "168:2379 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.168/2380 && echo "168:2380 OK" || echo "168:2380 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.145/2379 && echo "145:2379 OK" || echo "145:2379 FAIL"'
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo "145:2380 OK" || echo "145:2380 FAIL"'
```

**所有 12 条都必须输出 OK**，如果有 FAIL 检查安全组规则。

---

## 三、方案 A：HTTP 模式（无 TLS）

> 内网环境推荐先用此方案跑通集群，确认 etcd 本身没问题，再加 TLS。

### 1. 创建 systemd 服务文件

三台机器**都执行**：

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=notify
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
```

> **如果你的 etcd 版本 < 3.5**，把 `Type=notify` 改为 `Type=simple`，并在 `[Service]` 段加一行 `TimeoutStartSec=120`。

### 2. 配置文件

#### node1（192.168.0.168） `/opt/etcd/etcd.yml`

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

#### node2（192.168.0.145） `/opt/etcd/etcd.yml`

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

#### node3（192.168.0.79） `/opt/etcd/etcd.yml`

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

### 3. 关于 `name` 字段

**`name` 是必填字段**，不能省略。原因：

- 集群模式下 etcd 使用 `name` 标识节点身份
- `name` 必须和 `initial-cluster` 中的 key 完全匹配（node1/node2/node3）
- 如果不写 `name`，etcd 会使用系统的 `hostname`，而 hostname 通常不会是 node1/node2/node3，导致集群初始化失败

### 4. 启动集群

三台机器都执行（尽量同时启动，间隔不要超过 1 分钟）：

```bash
# 清理旧数据（首次启动或重新初始化时必须执行）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data

# 加载服务并启动
systemctl daemon-reload
systemctl enable etcd
systemctl start etcd

# 检查状态
systemctl status etcd
```

---

## 四、方案 B：HTTPS 模式（TLS 加密）

> 前提：先用方案 A 跑通集群，确认 etcd 本身没问题。

### 0. 确认证书文件

你的证书放在 `/opt/etcd/ssl/` 下，文件为：

| 文件 | 用途 |
|------|------|
| `chain.pem` | CA 证书（根证书链） |
| `server.pem` | 服务端证书 |
| `server.key` | 服务端私钥 |

**重要：这些文件不需要做 base64 转换，不需要做 PKCS8 转换。** 你之前看到的教程是给 Java/Nacos 用的，etcd 直接使用原始 PEM 格式。

### 1. 检查证书 SAN（关键！）

在每台机器上执行：

```bash
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"
```

你会看到类似这样的输出：

```
Subject Alternative Name:
    DNS:etcd-node, IP Address:192.168.0.168, IP Address:192.168.0.145, IP Address:192.168.0.79
```

**情况判断：**

| SAN 内容 | 处理方式 |
|-----------|----------|
| 包含所有 3 个 IP | 三台可以共用同一套证书，直接用 |
| 只包含 1 个 IP | 每台需要各自签名的证书（确认三台的 server.pem 内容不同） |
| 不包含任何内网 IP | 证书不能用，需要重新签发 |

确认三台证书是否相同：

```bash
# 三台分别执行
md5sum /opt/etcd/ssl/server.pem
md5sum /opt/etcd/ssl/server.key
md5sum /opt/etcd/ssl/chain.pem
```

- 如果三台 md5 相同 → 共用证书，SAN 必须包含所有 IP
- 如果三台 md5 不同 → 各自签名，SAN 只需包含本机 IP

### 2. 创建 systemd 服务文件

与方案 A 相同：

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=notify
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
```

### 3. 配置文件

#### node1（192.168.0.168） `/opt/etcd/etcd.yml`

```yaml
name: 'node1'
data-dir: /opt/etcd/data
listen-client-urls: 'https://192.168.0.168:2379,https://127.0.0.1:2379'
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

#### node2（192.168.0.145） `/opt/etcd/etcd.yml`

```yaml
name: 'node2'
data-dir: /opt/etcd/data
listen-client-urls: 'https://192.168.0.145:2379,https://127.0.0.1:2379'
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

#### node3（192.168.0.79） `/opt/etcd/etcd.yml`

```yaml
name: 'node3'
data-dir: /opt/etcd/data
listen-client-urls: 'https://192.168.0.79:2379,https://127.0.0.1:2379'
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

### 4. 关于 `client-cert-auth` 的取舍

| 设置 | 含义 | 适用场景 |
|------|------|----------|
| `client-cert-auth: true` | 客户端必须提供证书才能连接 etcd | etcd 集群内部通信（peer）建议开 |
| `client-cert-auth: false` | 客户端不需要证书，只服务端提供证书 | 如果 Nacos 等应用不带客户端证书连 etcd，需要关掉 |

**如果后续 Nacos 连接 etcd 报证书错误**，把 `client-transport-security` 段的 `client-cert-auth: true` 改为 `client-cert-auth: false`，然后重启 etcd。

`peer-transport-security` 段的 `client-cert-auth: true` 建议保持不变——这是节点间通信，三台都有证书。

### 5. 如果三台证书不同（各台独立签发）

把配置文件中的证书路径改为各台自己的证书文件名即可。比如某台的证书叫 `server-node1.pem`，就改：

```yaml
client-transport-security:
  cert-file: /opt/etcd/ssl/server-node1.pem
  key-file: /opt/etcd/ssl/server-node1.key
  ...
```

### 6. 启动集群

```bash
# 清理旧数据（如果之前用 HTTP 模式启动过，必须清理）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data

# 确认证书文件可读
ls -la /opt/etcd/ssl/

# 加载并启动
systemctl daemon-reload
systemctl enable etcd
systemctl start etcd

# 检查状态
systemctl status etcd
```

---

## 五、验证集群

### 方案 A（HTTP）验证

在任意一台执行：

```bash
# 查看集群成员
ETCDCTL_API=3 etcdctl \
  --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 \
  member list

# 检查健康状态
ETCDCTL_API=3 etcdctl \
  --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 \
  endpoint health

# 写入测试
ETCDCTL_API=3 etcdctl \
  --endpoints=http://192.168.0.168:2379 \
  put testkey hello

# 从另一台读取（验证数据同步）
ETCDCTL_API=3 etcdctl \
  --endpoints=http://192.168.0.145:2379 \
  get testkey
```

预期输出：
- `member list` 显示 3 个节点，状态都是 started
- `endpoint health` 显示 3 个节点都是 healthy
- `get testkey` 返回 `hello`

### 方案 B（HTTPS）验证

在任意一台执行：

```bash
# 查看集群成员
ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  member list

# 检查健康状态
ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  endpoint health

# 写入测试
ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.168:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  put testkey hello

# 从另一台读取
ETCDCTL_API=3 etcdctl \
  --endpoints=https://192.168.0.145:2379 \
  --cacert=/opt/etcd/ssl/chain.pem \
  --cert=/opt/etcd/ssl/server.pem \
  --key=/opt/etcd/ssl/server.key \
  get testkey
```

---

## 六、跳板机批量部署脚本

### HTTP 模式部署脚本

保存为 `deploy-etcd-http.sh`，在跳板机上执行：

```bash
#!/bin/bash
# etcd HTTP 模式批量部署脚本
# 在跳板机上运行

set -e

NODES=("192.168.0.168" "192.168.0.145" "192.168.0.79")
NAMES=("node1" "node2" "node3")
USER="root"

for i in "${!NODES[@]}"; do
  IP=${NODES[$i]}
  NAME=${NAMES[$i]}

  echo "=========================================="
  echo "配置 $NAME ($IP)"
  echo "=========================================="

  # 创建 systemd 服务
  ssh ${USER}@${IP} 'cat > /etc/systemd/system/etcd.service << '"'"'EOF'"'"'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=notify
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF'

  # 写入配置文件
  ssh ${USER}@${IP} "cat > /opt/etcd/etcd.yml << EOF
name: '${NAME}'
data-dir: /opt/etcd/data
listen-client-urls: 'http://${IP}:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://${IP}:2380'
advertise-client-urls: 'http://${IP}:2379'
initial-advertise-peer-urls: 'http://${IP}:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: 'etcd-cluster'
EOF"

  # 链接二进制
  ssh ${USER}@${IP} 'ln -sf /opt/etcd/etcd /usr/local/bin/etcd; ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl'

  # 清理旧数据
  ssh ${USER}@${IP} 'rm -rf /opt/etcd/data; mkdir -p /opt/etcd/data'

  echo "$NAME ($IP) 配置完成"
  echo ""
done

echo "=========================================="
echo "三台节点配置完成！"
echo "现在依次 SSH 到每台执行："
echo "  systemctl daemon-reload"
echo "  systemctl enable etcd"
echo "  systemctl start etcd"
echo "  systemctl status etcd"
echo "=========================================="
```

### HTTPS 模式部署脚本

保存为 `deploy-etcd-https.sh`，在跳板机上执行：

```bash
#!/bin/bash
# etcd HTTPS 模式批量部署脚本
# 前提：三台机器的 /opt/etcd/ssl/ 下已有证书文件
# 前提：已确认证书 SAN 包含对应 IP

set -e

NODES=("192.168.0.168" "192.168.0.145" "192.168.0.79")
NAMES=("node1" "node2" "node3")
USER="root"

for i in "${!NODES[@]}"; do
  IP=${NODES[$i]}
  NAME=${NAMES[$i]}

  echo "=========================================="
  echo "配置 $NAME ($IP)"
  echo "=========================================="

  # 创建 systemd 服务
  ssh ${USER}@${IP} 'cat > /etc/systemd/system/etcd.service << '"'"'EOF'"'"'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=notify
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF'

  # 写入配置文件
  ssh ${USER}@${IP} "cat > /opt/etcd/etcd.yml << EOF
name: '${NAME}'
data-dir: /opt/etcd/data
listen-client-urls: 'https://${IP}:2379,https://127.0.0.1:2379'
listen-peer-urls: 'https://${IP}:2380'
advertise-client-urls: 'https://${IP}:2379'
initial-advertise-peer-urls: 'https://${IP}:2380'
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
EOF"

  # 链接二进制
  ssh ${USER}@${IP} 'ln -sf /opt/etcd/etcd /usr/local/bin/etcd; ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl'

  # 确认证书文件存在
  echo "证书文件检查："
  ssh ${USER}@${IP} 'ls -la /opt/etcd/ssl/'

  # 清理旧数据
  ssh ${USER}@${IP} 'rm -rf /opt/etcd/data; mkdir -p /opt/etcd/data'

  echo "$NAME ($IP) 配置完成"
  echo ""
done

echo "=========================================="
echo "三台节点配置完成！"
echo "现在依次 SSH 到每台执行："
echo "  systemctl daemon-reload"
echo "  systemctl enable etcd"
echo "  systemctl start etcd"
echo "  systemctl status etcd"
echo "=========================================="

echo ""
echo "验证命令："
echo "ETCDCTL_API=3 etcdctl \\"
echo "  --endpoints=https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379 \\"
echo "  --cacert=/opt/etcd/ssl/chain.pem \\"
echo "  --cert=/opt/etcd/ssl/server.pem \\"
echo "  --key=/opt/etcd/ssl/server.key \\"
echo "  endpoint health"
```

---

## 七、排错手册

### 问题 1：systemctl start etcd 报 exit-code

**错误信息**：`Job for etcd.service failed because the control process exited with error code`

**排查步骤**（按顺序执行）：

```bash
# 第一步：看退出码
systemctl status etcd

# 第二步：看完整日志
journalctl -u etcd -n 100 --no-pager

# 第三步：如果上面都没有有效信息，前台跑看错误
/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
# 错误会直接打印到终端
```

### 问题 2：前台运行没有输出就退出

这通常是配置文件格式问题。排查：

```bash
# 检查 yml 格式（注意缩进和引号）
cat -A /opt/etcd/etcd.yml | head -20

# 验证 yml 是否合法（如果机器上有 python）
python3 -c "import yaml; yaml.safe_load(open('/opt/etcd/etcd.yml'))" 2>&1

# 最小化测试：用最少参数前台启动
/opt/etcd/etcd --name test-node --data-dir /tmp/etcd-test --listen-client-urls http://127.0.0.1:2379
# 如果这个能跑起来，说明是配置文件的问题
```

### 问题 3：日志含 certificate / TLS / x509 错误

**常见信息**：`remote error: tls: bad certificate`、`certificate does not match`、`x509: certificate signed by unknown authority`

**原因**：用了 https 但证书不匹配。

**快速修复**：先把配置改为 HTTP 模式（方案 A），确认 etcd 本身没问题，再排查证书。

**证书排查**：

```bash
# 1. 确认证书文件存在且可读
ls -la /opt/etcd/ssl/

# 2. 检查证书 SAN 包含的 IP
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# 3. 检查证书是否过期
openssl x509 -in /opt/etcd/ssl/server.pem -noout -dates

# 4. 验证证书和私钥是否匹配（两条命令的 md5 应该一样）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -modulus | md5sum
openssl rsa -in /opt/etcd/ssl/server.key -noout -modulus | md5sum

# 5. 验证证书链（CA 是否信任服务端证书）
openssl verify -CAfile /opt/etcd/ssl/chain.pem /opt/etcd/ssl/server.pem
```

### 问题 4：日志含 `conflict entry` / `already initialized`

**原因**：data-dir 中有旧数据。当 `initial-cluster-state: new` 时，data-dir 必须为空。

**修复**：

```bash
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
systemctl start etcd
```

> **警告**：`rm -rf /opt/etcd/data` 会删除所有 etcd 数据！生产环境请先备份。

### 问题 5：日志含 `bind: address already in use`

**原因**：有旧 etcd 进程没杀干净，或其他程序占了 2379/2380 端口。

```bash
# 查看谁在占端口
ss -tlnp | grep -E '2379|2380'

# 杀掉旧进程
pkill etcd

# 如果端口还是被占，看看是哪个进程
ss -tlnp | grep 2379
# 根据进程 ID 处理
```

### 问题 6：`Type=notify` 导致启动失败

**错误信息**：`Failed at step NOTIFY_SOCKET spawning` 或 systemd 直接超时。

**原因**：etcd 版本 < 3.5，或者编译时没有包含 systemd notify 支持。

**修复**：编辑 `/etc/systemd/system/etcd.service`：

```ini
[Service]
Type=simple
TimeoutStartSec=120
# ... 其他行不变
```

然后：

```bash
systemctl daemon-reload
systemctl restart etcd
```

### 问题 7：只有 1 个节点健康，其他节点报 connection refused

**原因**：节点间网络不通（2380 端口）。

**排查**：

```bash
# 从 node1 测试到 node2 的 peer 端口
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo "OK" || echo "FAIL"'

# 如果 FAIL，检查安全组规则是否放行了 2380
```

华为云 ECS 安全组需要放行以下端口：
- 2379（客户端通信）
- 2380（节点间通信）

### 问题 8：集群已存在成员，想重新初始化

**场景**：之前启动过，现在想完全重来。

```bash
# 在三台机器上分别执行
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data

# 确保配置文件中 initial-cluster-state: new
grep "initial-cluster-state" /opt/etcd/etcd.yml

# 重新启动
systemctl start etcd
```

### 问题 9：etcdctl 连接 HTTPS 集群报错

**常见报错**：`x509: certificate is valid for ... not for ...`

这意味着证书的 SAN 不包含你连接时用的 IP。检查：

```bash
# 看证书的 SAN
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# etcdctl 的 --endpoints 里的 IP 必须在 SAN 中
```

**常见报错**：`x509: certificate signed by unknown authority`

`--cacert` 指定的 CA 证书不对，确认 chain.pem 文件内容。

### 问题 10：Nacos 连接 etcd 报证书错误

如果 Nacos 连接 etcd 不带客户端证书，需要关闭客户端证书认证：

编辑每台机器的 `/opt/etcd/etcd.yml`：

```yaml
client-transport-security:
  cert-file: /opt/etcd/ssl/server.pem
  key-file: /opt/etcd/ssl/server.key
  client-cert-auth: false    # 改为 false
  trusted-ca-file: /opt/etcd/ssl/chain.pem
  auto-tls: false
```

`peer-transport-security` 段的 `client-cert-auth: true` 保持不变。

然后重启：

```bash
systemctl restart etcd
```

### 通用排查流程

```
systemctl start etcd 失败
│
├─ systemctl status etcd 看退出码
│   │
│   ├─ journalctl -u etcd -n 100 看日志
│   │   │
│   │   ├─ certificate / TLS 相关 → 证书问题（问题 3）
│   │   ├─ conflict entry → 数据冲突（问题 4）
│   │   ├─ bind: address already in use → 端口冲突（问题 5）
│   │   └─ connection refused → 网络不通（问题 7）
│   │
│   └─ 日志为空 → 前台运行看报错（问题 2）
│
└─ Type=notify 失败 → 改 Type=simple（问题 6）
```

---

## 附录：从 HTTP 切换到 HTTPS

如果你先用方案 A（HTTP）跑通了集群，现在想升级到 HTTPS：

### 步骤

```bash
# 1. 确认证书 SAN（在三台分别执行）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# 2. 停止三台 etcd
# 在每台执行
systemctl stop etcd

# 3. 清理数据（必须！因为从 HTTP 切到 HTTPS 相当于重建集群）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data

# 4. 修改配置文件（用方案 B 的配置替换方案 A 的配置）

# 5. 启动三台 etcd
systemctl start etcd
systemctl status etcd

# 6. 用 HTTPS 方式验证集群（见第五节 HTTPS 验证部分）
```

> **注意**：从 HTTP 切换到 HTTPS 必须清空 data-dir 重新初始化，不能原地升级。如果你有重要数据需要保留，先用 etcdctl 备份：
> ```bash
> ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379 snapshot save /tmp/etcd-snapshot.db
> ```
> 切换到 HTTPS 后再恢复。

---

## 配置字段速查表

| 字段 | 说明 | 是否必须 |
|------|------|----------|
| `name` | 节点名称，必须和 initial-cluster 中的 key 匹配 | **必须** |
| `data-dir` | 数据存储目录 | **必须** |
| `listen-client-urls` | 监听客户端请求的地址 | **必须** |
| `listen-peer-urls` | 监听节点间通信的地址 | **必须** |
| `advertise-client-urls` | 告知客户端的访问地址 | **必须** |
| `initial-advertise-peer-urls` | 告知其他节点的通信地址 | **必须** |
| `initial-cluster` | 集群成员列表 | 首次启动必须 |
| `initial-cluster-state` | `new`（新建集群）或 `existing`（加入已有集群） | 首次启动必须 |
| `initial-cluster-token` | 集群唯一标识，防止误加入其他集群 | 建议填写 |
| `client-transport-security` | 客户端 TLS 配置 | HTTPS 时必须 |
| `peer-transport-security` | 节点间 TLS 配置 | HTTPS 时必须 |