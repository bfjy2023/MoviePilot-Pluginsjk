import hashlib
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import urllib3
from apscheduler.triggers.interval import IntervalTrigger
from urllib3.exceptions import InsecureRequestWarning

from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType

urllib3.disable_warnings(InsecureRequestWarning)


class ForumRssMonitor(_PluginBase):
    plugin_name = "论坛动态监控"
    plugin_desc = "监控论坛 RSS/Atom 动态和蜂巢(pting.club) API，默认推送最近 24 小时内的新帖。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.2.0"
    plugin_author = "jiangbkvir,bfjy"
    author_url = "https://github.com/jiangbkvir/MoviePilot-Plugins"
    plugin_config_prefix = "forumrssmonitor_"
    plugin_order = 40
    auth_level = 1

    DEFAULT_RSS_URLS = "https://invites.fun/atom/t/xxzx"
    DEFAULT_KEYWORDS = ""
    DEFAULT_RECENT_HOURS = 24
    DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
    MAX_HISTORY = 50
    REQUEST_TIMEOUT = 30
    DEFAULT_PTING_BASE_URL = "https://pting.club"

    _enabled = False
    _notify = True
    _run_once = False
    _interval = 10
    _recent_hours = DEFAULT_RECENT_HOURS
    _rss_urls = DEFAULT_RSS_URLS
    _cookie = ""
    _keywords = DEFAULT_KEYWORDS
    _pting_enabled = False
    _pting_cookie = ""
    _pting_csrf_token = ""
    _pting_base_url = DEFAULT_PTING_BASE_URL
    _clear_cache = False
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        self._interval = self.__safe_int(config.get("interval"), 10, min_value=1)
        self._recent_hours = self.__safe_int(config.get("recent_hours"), self.DEFAULT_RECENT_HOURS, min_value=1)
        self._rss_urls = (config.get("rss_urls") or self.DEFAULT_RSS_URLS).strip()
        self._cookie = str(config.get("cookie") or "").strip()
        self._keywords = str(config.get("keywords", self.DEFAULT_KEYWORDS) or "").strip()
        self._pting_enabled = bool(config.get("pting_enabled", False))
        self._pting_cookie = str(config.get("pting_cookie") or "").strip()
        self._pting_csrf_token = str(config.get("pting_csrf_token") or "").strip()
        self._pting_base_url = str(config.get("pting_base_url") or self.DEFAULT_PTING_BASE_URL).strip()
        self._clear_cache = bool(config.get("clear_cache", False))
        logger.info(
            f"论坛动态监控初始化完成：enabled={self._enabled}, interval={self._interval}, "
            f"notify={self._notify}, recent_hours={self._recent_hours}, "
            f"cookie={'已配置' if self._cookie else '未配置'}, feed_count={len(self.__rss_url_list())}, "
            f"pting_enabled={self._pting_enabled}, pting_cookie={'已配置' if self._pting_cookie else '未配置'}, "
            f"pting_csrf_token={'已配置' if self._pting_csrf_token else '未配置'}"
        )
        if self._clear_cache:
            self._clear_cache = False
            self.update_config({
                "enabled": self._enabled,
                "notify": self._notify,
                "run_once": False,
                "clear_cache": False,
                "interval": self._interval,
                "recent_hours": self._recent_hours,
                "rss_urls": self._rss_urls,
                "cookie": self._cookie,
                "keywords": self._keywords,
                "pting_enabled": self._pting_enabled,
                "pting_cookie": self._pting_cookie,
                "pting_csrf_token": self._pting_csrf_token,
                "pting_base_url": self._pting_base_url
            })
            logger.info("收到配置页清除缓冲请求，先清除再执行")
            self.clear_cache()
        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "notify": self._notify,
                "run_once": False,
                "clear_cache": False,
                "interval": self._interval,
                "recent_hours": self._recent_hours,
                "rss_urls": self._rss_urls,
                "cookie": self._cookie,
                "keywords": self._keywords,
                "pting_enabled": self._pting_enabled,
                "pting_cookie": self._pting_cookie,
                "pting_csrf_token": self._pting_csrf_token,
                "pting_base_url": self._pting_base_url
            })
            logger.info("收到配置页立即运行请求，后台启动 RSS 检查任务")
            threading.Thread(target=self.check_feeds, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/ForumRssMonitor/run",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即检查论坛 RSS",
                "description": "按当前插件配置立即检查一次论坛 RSS。"
            },
            {
                "path": "/ForumRssMonitor/clear_cache",
                "endpoint": self.clear_cache_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清除已推送缓冲",
                "description": "清除所有已推送的记录，下次检查时会重新推送。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        return [
            {
                "id": "ForumRssMonitor",
                "name": "论坛动态监控",
                "trigger": IntervalTrigger(minutes=max(self._interval, 1)),
                "func": self.check_feeds,
                "kwargs": {}
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"}
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "notify", "label": "发送通知"}
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "run_once",
                                            "label": "立即运行一次",
                                            "hint": "保存配置后执行，并自动关闭"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "clear_cache",
                                            "label": "清除推送缓冲",
                                            "hint": "清除已推送记录，保存后执行并自动关闭"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "cookie",
                                            "label": "请求 Cookie",
                                            "rows": 3,
                                            "placeholder": "可选：flarum_remember=...; flarum_session=...",
                                            "hint": "RSS 需要登录时填写浏览器 Cookie；留空则不带 Cookie"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "interval",
                                            "label": "检查间隔（分钟）",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "定时检查 RSS 的间隔"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "recent_hours",
                                            "label": "推送最近小时数",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "默认只推送最近 24 小时内的帖子"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "rss_urls",
                                            "label": "RSS 地址列表",
                                            "rows": 5,
                                            "placeholder": "一行一个 RSS/Atom 链接",
                                            "hint": "例如：https://invites.fun/atom/t/xxzx"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "keywords",
                                            "label": "关键词",
                                            "rows": 3,
                                            "placeholder": "可选：BTM,不可躺,开注",
                                            "hint": "逗号或换行分隔；留空则只按时间推送"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VDivider",
                        "props": {"class": "my-4"}
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-h6 mb-2"},
                        "text": "蜂巢 (pting.club) 配置"
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "pting_enabled",
                                            "label": "启用蜂巢监控",
                                            "hint": "启用后将通过 API 监控 pting.club 新帖"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "pting_cookie",
                                            "label": "蜂巢 Cookie",
                                            "rows": 4,
                                            "placeholder": "flarum_remember=...; flarum_session=...; acw_tc=...; cdn_sec_tc=...",
                                            "hint": "从浏览器复制完整的 Cookie 字符串"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "pting_csrf_token",
                                            "label": "CSRF Token",
                                            "placeholder": "从请求头 X-CSRF-Token 中获取",
                                            "hint": "浏览器开发者工具 -> Network -> 找到 API 请求 -> Headers -> X-CSRF-Token"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "class": "mt-2"
                        },
                        "text": "获取方式：登录 pting.club -> 打开浏览器开发者工具(F12) -> Network 选项卡 -> 刷新页面 -> 点击任意 api 请求 -> 复制 Request Headers 中的 Cookie 和 X-CSRF-Token 值。保存配置后点击「立即运行一次」测试连接。"
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "notify": self._notify,
            "run_once": False,
            "clear_cache": False,
            "interval": self._interval,
            "recent_hours": self._recent_hours,
            "rss_urls": self._rss_urls or self.DEFAULT_RSS_URLS,
            "cookie": self._cookie,
            "keywords": self._keywords,
            "pting_enabled": self._pting_enabled,
            "pting_cookie": self._pting_cookie,
            "pting_csrf_token": self._pting_csrf_token,
            "pting_base_url": self._pting_base_url or self.DEFAULT_PTING_BASE_URL
        }

    def get_page(self) -> List[dict]:
        records = self.__get_records()
        state = self.__get_state_data()
        errors = state.get("errors") or []
        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {"component": "VCardTitle", "text": "RSS 监控状态"},
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("RSS 源数量", len(self.__rss_url_list())),
                                    self.__info_col("最近检查", state.get("last_checked_at") or "-"),
                                    self.__info_col("最近推送", state.get("last_pushed_at") or "-"),
                                    self.__info_col("推送范围", f"最近 {self._recent_hours} 小时"),
                                    self.__info_col("Cookie", "已配置" if self._cookie else "未配置"),
                                    self.__info_col("关键词", self.__keyword_text())
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {"component": "VCardTitle", "text": "蜂巢 (pting.club) 监控状态"},
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("启用状态", "已启用" if self._pting_enabled else "未启用"),
                                    self.__info_col("Cookie", "已配置" if self._pting_cookie else "未配置"),
                                    self.__info_col("CSRF Token", "已配置" if self._pting_csrf_token else "未配置"),
                                    self.__info_col("站点地址", self._pting_base_url or "-")
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "component": "VDataTable",
                "props": {
                    "headers": [
                        {"title": "时间", "key": "date"},
                        {"title": "来源", "key": "source"},
                        {"title": "作者", "key": "author"},
                        {"title": "标题", "key": "title"},
                        {"title": "链接", "key": "link"}
                    ],
                    "items": records,
                    "items-per-page": 10,
                    "hide-default-footer": True,
                    "density": "compact"
                }
            },
            {
                "component": "VDivider",
                "props": {"class": "my-4"}
            },
            {
                "component": "div",
                "props": {"class": "text-h6 mb-2"},
                "text": "最近错误"
            },
            {
                "component": "VDataTable",
                "props": {
                    "headers": [
                        {"title": "时间", "key": "date"},
                        {"title": "来源", "key": "url"},
                        {"title": "错误", "key": "message"}
                    ],
                    "items": errors[-10:][::-1],
                    "items-per-page": 10,
                    "hide-default-footer": True,
                    "density": "compact"
                }
            }
        ]

    def stop_service(self):
        pass

    def run_once_api(self) -> Dict[str, Any]:
        if self._lock.locked():
            logger.warn("立即检查请求被忽略：已有 RSS 检查任务正在执行")
            return {"success": False, "message": "已有 RSS 检查任务正在执行"}
        logger.info("收到 API 立即检查请求，后台启动 RSS 检查任务")
        threading.Thread(target=self.check_feeds, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会按配置发送通知"}

    def clear_cache_api(self) -> Dict[str, Any]:
        logger.info("收到 API 清除缓冲请求")
        return self.clear_cache()

    def clear_cache(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=True, timeout=30):
            return {"success": False, "message": "等待检查任务超时，请稍后再试"}
        try:
            state = self.__get_state_data()
            state["seen"] = {}
            self.save_data("state", state)
            logger.info("已清除所有推送缓冲")
            return {"success": True, "message": "已清除所有推送缓冲，下次检查时将重新推送"}
        except Exception as err:
            logger.error(f"清除缓冲失败：{err}")
            return {"success": False, "message": f"清除失败：{str(err)}"}
        finally:
            self._lock.release()

    def check_feeds(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            logger.warn("RSS 检查任务启动失败：已有任务正在执行")
            return {"success": False, "message": "已有 RSS 检查任务正在执行"}
        try:
            urls = self.__rss_url_list()
            keywords = self.__keyword_list()
            cutoff_time = self.__now().astimezone(timezone.utc) - timedelta(hours=self._recent_hours)
            state = self.__get_state_data()
            seen = state.get("seen") or {}
            pushed_count = 0
            checked_count = 0
            logger.info(
                f"RSS 检查任务开始：feed_count={len(urls)}，recent_hours={self._recent_hours}，"
                f"cutoff={cutoff_time.isoformat()}，keywords={keywords or '未配置，仅按时间推送'}，"
                f"pting_enabled={self._pting_enabled}"
            )
            for url in urls:
                checked_count += 1
                feed_key = self.__feed_key(url)
                previous_seen = set(seen.get(feed_key) or [])
                try:
                    entries = self.__fetch_entries(url)
                except Exception as err:
                    self.__record_error(state, url, str(err))
                    logger.error(f"RSS 源检查失败：url={url}，错误={err}")
                    continue

                current_ids = [entry["id"] for entry in entries if entry.get("id")]
                new_entries = [
                    entry for entry in entries
                    if entry.get("id") and entry.get("id") not in previous_seen
                ]
                logger.info(
                    f"RSS 源解析完成：url={url}，entries={len(entries)}，"
                    f"new_entries={len(new_entries)}，first_run={not bool(previous_seen)}"
                )
                for entry in reversed(new_entries):
                    if not self.__is_recent_entry(entry, cutoff_time):
                        logger.info(f"跳过超出时间范围的 RSS 条目：entry={self.__to_log_text(entry)}")
                        continue
                    if not self.__match_keywords(entry, keywords):
                        logger.info(f"跳过未命中关键词的 RSS 条目：entry={self.__to_log_text(entry)}")
                        continue
                    pushed_count += 1
                    self.__send_notification(entry)
                    self.__save_record(entry)

                merged_seen = list(dict.fromkeys(current_ids + list(previous_seen)))[:300]
                seen[feed_key] = merged_seen

            if self._pting_enabled:
                pting_key = "pting_discussions"
                previous_pting_seen = set(seen.get(pting_key) or [])
                try:
                    pting_entries = self.__fetch_pting_discussions()
                    checked_count += 1
                except Exception as err:
                    self.__record_error(state, "pting.club", str(err))
                    logger.error(f"蜂巢 API 检查失败：错误={err}")
                    pting_entries = []

                current_pting_ids = [entry["id"] for entry in pting_entries if entry.get("id")]
                new_pting_entries = [
                    entry for entry in pting_entries
                    if entry.get("id") and entry.get("id") not in previous_pting_seen
                ]
                logger.info(
                    f"蜂巢 API 解析完成：entries={len(pting_entries)}，"
                    f"new_entries={len(new_pting_entries)}，first_run={not bool(previous_pting_seen)}"
                )
                for entry in reversed(new_pting_entries):
                    if not self.__is_recent_entry(entry, cutoff_time):
                        logger.info(f"跳过超出时间范围的蜂巢条目：entry={self.__to_log_text(entry)}")
                        continue
                    if not self.__match_keywords(entry, keywords):
                        logger.info(f"跳过未命中关键词的蜂巢条目：entry={self.__to_log_text(entry)}")
                        continue
                    pushed_count += 1
                    self.__send_notification(entry)
                    self.__save_record(entry)

                merged_pting_seen = list(dict.fromkeys(current_pting_ids + list(previous_pting_seen)))[:300]
                seen[pting_key] = merged_pting_seen

            state["seen"] = seen
            state["last_checked_at"] = self.__format_datetime(self.__now())
            if pushed_count:
                state["last_pushed_at"] = state["last_checked_at"]
            self.save_data("state", state)
            logger.info(f"RSS 检查任务结束：checked={checked_count}，pushed={pushed_count}")
            return {"success": True, "checked": checked_count, "pushed": pushed_count}
        finally:
            self._lock.release()

    def __fetch_entries(self, url: str) -> List[Dict[str, Any]]:
        headers = self.__request_headers(url)
        logger.info(
            f"请求 RSS 源：url={url}，referer={headers.get('referer') or '-'}，"
            f"cookie={'已配置' if self._cookie else '未配置'}"
        )
        response = requests.get(
            url,
            headers=headers,
            timeout=self.REQUEST_TIMEOUT,
            verify=False
        )
        logger.info(f"RSS 源响应：url={url}，status_code={response.status_code}")
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        try:
            root = ET.fromstring(response.text or "")
        except ET.ParseError as err:
            raise RuntimeError(f"RSS XML 解析失败：{err}") from err
        if self.__strip_ns(root.tag).lower() == "feed":
            return self.__parse_atom(url, root)
        if self.__strip_ns(root.tag).lower() == "rss":
            return self.__parse_rss(url, root)
        raise RuntimeError(f"不支持的 RSS 根节点：{root.tag}")

    def __request_headers(self, url: str) -> Dict[str, str]:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        referer = origin
        if parsed.netloc.replace("www.", "") == "invites.fun":
            referer = "https://invites.fun/t/xxzx"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,image/apng,*/*;q=0.8,"
                      "application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "max-age=0",
            "priority": "u=0, i",
            "referer": referer,
            "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        }
        if self._cookie:
            headers["cookie"] = self._cookie
        return headers

    def __pting_request_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Referer": f"{self._pting_base_url}/?sort=newest",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/147.0.0.0 Mobile Safari/537.36",
            "X-CSRF-Token": self._pting_csrf_token,
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"'
        }
        if self._pting_cookie:
            headers["Cookie"] = self._pting_cookie
        return headers

    def __fetch_pting_discussions(self) -> List[Dict[str, Any]]:
        if not self._pting_enabled:
            return []
        if not self._pting_cookie or not self._pting_csrf_token:
            raise RuntimeError("蜂巢(pting.club) Cookie 或 CSRF Token 未配置")
        url = f"{self._pting_base_url}/api/discussions"
        params = {
            "include": "user,lastPostedUser,tags,tags.parent,firstPost,recipientUsers,recipientGroups,lastPost",
            "sort": "-createdAt",
            "page[offset]": 0
        }
        headers = self.__pting_request_headers()
        logger.info(
            f"请求蜂巢 API：url={url}，cookie={'已配置' if self._pting_cookie else '未配置'}，"
            f"csrf_token={'已配置' if self._pting_csrf_token else '未配置'}"
        )
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=self.REQUEST_TIMEOUT,
            verify=False
        )
        logger.info(f"蜂巢 API 响应：url={url}，status_code={response.status_code}")
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as err:
            raise RuntimeError(f"蜂巢 API 响应解析失败：{err}") from err
        return self.__parse_pting_response(data)

    def __parse_pting_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries = []
        discussions = data.get("data") or []
        included = data.get("included") or []
        user_map = {}
        for item in included:
            if item.get("type") == "users":
                user_id = item.get("id")
                username = (item.get("attributes") or {}).get("username", "")
                if user_id and username:
                    user_map[user_id] = username
        for discussion in discussions:
            if discussion.get("type") != "discussions":
                continue
            attrs = discussion.get("attributes") or {}
            disc_id = discussion.get("id") or ""
            title = attrs.get("title") or "无标题"
            slug = attrs.get("slug") or ""
            created_at = attrs.get("createdAt") or ""
            last_posted_at = attrs.get("lastPostedAt") or ""
            comment_count = attrs.get("commentCount") or 0
            discussion_id = attrs.get("discussionId") or disc_id
            link = f"{self._pting_base_url}/d/{discussion_id}"
            if slug:
                link = f"{self._pting_base_url}/d/{discussion_id}-{slug}"
            relationships = discussion.get("relationships") or {}
            user_data = (relationships.get("user") or {}).get("data") or {}
            author_id = user_data.get("id") or ""
            author = user_map.get(author_id, "未知用户")
            tags = []
            tags_data = (relationships.get("tags") or {}).get("data") or []
            for tag_ref in tags_data:
                tag_id = tag_ref.get("id")
                for inc in included:
                    if inc.get("type") == "tags" and inc.get("id") == tag_id:
                        tag_name = (inc.get("attributes") or {}).get("name") or ""
                        if tag_name:
                            tags.append(tag_name)
                        break
            summary_parts = []
            if tags:
                summary_parts.append(f"标签：{'、'.join(tags)}")
            if comment_count:
                summary_parts.append(f"回复数：{comment_count}")
            first_post_data = (relationships.get("firstPost") or {}).get("data") or {}
            first_post_id = first_post_data.get("id")
            for inc in included:
                if inc.get("type") == "posts" and inc.get("id") == first_post_id:
                    post_content = (inc.get("attributes") or {}).get("contentHtml") or ""
                    if post_content:
                        clean_content = self.__clean_text(post_content)
                        if clean_content:
                            summary_parts.append(clean_content[:200])
                    break
            summary = " | ".join(summary_parts) if summary_parts else "-"
            entries.append({
                "id": f"pting_{disc_id}",
                "source": "pting.club",
                "feed_url": "api",
                "title": title,
                "link": link,
                "author": author,
                "published": last_posted_at or created_at,
                "summary": summary
            })
        return entries

    def __parse_atom(self, url: str, root: ET.Element) -> List[Dict[str, Any]]:
        entries = []
        source = self.__source_name(url)
        for node in self.__children_by_name(root, "entry"):
            entry_id = self.__text(node, "id") or self.__text(node, "link") or ""
            link = self.__atom_link(node) or entry_id
            title = self.__clean_text(self.__text(node, "title"))
            author = self.__clean_text(self.__text_path(node, ["author", "name"])) or "-"
            published = self.__text(node, "published") or self.__text(node, "updated") or "-"
            summary = self.__clean_text(self.__text(node, "summary") or self.__text(node, "content"))
            entries.append({
                "id": entry_id or link or title,
                "source": source,
                "feed_url": url,
                "title": title or "无标题",
                "link": link,
                "author": author,
                "published": published,
                "summary": summary
            })
        return entries

    def __parse_rss(self, url: str, root: ET.Element) -> List[Dict[str, Any]]:
        channel = next(iter(self.__children_by_name(root, "channel")), root)
        entries = []
        source = self.__source_name(url)
        for node in self.__children_by_name(channel, "item"):
            guid = self.__text(node, "guid")
            link = self.__text(node, "link") or guid or ""
            title = self.__clean_text(self.__text(node, "title"))
            author = self.__clean_text(
                self.__text(node, "author")
                or self.__text(node, "creator")
            ) or "-"
            published = self.__text(node, "pubDate") or self.__text(node, "published") or "-"
            summary = self.__clean_text(self.__text(node, "description") or self.__text(node, "summary"))
            entries.append({
                "id": guid or link or title,
                "source": source,
                "feed_url": url,
                "title": title or "无标题",
                "link": link,
                "author": author,
                "published": published,
                "summary": summary
            })
        return entries

    def __send_notification(self, entry: Dict[str, Any]):
        if not self._notify:
            logger.info(f"RSS 命中但通知未发送：发送通知开关未开启，entry={self.__to_log_text(entry)}")
            return
        title = f"【论坛动态监控】{entry.get('source')} - {entry.get('author')}"
        text = (
            f"标题：{entry.get('title')}\n"
            f"时间：{self.__format_datetime(entry.get('published'))}\n"
            f"摘要：{entry.get('summary') or '-'}\n"
            f"原文：{entry.get('link') or '-'}"
        )
        logger.info(f"准备发送 RSS 通知：title={title}，entry={self.__to_log_text(entry)}")
        self.post_message(
            mtype=NotificationType.Plugin,
            title=title,
            text=text,
            link=entry.get("link") or None
        )

    def __save_record(self, entry: Dict[str, Any]):
        records = self.__get_records()
        record = {
            "date": self.__format_datetime(self.__now()),
            "source": entry.get("source") or "-",
            "author": entry.get("author") or "-",
            "title": entry.get("title") or "无标题",
            "link": entry.get("link") or "",
            "id": entry.get("id") or "",
            "feed_url": entry.get("feed_url") or ""
        }
        records.insert(0, record)
        self.save_data("records", records[:self.MAX_HISTORY])

    def __record_error(self, state: Dict[str, Any], url: str, message: str):
        errors = state.get("errors") or []
        errors.append({
            "date": self.__format_datetime(self.__now()),
            "url": url,
            "message": message
        })
        state["errors"] = errors[-30:]

    def __rss_url_list(self) -> List[str]:
        urls = []
        for line in (self._rss_urls or "").splitlines():
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            urls.append(url)
        return list(dict.fromkeys(urls))

    def __keyword_list(self) -> List[str]:
        return [
            keyword.strip()
            for keyword in re.split(r"[,，\n]+", self._keywords or "")
            if keyword.strip()
        ]

    def __keyword_text(self) -> str:
        keywords = self.__keyword_list()
        return "、".join(keywords) if keywords else "未配置"

    def __is_recent_entry(self, entry: Dict[str, Any], cutoff_time: datetime) -> bool:
        published_at = self.__parse_datetime(entry.get("published"))
        if not published_at:
            logger.warn(f"RSS 条目缺少可解析发布时间，按新帖处理：entry={self.__to_log_text(entry)}")
            return True
        return published_at >= cutoff_time

    @staticmethod
    def __parse_datetime(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text or text == "-":
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, IndexError, OverflowError):
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def __now(cls) -> datetime:
        return datetime.now(cls.DISPLAY_TIMEZONE)

    @classmethod
    def __format_datetime(cls, value: Any) -> str:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = cls.__parse_datetime(value)
        if not parsed:
            return "-"
        return parsed.astimezone(cls.DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def __match_keywords(entry: Dict[str, Any], keywords: List[str]) -> bool:
        if not keywords:
            return True
        haystack = "\n".join([
            str(entry.get("title") or ""),
            str(entry.get("author") or ""),
            str(entry.get("summary") or "")
        ]).lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    def __get_records(self) -> List[Dict[str, Any]]:
        records = self.get_data("records") or []
        return records if isinstance(records, list) else []

    def __get_state_data(self) -> Dict[str, Any]:
        state = self.get_data("state") or {}
        return state if isinstance(state, dict) else {}

    @staticmethod
    def __info_col(label: str, value: Any) -> Dict[str, Any]:
        return {
            "component": "VCol",
            "props": {"cols": 6, "md": 3},
            "content": [
                {
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis"},
                    "text": label
                },
                {
                    "component": "div",
                    "props": {"class": "text-h6"},
                    "text": str(value if value not in [None, ""] else "-")
                }
            ]
        }

    @staticmethod
    def __source_name(url: str) -> str:
        host = urlparse(url).netloc or url
        return host.replace("www.", "")

    @staticmethod
    def __feed_key(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()

    @classmethod
    def __text(cls, node: ET.Element, name: str) -> str:
        for child in list(node):
            if cls.__strip_ns(child.tag).lower() == name.lower() or child.tag.lower() == name.lower():
                return (child.text or "").strip()
        return ""

    @classmethod
    def __text_path(cls, node: ET.Element, names: List[str]) -> str:
        current = node
        for name in names:
            found = None
            for child in list(current):
                if cls.__strip_ns(child.tag).lower() == name.lower():
                    found = child
                    break
            if found is None:
                return ""
            current = found
        return (current.text or "").strip()

    @classmethod
    def __children_by_name(cls, node: ET.Element, name: str) -> List[ET.Element]:
        return [
            child for child in list(node)
            if cls.__strip_ns(child.tag).lower() == name.lower()
        ]

    @classmethod
    def __atom_link(cls, node: ET.Element) -> str:
        fallback = ""
        for child in list(node):
            if cls.__strip_ns(child.tag).lower() != "link":
                continue
            href = (child.attrib.get("href") or "").strip()
            rel = (child.attrib.get("rel") or "").strip()
            if href and rel in ["", "alternate"]:
                return href
            if href and not fallback:
                fallback = href
        return fallback

    @staticmethod
    def __strip_ns(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def __clean_text(value: str) -> str:
        text = unescape(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]

    @staticmethod
    def __safe_int(value: Any, default: int, min_value: Optional[int] = None) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        if min_value is not None:
            number = max(number, min_value)
        return number

    @staticmethod
    def __to_log_text(value: Any, max_length: int = 3000) -> str:
        text = str(value)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_length:
            return f"{text[:max_length]}...（已截断，原始长度 {len(text)}）"
        return text
