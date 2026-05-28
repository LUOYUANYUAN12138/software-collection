#!/usr/bin/env python3
"""
Extract Spring Boot ${KEY:default} placeholders from application*.properties
and resolve values from deploy/ directories by priority.

Priority (highest first):
  1. deploy/default.meta/service-config.txt
  2. deploy/huawei.meta/service-config.txt
  3. deploy/huawei.intl.meta/service-config.txt
  4. deploy/default.prod/service-config.txt
  5. deploy/huawei.prod/service-config.txt
  6. deploy/huawei.intl.prod/service-config.txt
  7. deploy/dev/service-config.txt
  8. Default value from ${KEY:default} syntax (empty string if no default)

Usage:
  python extract_config.py              # Extract from actual project
  python extract_config.py --test       # Run with simulated data
  python extract_config.py --test -v    # Verbose: show lookup trace
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

PLACEHOLDER_RE = re.compile(r'\$\{([^}]+)\}')
PRIORITY_DIRS = [
    "default.meta",
    "huawei.meta",
    "huawei.intl.meta",
    "default.prod",
    "huawei.prod",
    "huawei.intl.prod",
    "dev",
]


def parse_service_config(filepath: str) -> dict:
    result = {}
    if not os.path.isfile(filepath):
        return result
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
    return result


def extract_placeholders_from_properties(filepath: str) -> dict:
    result = {}
    if not os.path.isfile(filepath):
        return result
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for match in PLACEHOLDER_RE.finditer(line):
                inner = match.group(1)
                if ":" in inner:
                    key, _, default = inner.partition(":")
                    result[key.strip()] = {"key": key.strip(), "default": default}
                else:
                    result[inner.strip()] = {"key": inner.strip(), "default": ""}
    return result


def resolve_value(key: str, default: str, deploy_base: str, priority_dirs: list[str], verbose: bool = False) -> str:
    for dir_name in priority_dirs:
        config_path = os.path.join(deploy_base, dir_name, "service-config.txt")
        config = parse_service_config(config_path)
        if key in config:
            if verbose:
                print(f"  {key} -> found in {dir_name} = {config[key]}")
            return config[key]
    if verbose:
        if default:
            print(f"  {key} -> using default = {default}")
        else:
            print(f"  {key} -> not found anywhere, value is empty string")
    return default


def scan_properties(resources_dir: str) -> dict:
    all_placeholders = {}
    if not os.path.isdir(resources_dir):
        print(f"Warning: resources directory not found: {resources_dir}", file=sys.stderr)
        return all_placeholders
    for fname in sorted(os.listdir(resources_dir)):
        if fname.startswith("application") and fname.endswith(".properties"):
            fpath = os.path.join(resources_dir, fname)
            placeholders = extract_placeholders_from_properties(fpath)
            for key, info in placeholders.items():
                if key not in all_placeholders:
                    all_placeholders[key] = info
                elif all_placeholders[key]["default"] == "" and info["default"] != "":
                    all_placeholders[key] = info
    return all_placeholders


def extract_config(resources_dir: str, deploy_dir: str, verbose: bool = False) -> dict:
    placeholders = scan_properties(resources_dir)
    result = {}
    active_priority_dirs = []
    for d in PRIORITY_DIRS:
        full = os.path.join(deploy_dir, d, "service-config.txt")
        if os.path.isfile(full):
            active_priority_dirs.append(d)
    if verbose:
        print(f"Active deploy dirs (in priority order): {active_priority_dirs}")
    for key in sorted(placeholders.keys()):
        default = placeholders[key]["default"]
        result[key] = resolve_value(key, default, deploy_dir, active_priority_dirs, verbose)
    return result


# ── Test data ──────────────────────────────────────────────────────────────

TEST_DATA = {
    "resources/application.properties": r"""# Base config
spring.datasource.url=jdbc:mysql://localhost:3306/${DB_NAME:root_db}
spring.datasource.username=${DB_USER:root}
spring.datasource.password=${DB_PASS:}
server.port=${APP_PORT:8080}
redis.host=${REDIS_HOST}
redis.port=${REDIS_PORT:6379}
feature.flag.enabled=${FEATURE_ENABLED:false}
""",
    "resources/application-dev.properties": r"""spring.datasource.url=jdbc:mysql://localhost:3306/${DB_NAME:root_db}
server.port=${APP_PORT:8081}
debug.mode=${DEBUG_MODE:true}
""",
    "resources/application-meta.properties": r"""meta.service.name=${SERVICE_NAME:default-service}
meta.service.version=${SERVICE_VERSION:1.0.0}
""",
    "resources/application-huaweisre-prod.properties": r"""spring.datasource.url=jdbc:mysql://${DB_HOST:localhost}:3306/${DB_NAME:root_db}
spring.datasource.password=${DB_PASS}
monitor.interval=${MONITOR_INTERVAL:30}
""",
    "resources/application-huaweisre-prod-meta.properties": r"""monitor.interval=${MONITOR_INTERVAL:60}
meta.logging.level=${LOG_LEVEL:INFO}
""",
    "resources/application-huaweisre-intl-prod.properties": r"""spring.datasource.url=jdbc:mysql://${DB_HOST:intl-host}:3306/${DB_NAME}
i18n.locale=${I18N_LOCALE:en_US}
""",
    "resources/application-huaweisre-intl-prod-meta.properties": r"""i18n.locale=${I18N_LOCALE:zh_CN}
meta.region=${REGION:ap-southeast}
""",
    "resources/application-icsl.properties": r"""icsl.endpoint=${ICSL_ENDPOINT}
