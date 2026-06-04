# dcm 服务连接 etcd 集群 — 证书配置方案

## 环境信息

| 项目 | 值 |
|------|-----|
| etcd 集群节点1 | **192.168.0.168** |
| etcd 集群节点2 | **192.168.0.145** |
| etcd 集群节点3 | **192.168.0.79** |
| etcd 端口 | 2379 (Client API) |
| 跳板机 | 1 台（同 VPC） |
| dcm 部署方式 | K8s Deployment（流水线 CI/CD 管理） |
| 网络互通 | ✅ 同 VPC，2379 端口已放通 |

---

## 问题背景

dcm 是 K8s 工作负载（Pod），需要连接 etcd 集群。etcd 开启了 TLS 客户端证书认证，dcm 没有证书无法连接，启动报错。

dcm 的 Deployment YAML 由 CI/CD 流水线管理，流水线构建机当前无法登录（/opt/cloud/ 路径在构建机上，不在 K8s 节点上）。

---

## 推荐方案：K8s Secret + VolumeMount

**核心思路**：把 etcd 客户端证书做成 K8s Secret，通过 volumeMount 挂载进 dcm 容器。不依赖构建机，不需要重建镜像。

---

### 步骤 1：在 etcd 节点上获取证书文件

SSH 到任一 etcd 节点（如 192.168.0.168），找到这三个文件：

```bash
# 通常在 etcd 配置目录下，路径取决于你的部署方式
ls /opt/etcd/ssl/   # 或 /etc/etcd/ssl/ 或你当初生成证书的目录

# 你需要的文件：
# ca.pem          # CA 根证书
# client.pem      # 客户端证书
# client-key.pem  # 客户端私钥
```

**注**：你当初用 http 部署（内网没配 TLS），如果 dcm 确实报证书错误，说明 etcd 配置后来改成了 https。去任一节点 `/opt/etcd/etcd.yml` 确认：

```bash
# 在 192.168.0.168 上
grep -E "client-transport-security|peer-transport-security|trusted-ca-file|cert-file|key-file" /opt/etcd/etcd.yml
```

如果输出有 `cert-file` 和 `key-file`，说明确实开了 TLS，证书就在那些路径下。

### 步骤 2：把证书传到能操作 kubectl 的机器上

```bash
# 从 etcd 节点 scp 到你的操作机
scp root@192.168.0.168:/path/to/ca.pem .
scp root@192.168.0.168:/path/to/client.pem .
scp root@192.168.0.168:/path/to/client-key.pem .
```

### 步骤 3：创建 K8s Secret

```bash
kubectl create secret generic etcd-client-certs \
  --from-file=ca.pem=./ca.pem \
  --from-file=client.pem=./client.pem \
  --from-file=client-key.pem=./client-key.pem \
  -n <namespace>
# 把 <namespace> 改成 dcm 实际所在的 namespace
```

验证：
```bash
kubectl get secret etcd-client-certs -n <namespace>
# 应该显示 3 个 data 条目
```

### 步骤 4：修改 dcm 的 Deployment YAML

在 dcm 的 Deployment（或 StatefulSet）模板中加入 volumeMounts 和 volumes：

```yaml
spec:
  template:
    spec:
      containers:
      - name: dcm                # 保持原有 name
        # ... 原有配置不动 ...
        volumeMounts:
        - name: etcd-certs        # 新增
          mountPath: /etc/etcd/certs
          readOnly: true
      volumes:                     # 新增
      - name: etcd-certs
        secret:
          secretName: etcd-client-certs
          defaultMode: 0400        # 私钥权限收紧
```

**⚠️ 关键**：这一步要改的是**流水线模板**，不是直接 `kubectl edit`（直接改会被下次流水线部署覆盖）。找你们管流水线的人，在 CI/CD 模板里加上这段。

### 步骤 5：修改 dcm 配置，指向挂载路径

dcm 的配置文件或环境变量里，etcd 连接配置改为：

```
etcd_endpoints: https://192.168.0.168:2379,https://192.168.0.145:2379,https://192.168.0.79:2379
etcd_ca:   /etc/etcd/certs/ca.pem
etcd_cert: /etc/etcd/certs/client.pem
etcd_key:  /etc/etcd/certs/client-key.pem
```

（如果 dcm 用环境变量配，对应改成 `ETCD_ENDPOINTS`、`ETCD_CA` 等）

### 步骤 6：部署并验证

```bash
# 触发流水线重新部署，或手动 apply
kubectl rollout restart deployment/dcm -n <namespace>

# 进容器验证证书挂载成功
kubectl exec -it <dcm-pod> -n <namespace> -- ls -la /etc/etcd/certs/
# 应该看到 ca.pem, client.pem, client-key.pem

# 如果容器里有 etcdctl，验证连通性
kubectl exec -it <dcm-pod> -n <namespace> -- etcdctl \
  --endpoints=https://192.168.0.168:2379 \
  --cacert=/etc/etcd/certs/ca.pem \
  --cert=/etc/etcd/certs/client.pem \
  --key=/etc/etcd/certs/client-key.pem \
  endpoint health

# 期望输出：192.168.0.168:2379 is healthy: successfully committed proposal
```

---

## 风险与回滚

| 风险 | 影响 | 应对 |
|------|------|------|
| 流水线模板改不了 | 方案无法落地 | 改用 ConfigMap+initContainer 方式，或临时 kubectl apply（但会被覆盖） |
| 证书过期 | dcm 连接失败 | 在 Secret 里更新证书，Pod 自动重新挂载（如果有滚动更新） |
| Secret 被删 | dcm Pod 启动失败 | 重新执行步骤 3 即可恢复 |
| 三个节点证书不一致 | 连部分节点失败 | etcd 集群用同一套 CA 签发，client 证书通用，不需要每个节点一份 |

**回滚**：
```bash
# 删 Secret
kubectl delete secret etcd-client-certs -n <namespace>

# 从 Deployment YAML 里删除 volumeMounts 和 volumes 部分

# 重启 dcm
kubectl rollout restart deployment/dcm -n <namespace>
```

---

## 备选方案：烤进 Docker 镜像（如果流水线模板能改）

如果你们流水线的构建机能操作，把证书 COPY 进镜像也行：

**Dockerfile 里加**：
```dockerfile
COPY ca.pem /etc/etcd/certs/ca.pem
COPY client.pem /etc/etcd/certs/client.pem
COPY client-key.pem /etc/etcd/certs/client-key.pem
```

**缺点**：证书泄露风险（镜像里包含私钥）、换证书要重建镜像。

---

## 需要你做的事

1. **去 192.168.0.168 上确认证书路径**（`grep cert-file /opt/etcd/etcd.yml`）
2. **告诉我 dcm 的 K8s namespace**（或者你自己在文档里替换）
3. **找管流水线的人改 Deployment 模板**（步骤 4 的 YAML 段直接给他）
