# Spring Boot 配置提取工具

从 `application*.properties` 提取所有 `${KEY}` 配置项，按优先级从 deploy 目录取值，输出一个大 JSON。

## 功能

- 扫描 `resources` 目录下所有 `application*.properties` 文件
- 提取 `${KEY}` 和 `${KEY:default}` 配置项
- 按优先级从 `deploy` 目录下的 `service-config.txt` 取值
- 输出一个合并的 JSON 配置文件

## 取值优先级

```
meta > prod > intl.prod > dev > 默认值
```

具体来说：
1. `deploy/huaweisre.meta/service-config.txt`
2. `deploy/huaweisre.prod/service-config.txt`
3. `deploy/huaweisre.intl.prod/service-config.txt`
4. `deploy/dev/service-config.txt`
5. `${KEY:default}` 中的默认值（没有默认值则为空字符串）

## 目录结构假设

```
项目根目录/
├── resources/
│   ├── application.properties
│   ├── application-dev.properties
│   ├── application-huaweisre-prod.properties
│   └── ...
└── deploy/
    ├── huaweisre.meta/
    │   └── service-config.txt
    ├── huaweisre.prod/
    │   └── service-config.txt
    ├── huaweisre.intl.prod/
    │   └── service-config.txt
    └── dev/
        └── service-config.txt
```

## 使用方法

```bash
python extract_config.py <项目根目录> [output.json]
```

### 示例

```bash
# 在项目根目录下执行
python extract_config.py . config.json

# 指定其他目录
python extract_config.py /path/to/project output.json
```

## 输出示例

```json
{
  "DB_NAME": "meta_real_db",
  "LOG_LEVEL": "DEBUG",
  "DB_HOST": "10.0.0.50",
  "SERVER_PORT": "8080",
  "REDIS_HOST": "10.0.0.100",
  "REDIS_PORT": "6379"
}
```

## service-config.txt 格式

每个 `service-config.txt` 文件格式如下：

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

1. 脚本使用 `pathlib.Path`，Windows/Linux/macOS 都兼容
2. 读取文件使用 UTF-8 编码
3. 如果 deploy 目录下没有对应的子目录，会自动跳过
4. 没有默认值且 deploy 里也没有的配置项，值为空字符串 `""`
5. 配置项按首次出现的顺序保持（使用 OrderedDict）
