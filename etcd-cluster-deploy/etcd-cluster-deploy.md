# etcd 三节点集群部署指南

> 适用环境：华为云 ECS 内网（EulerOS / openEuler）
> 节点 IP：192.168.0.168（node1）、192.168.0.145（node2）、192.168.0.79（node3）

---

## 一、前置检查

```bash
# 确认 etcd 二进制存在
/opt/etcd/etcd --version

# 链接到 PATH
ln -sf /opt/etcd/etcd /usr/local/bin/etcd
ln -sf /opt/etcd/etcdctl /usr/local/bin/etcdctl

# 确认架构匹配
file /opt/etcd/etcd
uname -m

# 确认端口没被占
ss -tlnp | grep -E '2379|2380'

# 如果有旧进程，杀掉
pkill etcd 2>/dev/null

# 确认端口互通（在每台机器上跑，所有结果都必须 OK）
bash -c 'echo > /dev/tcp/192.168.0.168/2379 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.168/2380 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.145/2379 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.145/2380 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.79/2379 && echo OK || echo FAIL'
bash -c 'echo > /dev/tcp/192.168.0.79/2380 && echo OK || echo FAIL'
```

---

## 二、方案 A：HTTP 模式（推荐先跑通）

> 以下命令直接在对应机器的终端上复制粘贴执行即可。

### node1（192.168.0.168）

```bash
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data

cat > /etc/systemd/system/etcd.service << 'EOF'
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
EOF

systemctl daemon-reload
systemctl enable etcd
systemctl start etcd
systemctl status etcd
```

### node2（192.168.0.145）

```bash
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data

cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node2 \
  --data-dir /opt/etcd/data \
  --listen-client-urls http://192.168.0.145:2379,http://127.0.0.1:2379 \
  --listen-peer-urls http://192.168.0.145:2380 \
  --advertise-client-urls http://192.168.0.145:2379 \
  --initial-advertise-peer-urls http://192.168.0.145:2380 \
  --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 \
  --initial-cluster-state new \
  --initial-cluster-token etcd-cluster
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable etcd
systemctl start etcd
systemctl status etcd
```

### node3（192.168.0.79）

```bash
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data

cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node3 \
  --data-dir /opt/etcd/data \
  --listen-client-urls http://192.168.0.79:2379,http://127.0.0.1:2379 \
  --listen-peer-urls http://192.168.0.79:2380 \
  --advertise-client-urls http://192.168.0.79:2379 \
  --initial-advertise-peer-urls http://192.168.0.79:2380 \
  --initial-cluster node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380 \
  --initial-cluster-state new \
  --initial-cluster-token etcd-cluster
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable etcd
systemctl start etcd
systemctl status etcd
```

### 验证（任意一台执行）

```bash
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 member list
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint health
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379 put testkey hello
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.145:2379 get testkey
```

预期：member list 显示 3 个节点，endpoint health 显示 3 个 healthy，get testkey 返回 hello。

---

## 三、方案 B：HTTPS 模式（TLS 加密）

> **前提**：先用方案 A 跑通集群，再切 HTTPS。
> **前提**：三台机器 `/opt/etcd/ssl/` 下已有 `chain.pem`、`server.pem`、`server.key`。

### 0. 检查证书（三台都跑）

```bash
# SAN 包含哪些 IP（必须包含本机 IP）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# 证书是否过期
openssl x509 -in /opt/etcd/ssl/server.pem -noout -dates

# 证书和私钥是否匹配（两条 md5 值必须一样）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -modulus | md5sum
openssl rsa -in /opt/etcd/ssl/server.key -noout -modulus | md5sum

# 证书链是否可信（输出应为 OK）
openssl verify -CAfile /opt/etcd/ssl/chain.pem /opt/etcd/ssl/server.pem

# 确认证书文件存在
ls -la /opt/etcd/ssl/
```

**SAN 判断：**
- 包含所有 3 个 IP → 三台可共用同一套证书，直接用
- 只包含 1 个 IP → 确认三台的 server.pem 内容不同（md5sum 不同），各自用自己的
- 不包含任何内网 IP → 证书不能用，需重新签发

### 1. 切换前先停掉所有节点并清数据

**三台都执行：**

```bash
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data
```

### 2. node1（192.168.0.168）

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node1 \
  --data-dir /opt/etcd/data \
  --listen-client-urls https://192.168.0.168:2379,https://127.0.0.1:2379 \
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
EOF

systemctl daemon-reload
systemctl start etcd
systemctl status etcd
```

### 3. node2（192.168.0.145）

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node2 \
  --data-dir /opt/etcd/data \
  --listen-client-urls https://192.168.0.145:2379,https://127.0.0.1:2379 \
  --listen-peer-urls https://192.168.0.145:2380 \
  --advertise-client-urls https://192.168.0.145:2379 \
  --initial-advertise-peer-urls https://192.168.0.145:2380 \
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
EOF

systemctl daemon-reload
systemctl start etcd
systemctl status etcd
```

### 4. node3（192.168.0.79）

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd service
After=network.target

[Service]
Type=simple
TimeoutStartSec=120
ExecStart=/opt/etcd/etcd \
  --name node3 \
  --data-dir /opt/etcd/data \
  --listen-client-urls https://192.168.0.79:2379,https://127.0.0.1:2379 \
  --listen-peer-urls https://192.168.0.79:2380 \
  --advertise-client-urls https://192.168.0.79:2379 \
  --initial-advertise-peer-urls https://192.168.0.79:2380 \
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
EOF

