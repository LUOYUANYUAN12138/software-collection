# etcd 三节点集群部署指南

> 适用环境：华为云内网，三台机器 + 一台跳板机
> 节点 IP：192.168.0.168、192.168.0.145、192.168.0.79

---

## 一、前置条件

- 三台机器已安装 etcd 二进制（位于 `/opt/etcd/`）
- 三台机器网络互通（2379、2380 端口互通）
- 跳板机可 SSH 到三台机器

## 二、每台机器都执行（以下操作三台相同）

### 1. 链接二进制到 PATH

```bash
ln -s /opt/etcd/etcd /usr/local/bin/etcd

# 验证
etcd --version
```

### 2. 创建 systemd 服务文件

```bash
cat > /etc/systemd/system/etcd.service << 'EOF'
[Unit]
Description=etcd
After=network.target

[Service]
Type=notify
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

## 三、配置文件（每台不同）

配置文件路径：`/opt/etcd/etcd.yml`

### 168 节点

```yaml
name: 'node1'
advertise-client-urls: 'http://192.168.0.168:2379'
data-dir: /opt/etcd/data
initial-advertise-peer-urls: 'http://192.168.0.168:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: etcd-cluster
listen-client-urls: 'http://192.168.0.168:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://192.168.0.168:2380'
```

### 145 节点

```yaml
name: 'node2'
advertise-client-urls: 'http://192.168.0.145:2379'
data-dir: /opt/etcd/data
initial-advertise-peer-urls: 'http://192.168.0.145:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: etcd-cluster
listen-client-urls: 'http://192.168.0.145:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://192.168.0.145:2380'
```

### 79 节点

```yaml
name: 'node3'
advertise-client-urls: 'http://192.168.0.79:2379'
data-dir: /opt/etcd/data
initial-advertise-peer-urls: 'http://192.168.0.79:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: etcd-cluster
listen-client-urls: 'http://192.168.0.79:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://192.168.0.79:2380'
```

> **注意：** 原配置用的是 `https`，内网无证书需改为 `http`，否则启动失败。
> **注意：** `name` 每台必须不同，对应 `initial-cluster` 里的 node1/node2/node3。
> **注意：** 如果之前用 `https` 启动过且 data-dir 有残留数据，需要清空 data-dir：`rm -rf /opt/etcd/data/*`

## 四、启动集群

三台尽量同时执行：

```bash
systemctl daemon-reload
systemctl enable etcd
systemctl start etcd
systemctl status etcd
```

如果 status 不是 active，查看日志：

```bash
journalctl -u etcd -n 50
```

## 五、验证集群

任选一台执行：

```bash
# 查看集群成员
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 member list

# 检查健康状态
ETCDCTL_API=3 etcdctl --endpoints=http://192.168.0.168:2379,http://192.168.0.145:2379,http://192.168.0.79:2379 endpoint health
```

预期输出：
- member list 显示 3 个节点
- endpoint health 显示 3 个节点都是 healthy

## 六、快速分发脚本（跳板机执行）

如果你从跳板机操作，可以用这个脚本一次性把配置推送到三台：

```bash
#!/bin/bash
# 在跳板机上运行

NODES=("192.168.0.168" "192.168.0.145" "192.168.0.79")
NAMES=("node1" "node2" "node3")

for i in "${!NODES[@]}"; do
  IP=${NODES[$i]}
  NAME=${NAMES[$i]}
  
  echo "=== 配置 $NAME ($IP) ==="
  
  # 创建 systemd 服务
  ssh root@$IP 'cat > /etc/systemd/system/etcd.service << '"'"'EOF'"'"'
[Unit]
Description=etcd
After=network.target

[Service]
Type=notify
ExecStart=/opt/etcd/etcd --config-file /opt/etcd/etcd.yml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF'
  
  # 写入配置文件
  ssh root@$IP "cat > /opt/etcd/etcd.yml << EOF
name: '$NAME'
advertise-client-urls: 'http://$IP:2379'
data-dir: /opt/etcd/data
initial-advertise-peer-urls: 'http://$IP:2380'
initial-cluster: 'node1=http://192.168.0.168:2380,node2=http://192.168.0.145:2380,node3=http://192.168.0.79:2380'
initial-cluster-state: new
initial-cluster-token: etcd-cluster
listen-client-urls: 'http://$IP:2379,http://127.0.0.1:2379'
listen-peer-urls: 'http://$IP:2380'
EOF"
  
  # 链接二进制
  ssh root@$IP 'ln -sf /opt/etcd/etcd /usr/local/bin/etcd'
  
  echo "=== $NAME 配置完成 ==="
done

echo "=== 三台配置完成，现在去每台启动 ==="
echo "systemctl daemon-reload && systemctl enable etcd && systemctl start etcd && systemctl status etcd"
```

## 七、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 启动失败，日志报 certificate 错误 | 用了 https 但没证书 | 配置文件全部改 http |
| 启动失败，日志报 data dir 已有数据 | 之前启动过，data-dir 有残留 | `rm -rf /opt/etcd/data/*` |
| 启动失败，日志报 name 冲突 | 三台 name 一样 | 每台 name 改成 node1/node2/node3 |
| 集群只有 1 个成员健康 | 防火墙挡了 2380 | 开放 2379、2380 端口 |
| `initial-cluster-state: new` 报错 | 集群已初始化过 | 改成 `existing` 或清空 data-dir |
