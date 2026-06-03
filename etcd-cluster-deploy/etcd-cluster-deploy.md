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
- [附录A：从 HTTP 切换到 HTTPS](#附录a从-http-切换到-https)
- [附录B：配置字段速查表](#附录b配置字段速查表)

---

## 一、前置条件

### 1. 确认 etcd 二进制

```bash
ls -la /opt/etcd/etcd
/opt/etcd/etcd --version
```

如果不在 PATH 中：

```bash
ln -sf /opt/etcd/etcd /usr/local/bin/etcd
ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl
```

### 2. 确认端口未被占用

```bash
ss -tlnp | grep -E '2379|2380'
```

如果有输出，先杀掉旧进程：

```bash
pkill etcd
```

### 3. 确认架构匹配

```bash
file /opt/etcd/etcd
uname -m
```

如果 `file` 显示 `ARM aarch64` 但 `uname -m` 显示 `x86_64`（或反过来），说明二进制架构不对，需要重新下载。

### 4. 关于启动方式

**本仓库提供两种方式启动 etcd：**

| 方式 | 文件 | 优缺点 |
|------|------|--------|
| **命令行参数（推荐）** | `etcd.service.http.nodeX` / `etcd.service.https.nodeX` | 稳定可靠，不会因 yml 格式问题导致静默退出 |
| **配置文件** | `etcd.yml` | 集中管理，但部分环境下 yml 格式问题会导致 etcd 无输出退出 |

> **已知问题**：部分环境下 etcd 读取 yml 配置文件会静默退出不报错，原因可能是 yml 引号格式、缩进、编码等问题。
> 如果遇到 `systemctl start etcd` 报 `exit-code` 但前台运行也没输出的情况，**请使用命令行参数方式（推荐）**。

---

## 二、网络连通性测试

华为云安全组已配置的情况下，确认三台之间 2379、2380 端口互通。

**在每台机器上执行**（无需 telnet，用 bash 内置）：

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

### 1. 部署方式

**推荐使用命令行参数方式**（直接用本仓库的 service 文件）：

```bash
# 在对应节点上，将 service 文件复制到 systemd 目录
# node1（192.168.0.168）：
cp etcd.service.http.node1 /etc/systemd/system/etcd.service

# node2（192.168.0.145）：
cp etcd.service.http.node2 /etc/systemd/system/etcd.service

# node3（192.168.0.79）：
cp etcd.service.http.node3 /etc/systemd/system/etcd.service
```

### 2. 启动集群

三台机器都执行（尽量同时启动，间隔不要超过 1 分钟）：

```bash
# 清理旧数据（首次启动或重新初始化时必须执行）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data

# 加载服务并启动
systemctl daemon-reload
systemctl enable etcd
systemctl start etcd

# 检查状态
systemctl status etcd
```

### 3. 关于 `name` 字段

**`name` 是必填字段**，不能省略。原因：
- 集群模式下 etcd 使用 `name` 标识节点身份
- `name` 必须和 `initial-cluster` 中的 key 完全匹配（node1/node2/node3）
- 如果不写 `name`，etcd 会使用系统的 `hostname`，而 hostname 通常不会是 node1/node2/node3，导致集群初始化失败

### 4. service 文件内容说明

以 node1 为例，`etcd.service.http.node1` 内容：

```ini
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node1 \
  --data-dir /opt/etcd/data \
  --listen-client-urls http://192.168.0.168:2379,http://127.0.0.1:2379 \
  --listen-peer-urls http://192.168.0.168:2380 \
  --advertise-client-urls http://192.168.0.168:2379 \
  --initial-advertise-peer-urls http://192.168.0.168:2380 \
  --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 \
  --initial-cluster-state new \
  --initial-cluster-token etcd-cluster
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

> **为什么用 `Type=simple` 而不是 `Type=notify`？**
> `Type=notify` 要求 etcd >= 3.5 且编译时包含 systemd notify 支持。如果版本不兼容会导致启动失败。
> `Type=simple` 兼容所有版本。配合 `TimeoutStartSec=120` 给 etcd 足够的启动时间。

---

## 四、方案 B：HTTPS 模式（TLS 加密）

> **前提**：先用方案 A 跑通集群，确认 etcd 本身没问题，再切换到 HTTPS。

### 0. 确认证书文件

你的证书在 `/opt/etcd/ssl/` 下：

| 文件 | 用途 |
|------|------|
| `chain.pem` | CA 证书（根证书链） |
| `server.pem` | 服务端证书 |
| `server.key` | 服务端私钥 |

**重要：这些文件不需要做 base64 转换，不需要做 PKCS8 转换。** 之前教程里的 base64/PKCS8 转换是给 Java/Nacos 用的，etcd 直接使用原始 PEM 格式。

### 1. 检查证书 SAN（关键！）

在每台机器上执行：

```bash
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"
```

输出示例：
```
Subject Alternative Name:
    DNS:etcd-node, IP Address:192.168.0.168, IP Address:192.168.0.145, IP Address:192.168.0.79
```

| SAN 内容 | 处理方式 |
|-----------|----------|
| 包含所有 3 个 IP | 三台可以共用同一套证书 |
| 只包含 1 个 IP | 每台需要各自签名的证书（确认三台的 server.pem 内容不同） |
| 不包含任何内网 IP | 证书不能用，需要重新签发 |

确认三台证书是否相同：

```bash
# 三台分别执行
md5sum /opt/etcd/ssl/server.pem
md5sum /opt/etcd/ssl/server.key
md5sum /opt/etcd/ssl/chain.pem
```

- 三台 md5 相同 → 共用证书，SAN 必须包含所有 IP
- 三台 md5 不同 → 各自签名，SAN 只需包含本机 IP

### 2. 部署方式

使用命令行参数方式（推荐）：

```bash
# node1（192.168.0.168）：
cp etcd.service.https.node1 /etc/systemd/system/etcd.service

# node2（192.168.0.145）：
cp etcd.service.https.node2 /etc/systemd/system/etcd.service

# node3（192.168.0.79）：
cp etcd.service.https.node3 /etc/systemd/system/etcd.service
```

### 3. service 文件内容说明

以 node1 为例，`etcd.service.https.node1` 内容：

```ini
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node1 \
  --data-dir /opt/etcd/data \
  --listen-client-urls https://192.168.0.168:2379,https://127.0.0.1:2380 \
  --listen-peer-urls https://192.168.0.168:2380 \
  --advertise-client-urls https://192.168.0.168:2379 \
  --initial-advertise-peer-urls https://192.168.0.168:2380 \
  --initial-cluster node1=https://192.168.0.168:2380,node2=https://192.168.0.145:2380,node3=https://192.168.0.79:2380 \
  --initial-cluster-state new \
  --initial-cluster-token etcd-cluster \
  --cert-file /opt/etcd/ssl/server.pem \
  --key-file /opt/etcd/ssl/server.key \
  --peer-cert-file /opt/etcd/ssl/server.pem \
  --peer-key-file /opt/etcd/ssl/server.key \
  --trusted-ca-file /opt/etcd/ssl/chain.pem \
  --peer-trusted-ca-file /opt/etcd/ssl/chain.pem \
  --client-cert-auth \
  --peer-client-cert-auth
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### 4. 关于 `--client-cert-auth` 的取舍

| 设置 | 含义 | 适用场景 |
|------|------|----------|
| `--client-cert-auth` 开启 | 客户端必须提供证书才能连接 | etcd 集群内部通信（peer）建议开 |
| 不加 `--client-cert-auth` | 客户端不需要证书 | 如果 Nacos 等应用不带客户端证书连 etcd |

**如果后续 Nacos 连接 etcd 报证书错误**，编辑 service 文件删除 `--client-cert-auth` 这一行，保留 `--peer-client-cert-auth`，然后：

```bash
systemctl daemon-reload
systemctl restart etcd
```

### 5. 启动集群

```bash
# 清理旧数据（如果之前用 HTTP 模式启动过，必须清理）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data

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

  # 创建 systemd 服务（命令行参数方式）
  ssh ${USER}@${IP} "cat > /etc/systemd/system/etcd.service << 'SERVICEEOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \\
  --name ${NAME} \\
  --data-dir /opt/etcd/data \\
  --listen-client-urls http://${IP}:2379,http://127.0.0.1:2379 \\
  --listen-peer-urls http://${IP}:2380 \\
  --advertise-client-urls http://${IP}:2379 \\
  --initial-advertise-peer-urls http://${IP}:2380 \\
  --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 \\
  --initial-cluster-state new \\
  --initial-cluster-token etcd-cluster
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICEEOF"

  # 链接二进制
  ssh ${USER}@${IP} 'ln -sf /opt/etcd/etcd /usr/local/bin/etcd; ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl'

  # 清理旧数据
  ssh ${USER}@${IP} 'rm -rf /opt/etcd/data; mkdir -p /opt/etcd/data; chmod 700 /opt/etcd/data'

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

  # 检查证书文件
  echo "证书文件检查："
  ssh ${USER}@${IP} 'ls -la /opt/etcd/ssl/'

  # 创建 systemd 服务（命令行参数方式 + TLS）
  ssh ${USER}@${IP} "cat > /etc/systemd/system/etcd.service << 'SERVICEEOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \\
  --name ${NAME} \\
  --data-dir /opt/etcd/data \\
  --listen-client-urls https://${IP}:2379,https://127.0.0.1:2379 \\
  --listen-peer-urls https://${IP}:2380 \\
  --advertise-client-urls https://${IP}:2379 \\
  --initial-advertise-peer-urls https://${IP}:2380 \\
  --initial-cluster node1=https://192.168.0.168:2380,node2=https://192.168.0.145:2380,node3=https://192.168.0.79:2380 \\
  --initial-cluster-state new \\
  --initial-cluster-token etcd-cluster \\
  --cert-file /opt/etcd/ssl/server.pem \\
  --key-file /opt/etcd/ssl/server.key \\
  --peer-cert-file /opt/etcd/ssl/server.pem \\
  --peer-key-file /opt/etcd/ssl/server.key \\
  --trusted-ca-file /opt/etcd/ssl/chain.pem \\
  --peer-trusted-ca-file /opt/etcd/ssl/chain.pem \\
  --client-cert-auth \\
  --peer-client-cert-auth
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICEEOF"

  # 链接二进制
  ssh ${USER}@${IP} 'ln -sf /opt/etcd/etcd /usr/local/bin/etcd; ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl'

  # 清理旧数据
  ssh ${USER}@${IP} 'rm -rf /opt/etcd/data; mkdir -p /opt/etcd/data; chmod 700 /opt/etcd/data'

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
# 第一步：看退出码和状态
systemctl status etcd

# 第二步：看完整日志
journalctl -u etcd -n 100 --no-pager

# 第三步：如果日志没有有用信息，前台运行看错误
/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
# 如果这条也没输出就退出，说明是配置文件问题，改用命令行参数方式

# 第四步：用命令行参数前台测试（以 node1 为例）
/opt/etcd/etcd \
  --name node1 \
  --data-dir /opt/etcd/data \
  --listen-client-urls http://192.168.0.168:2379,http://127.0.0.1:2379 \
  --listen-peer-urls http://192.168.0.168:2380 \
  --advertise-client-urls http://192.168.0.168:2379 \
  --initial-advertise-peer-urls http://192.168.0.168:2380 \
  --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 \
  --initial-cluster-state new \
  --initial-cluster-token etcd-cluster
```

### 问题 2：前台运行没有输出就退出

**最常见原因**：etcd 读取配置文件时格式错误导致静默退出。

**解决**：不用 yml 配置文件，改用本仓库提供的命令行参数 service 文件。

**如果还是没输出**：

```bash
# 确认二进制架构匹配
file /opt/etcd/etcd
uname -m

# 用 strace 追踪
strace -f -o /tmp/etcd-strace.log /opt/etcd/etcd --config-file /opt/etcd/etcd.yml
tail -50 /tmp/etcd-strace.log
```

### 问题 3：日志含 certificate / TLS / x509 错误

**常见信息**：`remote error: tls: bad certificate`、`certificate does not match`、`x509: certificate signed by unknown authority`

**原因**：证书配置问题。

**快速修复**：先用 HTTP 模式（方案 A），确认 etcd 本身没问题，再排查证书。

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

### 问题 4：日志含 conflict entry / already initialized

**原因**：data-dir 中有旧数据。当 `--initial-cluster-state new` 时，data-dir 必须为空。

**修复**：

```bash
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data
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
```

### 问题 6：data 目录权限警告

**警告信息**：`check file permission, directory /opt/etcd/data exist, but the permission is drwxr-xr-x. The recommended permission is -rwx`

**修复**：

```bash
chmod 700 /opt/etcd/data
systemctl restart etcd
```

### 问题 7：只有 1 个节点健康，其他节点报 connection refused

**原因**：节点间网络不通（2380 端口）。

**排查**：

```bash
# 从 node1 测试到 node2
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo "OK" || echo "FAIL"'
```

华为云 ECS 安全组需要放行：2379（客户端）、2380（节点间）。

### 问题 8：Nacos 连接 etcd 报证书错误

如果 Nacos 不带客户端证书连接 etcd，需要去掉 `--client-cert-auth`：

```bash
# 编辑 service 文件，删除 --client-cert-auth 这一行
# 保留 --peer-client-cert-auth
vi /etc/systemd/system/etcd.service

# 重新加载并重启
systemctl daemon-reload
systemctl restart etcd
```

### 问题 9：集群已存在成员，想重新初始化

```bash
# 三台机器都执行
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data

# 确保配置文件中 --initial-cluster-state new
systemctl start etcd
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
│       │
│       ├─ 前台也没输出 → 配置文件问题，改用命令行参数
│       └─ 前台有输出 → 根据输出排查
│
└─ Type=notify 失败 → 改 Type=simple
```

---

## 附录A：从 HTTP 切换到 HTTPS

如果先用方案 A（HTTP）跑通了集群，现在想升级到 HTTPS：

```bash
# 1. 确认证书 SAN（在三台分别执行）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# 2. 停止三台 etcd
systemctl stop etcd    # 三台都执行

# 3. 清理数据（必须！HTTP 切 HTTPS 相当于重建集群）
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data
chmod 700 /opt/etcd/data

# 4. 替换 service 文件（三台分别用对应的 https 版本）
# node1：
cp etcd.service.https.node1 /etc/systemd/system/etcd.service
# node2：
cp etcd.service.https.node2 /etc/systemd/system/etcd.service
# node3：
cp etcd.service.https.node3 /etc/systemd/system/etcd.service

# 5. 启动三台
systemctl daemon-reload
systemctl start etcd
systemctl status etcd

# 6. 验证（见第五节 HTTPS 验证部分）
```

> **注意**：HTTP 切换到 HTTPS 必须清空 data-dir 重新初始化。如果有重要数据需要保留，先备份：
> ```bash
> ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379 snapshot save /tmp/etcd-snapshot.db
> ```

---

## 附录B：配置字段速查表

### 命令行参数对照表

| 参数 | 说明 | 是否必须 |
|------|------|----------|
| `--name` | 节点名称，必须和 initial-cluster 中的 key 匹配 | **必须** |
| `--data-dir` | 数据存储目录 | **必须** |
| `--listen-client-urls` | 监听客户端请求的地址 | **必须** |
| `--listen-peer-urls` | 监听节点间通信的地址 | **必须** |
| `--advertise-client-urls` | 告知客户端的访问地址 | **必须** |
| `--initial-advertise-peer-urls` | 告知其他节点的通信地址 | **必须** |
| `--initial-cluster` | 集群成员列表 | 首次启动必须 |
| `--initial-cluster-state` | `new`（新建集群）或 `existing`（加入已有集群） | 首次启动必须 |
| `--initial-cluster-token` | 集群唯一标识 | 建议填写 |
| `--cert-file` | 服务端证书（HTTPS） | HTTPS 必须 |
| `--key-file` | 服务端私钥（HTTPS） | HTTPS 必须 |
| `--trusted-ca-file` | 客户端 CA 证书（HTTPS） | HTTPS 必须 |
| `--peer-cert-file` | 节点间通信证书（HTTPS） | HTTPS 必须 |
| `--peer-key-file` | 节点间通信私钥（HTTPS） | HTTPS 必须 |
| `--peer-trusted-ca-file` | 节点间 CA 证书（HTTPS） | HTTPS 必须 |
| `--client-cert-auth` | 要求客户端提供证书 | 可选，Nacos 不带证书时需去掉 |
| `--peer-client-cert-auth` | 要求节点间通信提供证书 | HTTPS 建议开启 |

### yml 配置字段对照表

| yml 字段 | 命令行参数 | 说明 |
|----------|-----------|------|
| `name` | `--name` | 节点名称 |
| `data-dir` | `--data-dir` | 数据目录 |
| `listen-client-urls` | `--listen-client-urls` | 客户端监听地址 |
| `listen-peer-urls` | `--listen-peer-urls` | 节点间监听地址 |
| `advertise-client-urls` | `--advertise-client-urls` | 客户端广播地址 |
| `initial-advertise-peer-urls` | `--initial-advertise-peer-urls` | 节点间广播地址 |
| `initial-cluster` | `--initial-cluster` | 集群成员列表 |
| `initial-cluster-state` | `--initial-cluster-state` | new 或 existing |
| `initial-cluster-token` | `--initial-cluster-token` | 集群标识 |
| `client-transport-security.cert-file` | `--cert-file` | 客户端证书 |
| `client-transport-security.key-file` | `--key-file` | 客户端私钥 |
| `client-transport-security.client-cert-auth` | `--client-cert-auth` | 客户端证书认证 |
| `client-transport-security.trusted-ca-file` | `--trusted-ca-file` | 客户端 CA |
| `peer-transport-security.cert-file` | `--peer-cert-file` | peer 证书 |
| `peer-transport-security.key-file` | `--peer-key-file` | peer 私钥 |
| `peer-transport-security.client-cert-auth` | `--peer-client-cert-auth` | peer 证书认证 |
| `peer-transport-security.trusted-ca-file` | `--peer-trusted-ca-file` | peer CA |