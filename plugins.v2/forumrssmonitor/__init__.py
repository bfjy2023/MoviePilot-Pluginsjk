import hashlib
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
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
    plugin_desc = "监控论坛 RSS/Atom 动态，并按关键词推送新帖。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "jiangbkvir,bfjy"
    author_url = "https://github.com/jiangbkvir/MoviePilot-Plugins"
    plugin_config_prefix = "forumrssmonitor_"
    plugin_order = 40
    auth_level = 1

    DEFAULT_RSS_URLS = "https://invites.fun/atom/t/xxzx"
    DEFAULT_KEYWORDS = "BTM,不可躺,开注"
    MAX_HISTORY = 50
    REQUEST_TIMEOUT = 30

    _enabled = False
    _notify = True
    _run_once = False
    _interval = 10
    _rss_urls = DEFAULT_RSS_URLS
    _keywords = DEFAULT_KEYWORDS
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        self._interval = self.__safe_int(config.get("interval"), 10, min_value=1)
        self._rss_urls = (config.get("rss_urls") or self.DEFAULT_RSS_URLS).strip()
        self._keywords = (config.get("keywords") or self.DEFAULT_KEYWORDS).strip()
        logger.info(
            f"论坛动态监控初始化完成：enabled={self._enabled}, interval={self._interval}, "
            f"notify={self._notify}, feed_count={len(self.__rss_url_list())}"
        )
        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "notify": self._notify,
                "run_once": False,
                "interval": self._interval,
                "rss_urls": self._rss_urls,
                "keywords": self._keywords
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
                                            "placeholder": "BTM,不可躺,开注",
                                            "hint": "逗号或换行分隔；留空则推送全部新条目"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "notify": self._notify,
            "run_once": False,
            "interval": self._interval,
            "rss_urls": self._rss_urls or self.DEFAULT_RSS_URLS,
            "keywords": self._keywords
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
                                    self.__info_col("关键词", self.__keyword_text())
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
                        {"title": "RSS", "key": "url"},
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

    def check_feeds(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            logger.warn("RSS 检查任务启动失败：已有任务正在执行")
            return {"success": False, "message": "已有 RSS 检查任务正在执行"}
        try:
            urls = self.__rss_url_list()
            keywords = self.__keyword_list()
            state = self.__get_state_data()
            seen = state.get("seen") or {}
            pushed_count = 0
            checked_count = 0
            logger.info(f"RSS 检查任务开始：feed_count={len(urls)}，keywords={keywords or '全部推送'}")
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
                    if not self.__match_keywords(entry, keywords):
                        continue
                    pushed_count += 1
                    self.__send_notification(entry)
                    self.__save_record(entry)

                merged_seen = list(dict.fromkeys(current_ids + list(previous_seen)))[:300]
                seen[feed_key] = merged_seen

            state["seen"] = seen
            state["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if pushed_count:
                state["last_pushed_at"] = state["last_checked_at"]
            self.save_data("state", state)
            logger.info(f"RSS 检查任务结束：checked={checked_count}，pushed={pushed_count}")
            return {"success": True, "checked": checked_count, "pushed": pushed_count}
        finally:
            self._lock.release()

    def __fetch_entries(self, url: str) -> List[Dict[str, Any]]:
        response = requests.get(
            url,
            headers={
                "accept": "application/atom+xml,application/rss+xml,application/xml,text/xml,*/*",
                "user-agent": "Mozilla/5.0 (MoviePilot ForumRssMonitor)"
            },
            timeout=self.REQUEST_TIMEOUT,
            verify=False
        )
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
            f"时间：{entry.get('published') or '-'}\n"
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
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
        return "、".join(keywords) if keywords else "全部"

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
