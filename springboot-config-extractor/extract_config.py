#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spring Boot 配置提取工具

功能：从 application*.properties 提取所有 ${KEY} 配置项，
      按优先级从 deploy 目录取值，输出一个大 JSON。

取值优先级：meta > prod > intl.prod > dev > 默认值

用法：python extract_config.py <项目根目录> [output.json]
示例：python extract_config.py . config.json

目录结构假设：
  项目根目录/
  ├── resources/
  │   ├── application.properties
  │   └── application-*.properties
  └── deploy/
      ├── huaweisre.meta/
      ├── huaweisre.prod/
      ├── huaweisre.intl.prod/
      └── dev/
"""

import os
import re
import json
import sys
from pathlib import Path
from collections import OrderedDict


def extract_properties_keys(resources_dir):
    """
    扫描 resources 目录下所有 application*.properties，
    提取 ${KEY} 和 ${KEY:default} 配置项。
    
    返回：{KEY: default_value or ""}
    """
    # 使用 [$] 匹配字面量的 $ 符号
    pattern = re.compile(r'[$]\{([^}:]+)(?::([^}]*))?\}')
    all_keys = OrderedDict()
    
    resources_path = Path(resources_dir)
    for prop_file in sorted(resources_path.glob("application*.properties")):
        with open(prop_file, "r", encoding="utf-8") as f:
            content = f.read()
        matches = pattern.findall(content)
        for key, default_value in matches:
            if key not in all_keys:
                all_keys[key] = default_value if default_value else ""
    
    return all_keys


def parse_service_config(config_file):
    """
    解析 service-config.txt 文件，格式为 KEY=VALUE
    返回：{KEY: VALUE}
    """
    config = {}
    if not os.path.exists(config_file):
        return config
    
    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    
    return config


def load_deploy_configs(deploy_dir):
    """
    按优先级加载 deploy 目录下的配置。
    
    优先级：meta > prod > intl.prod > dev
    返回：[(priority_name, config_dict), ...]
    """
    priority_order = [
        ("huaweisre.meta", "meta"),
        ("huaweisre.prod", "prod"),
        ("huaweisre.intl.prod", "intl.prod"),
        ("dev", "dev"),
    ]
    
    deploy_path = Path(deploy_dir)
    configs = []
    
    for dir_name, label in priority_order:
        config_file = deploy_path / dir_name / "service-config.txt"
        if config_file.exists():
            config = parse_service_config(str(config_file))
            configs.append((label, config))
            print(f"[INFO] 已加载 {dir_name}/service-config.txt ({len(config)} 个配置项)")
        else:
            print(f"[WARN] 未找到 {dir_name}/service-config.txt，跳过")
    
    return configs


def resolve_value(key, default_value, deploy_configs):
    """
    按优先级查找 key 的值。
    优先级：meta > prod > intl.prod > dev > 默认值
    """
    for label, config in deploy_configs:
        if key in config:
            return config[key]
    
    return default_value


def extract_config(resources_dir, deploy_dir):
    """
    主函数：提取配置并按优先级组装
    """
    all_keys = extract_properties_keys(resources_dir)
    print(f"\n[INFO] 从 properties 文件中提取到 {len(all_keys)} 个配置项")
    
    deploy_configs = load_deploy_configs(deploy_dir)
    
    final_config = OrderedDict()
    for key, default_value in all_keys.items():
        final_config[key] = resolve_value(key, default_value, deploy_configs)
    
    return final_config


def main():
    if len(sys.argv) < 2:
        print("用法：python extract_config.py <项目根目录> [output.json]")
        print("示例：python extract_config.py . config.json")
        print()
        print("目录结构假设：")
        print("  项目根目录/")
        print("  ├── resources/")
        print("  │   ├── application.properties")
        print("  │   └── application-*.properties")
        print("  └── deploy/")
        print("      ├── huaweisre.meta/")
        print("      ├── huaweisre.prod/")
        print("      ├── huaweisre.intl.prod/")
        print("      └── dev/")
        sys.exit(1)
    
    project_dir = Path(sys.argv[1]).resolve()
    output_file = sys.argv[2] if len(sys.argv) > 2 else "config.json"
    
    resources_dir = project_dir / "resources"
    deploy_dir = project_dir / "deploy"
    
    if not resources_dir.is_dir():
        print(f"[ERROR] resources 目录不存在: {resources_dir}")
        sys.exit(1)
    if not deploy_dir.is_dir():
        print(f"[ERROR] deploy 目录不存在: {deploy_dir}")
        sys.exit(1)
    
    print(f"[INFO] 项目目录: {project_dir}")
    print(f"[INFO] resources: {resources_dir}")
    print(f"[INFO] deploy: {deploy_dir}")
    
    final_config = extract_config(str(resources_dir), str(deploy_dir))
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_config, f, indent=2, ensure_ascii=False)
    
    print(f"\n[DONE] 配置已导出到: {output_file}")
    print(f"[DONE] 共 {len(final_config)} 个配置项")


if __name__ == "__main__":
    main()
