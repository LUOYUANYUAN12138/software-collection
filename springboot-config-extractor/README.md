# Spring Boot 配置提取工具

从 `application*.properties` 提取所有 `${KEY}` 配置项，按优先级从 deploy 目录取值，输出一个大 JSON。

## 功能

- 扫描 `resources` 目录下所有 `application*.properties` 文件
- 提取 `${KEY}` 和 `${KEY:default}` 配置项
- 按优先级从 `deploy` 目录下的 `service-config.txt` 取值
- 支持 `--test` 模式，用模拟数据自动验证所有场景
- 支持 `-v` 详细模式，显示每个 key 的取值来源
- 输出一个合并的 JSON 配置文件

## 取值优先级

```
default.meta > huawei.meta > huawei.intl.meta > default.prod > huawei.prod > huawei.intl.prod > dev > 默认值
```

| 优先级 | 目录 | 说明 |
|--------|------|------|
| 1 | `deploy/default.meta/` | 最通用 meta |
| 2 | `deploy/huawei.meta/` | 较通用 meta |
| 3 | `deploy/huawei.intl.meta/` | 特定 meta |
| 4 | `deploy/default.prod/` | 最通用 prod |
| 5 | `deploy/huawei.prod/` | 较通用 prod |
| 6 | `deploy/huawei.intl.prod/` | 特定 prod |
| 7 | `deploy/dev/` | 开发环境 |
| 8 | `${KEY:default}` 中的默认值 | 没有默认值则为空字符串 |

## 目录结构

```
项目根目录/
├── resources/
│   ├── application.properties
│   ├── application-dev.properties
│   ├── application-meta.properties
│   ├── application-huaweisre-prod.properties
│   ├── application-huaweisre-prod-meta.properties
│   ├── application-huaweisre-intl-prod.properties
│   ├── application-huaweisre-intl-prod-meta.properties
│   └── application-icsl.properties
└── deploy/
    ├── default.meta/
    │   └── service-config.txt
    ├── default.prod/
    │   └── service-config.txt
    ├── huawei.meta/
    │   └── service-config.txt
    ├── huawei.intl.meta/
    │   └── service-config.txt
    ├── huawei.prod/
    │   └── service-config.txt
    ├── huawei.intl.prod/
    │   └── service-config.txt
    └── dev/
        └── service-config.txt
```

## 使用方法

```bash
# 用模拟数据测试
python extract_config.py --test

# 详细模式，显示每个 key 的取值来源
python extract_config.py --test -v

# 实际提取项目配置（resources/ 和 deploy/ 与脚本同级）
python extract_config.py
```

## service-config.txt 格式

```properties
# 这是注释
DB_NAME=my_database
DB_HOST=10.0.0.1
DB_PORT=3306
REDIS_HOST=10.0.0.100
```

- 每行一个配置项，格式为 `KEY=VALUE`
- 支持 `#` 开头的注释行
- 空行会被跳过

## 依赖

- Python 3.6+
- 无第三方依赖，仅使用标准库

## 注意事项

1. Windows/Linux/macOS 都兼容
2. 读取文件使用 UTF-8 编码
3. 如果 deploy 目录下没有对应的子目录，会自动跳过
4. 没有默认值且 deploy 里也没有的配置项，值为空字符串 `""`
5. 配置项按字母排序输出