systemctl daemon-reload
systemctl start etcd
systemctl status etcd
```

### 5. 验证 HTTPS 集群（任意一台执行）

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

### 6. 如果 Nacos 连不上 etcd（客户端证书问题）

Nacos 不带客户端证书时，需要去掉 `--client-cert-auth`。编辑 service 文件：

```bash
# 三台都执行：删除 --client-cert-auth 那一行
sed -i '/--client-cert-auth$/d' /etc/systemd/system/etcd.service

# 重启
systemctl daemon-reload
systemctl restart etcd
```

> 注意：只删除 `--client-cert-auth`，保留 `--peer-client-cert-auth`。

---

## 四、排错手册

### 1. systemctl start etcd 报 exit-code

```bash
# 看退出码
systemctl status etcd

# 看日志
journalctl -u etcd -n 100 --no-pager
```

### 2. 前台运行没输出就退出

可能是 yml 配置文件问题。本方案已用命令行参数替代 yml，避免此问题。

如果命令行参数也退出没输出：

```bash
# 检查架构是否匹配
file /opt/etcd/etcd
uname -m

# 用 strace 追踪
strace -f -o /tmp/etcd.log /opt/etcd/etcd --name node1 --data-dir /opt/etcd/data --listen-client-urls http://127.0.0.1:2379
tail -50 /tmp/etcd.log
```

### 3. 日志含 certificate / TLS / x509 错误

先用方案 A（HTTP）跑通，再排查证书：

```bash
# 检查证书 SAN
openssl x509 -in /opt/etcd/ssl/server.pem -noout -text | grep -A1 "Subject Alternative Name"

# 检查证书过期
openssl x509 -in /opt/etcd/ssl/server.pem -noout -dates

# 证书私钥是否匹配（两条 md5 必须一样）
openssl x509 -in /opt/etcd/ssl/server.pem -noout -modulus | md5sum
openssl rsa -in /opt/etcd/ssl/server.key -noout -modulus | md5sum

# CA 是否信任证书
openssl verify -CAfile /opt/etcd/ssl/chain.pem /opt/etcd/ssl/server.pem
```

### 4. 日志含 conflict entry / already initialized

data-dir 有旧数据，和 `--initial-cluster-state new` 冲突：

```bash
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data
systemctl start etcd
```

### 5. 日志含 bind: address already in use

```bash
ss -tlnp | grep -E '2379|2380'
pkill etcd
systemctl restart etcd
```

### 6. data 目录权限警告

```
recommended permission is -rwx
```

```bash
chmod 700 /opt/etcd/data
systemctl restart etcd
```

### 7. Nacos 连 etcd 报证书错误

参见上方「如果 Nacos 连不上 etcd」部分，去掉 `--client-cert-auth`。

### 8. 只有一个节点健康，其他 connection refused

端口不通，检查安全组是否放行了 2379 和 2380。

### 9. 从 HTTP 切换到 HTTPS

```bash
# 三台都执行
systemctl stop etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data

# 然后用方案 B 的 cat 命令替换 service 文件，重启
```

> 注意：HTTP 切 HTTPS 必须清空 data-dir。

### 10. 完全重新初始化集群

```bash
# 三台都执行
systemctl stop etcd
pkill etcd
rm -rf /opt/etcd/data
mkdir -p /opt/etcd/data && chmod 700 /opt/etcd/data

# 重新用方案 A 或方案 B 的 cat 命令写入 service 文件
# 然后
systemctl daemon-reload
systemctl start etcd
```

---

## 五、关于 yml 配置文件

本方案使用命令行参数而非 yml 配置文件，原因：

- 部分环境下 etcd 读取 yml 配置文件会静默退出不报错
- 可能是 yml 引号格式、缩进、编码等问题
- 命令行参数方式稳定可靠，调试方便

如果仍想用 yml 配置文件，注意以下坑：

1. 确保 yml 文件使用 LF 换行（不是 CRLF/Windows 换行）
2. 确保 yml 中 `name` 字段必填，且和 `initial-cluster` 中的 key 一致
3. 确保 URL 两侧的引号一致（单引号或不用引号）
4. 清理 CRLF：`perl -i -pe 's/\r$//' /opt/etcd/etcd.yml`
5. 验证 yml 格式：`python3 -c "import yaml; yaml.safe_load(open('/opt/etcd/etcd.yml'))"`

---

## 六、配置参数速查

| 参数 | 说明 | 是否必须 |
|------|------|----------|
| `--name` | 节点名称，必须和 initial-cluster 中的 key 匹配 | **必须** |
| `--data-dir` | 数据目录 | **必须** |
| `--listen-client-urls` | 监听客户端地址 | **必须** |
| `--listen-peer-urls` | 监听节点间地址 | **必须** |
| `--advertise-client-urls` | 客户端广播地址 | **必须** |
| `--initial-advertise-peer-urls` | 节点间广播地址 | **必须** |
| `--initial-cluster` | 集群成员列表 | 首次必须 |
| `--initial-cluster-state` | `new` 或 `existing` | 首次必须 |
| `--initial-cluster-token` | 集群标识 | 建议填 |
| `--cert-file` | 服务端证书 | HTTPS 必须 |
| `--key-file` | 服务端私钥 | HTTPS 必须 |
| `--trusted-ca-file` | 客户端 CA | HTTPS 必须 |
| `--peer-cert-file` | peer 证书 | HTTPS 必须 |
| `--peer-key-file` | peer 私钥 | HTTPS 必须 |
| `--peer-trusted-ca-file` | peer CA | HTTPS 必须 |
| `--client-cert-auth` | 要求客户端证书 | 可选，Nacos 不带证书时去掉 |
| `--peer-client-cert-auth` | 要求 peer 证书 | HTTPS 建议开 |