icsl.timeout=${ICSL_TIMEOUT:5000}
""",
    # ── Deploy directories ──
    "deploy/default.meta/service-config.txt": """\
# default.meta - most generic
SERVICE_NAME=default-service-from-meta
LOG_LEVEL=WARN
REDIS_PORT=6380
""",
    "deploy/huawei.meta/service-config.txt": """\
# huawei.meta
SERVICE_NAME=huawei-service-from-meta
DB_PASS=huawei_meta_password
FEATURE_ENABLED=true
""",
    "deploy/huawei.intl.meta/service-config.txt": """\
# huawei.intl.meta
I18N_LOCALE=en_GB
REGION=eu-west
""",
    "deploy/default.prod/service-config.txt": """\
# default.prod
APP_PORT=80
DB_HOST=prod-db-host
MONITOR_INTERVAL=120
""",
    "deploy/huawei.prod/service-config.txt": """\
# huawei.prod
DB_HOST=huawei-prod-db-host
DB_PASS=huawei_prod_password
REDIS_HOST=huawei-prod-redis
""",
    "deploy/huawei.intl.prod/service-config.txt": """\
# huawei.intl.prod
DB_HOST=intl-prod-db-host
ICSL_TIMEOUT=10000
""",
    "deploy/dev/service-config.txt": """\
# dev
DB_NAME=dev_database
DB_USER=dev_user
DB_PASS=dev_password
REDIS_HOST=dev-redis
REDIS_PORT=6379
DEBUG_MODE=false
APP_PORT=8081
""",
}


def create_test_env(base_dir: str):
    for rel_path, content in TEST_DATA.items():
        fpath = os.path.join(base_dir, rel_path)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)


def run_tests(verbose: bool = False):
    tmpdir = tempfile.mkdtemp(prefix="extract_config_test_")
    try:
        create_test_env(tmpdir)
        resources_dir = os.path.join(tmpdir, "resources")
        deploy_dir = os.path.join(tmpdir, "deploy")
        result = extract_config(resources_dir, deploy_dir, verbose=verbose)

        expected = {
            # DB_NAME: not in meta, not in prod, found in dev
            "DB_NAME": "dev_database",
            # DB_USER: not in meta, not in prod, found in dev
            "DB_USER": "dev_user",
            # DB_PASS: huawei.meta has it (priority higher than dev)
            "DB_PASS": "huawei_meta_password",
            # APP_PORT: default.prod has it (priority 4, higher than dev)
            "APP_PORT": "80",
            # REDIS_HOST: not in any meta, found in huawei.prod (priority 5)
            "REDIS_HOST": "huawei-prod-redis",
            # REDIS_PORT: default.meta has it (priority 1)
            "REDIS_PORT": "6380",
            # FEATURE_ENABLED: huawei.meta has it (priority 2)
            "FEATURE_ENABLED": "true",
            # SERVICE_NAME: default.meta has it (priority 1)
            "SERVICE_NAME": "default-service-from-meta",
            # SERVICE_VERSION: not in any deploy dir, use default from properties
            "SERVICE_VERSION": "1.0.0",
            # DB_HOST: default.prod has it (priority 4)
            "DB_HOST": "prod-db-host",
            # MONITOR_INTERVAL: default.prod has 120 (priority 4)
            "MONITOR_INTERVAL": "120",
            # LOG_LEVEL: default.meta has WARN (priority 1)
            "LOG_LEVEL": "WARN",
            # I18N_LOCALE: default.meta doesn't have it, huawei.meta doesn't,
            # huawei.intl.meta has en_GB (priority 3)
            "I18N_LOCALE": "en_GB",
            # REGION: huawei.intl.meta has eu-west (priority 3)
            "REGION": "eu-west",
            # ICSL_ENDPOINT: not in any deploy dir, no default -> empty
            "ICSL_ENDPOINT": "",
            # ICSL_TIMEOUT: not in meta, not in prod dirs except huawei.intl.prod (priority 6)
            "ICSL_TIMEOUT": "10000",
            # DEBUG_MODE: not in meta, not in prod, in dev (priority 7)
            "DEBUG_MODE": "false",
        }

        lines = []
        passed = 0
        failed = 0
        for key in sorted(set(list(expected.keys()) + list(result.keys()))):
            exp = expected.get(key, "<MISSING_IN_EXPECTED>")
            got = result.get(key, "<MISSING_IN_RESULT>")
            status = "PASS" if exp == got else "FAIL"
            if status == "PASS":
                passed += 1
            else:
                failed += 1
            lines.append(f"  [{status}] {key}: expected={exp!r}, got={got!r}")

        print(f"\n{'='*60}")
        print(f"Test results: {passed} passed, {failed} failed")
        print(f"{'='*60}")
        for line in lines:
            print(line)

        print(f"\nOutput JSON:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        if failed > 0:
            print(f"\n!!! {failed} tests FAILED !!!")
            return False
        else:
            print(f"\nAll {passed} tests PASSED!")
            return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    test_mode = "--test" in sys.argv

    if test_mode:
        success = run_tests(verbose=verbose)
        sys.exit(0 if success else 1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    resources_dir = os.path.join(script_dir, "resources")
    deploy_dir = os.path.join(script_dir, "deploy")

    if not os.path.isdir(resources_dir):
        print(f"Error: resources directory not found: {resources_dir}", file=sys.stderr)
        sys.exit(1)

    result = extract_config(resources_dir, deploy_dir, verbose=verbose)

    output_path = os.path.join(script_dir, "config_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Output written to: {output_path}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()