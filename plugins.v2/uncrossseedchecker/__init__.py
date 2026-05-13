import re
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.utils.string import StringUtils


class UnCrossSeedChecker(_PluginBase):
    plugin_name = "未辅种检查器"
    plugin_desc = "检查下载器中指定站点的种子是否已辅种到其他站点"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "jiangbkvir,bfjy"
    author_url = "https://github.com/jiangbkvir/MoviePilot-Plugins"
    plugin_config_prefix = "uncrossseedchecker_"
    plugin_order = 50
    auth_level = 1

    _enabled = False
    _notify = True
    _run_once = False
    _downloader = ""
    _site = ""
    _min_size = 0
    _downloader_options: List[dict] = []
    _site_options: List[dict] = []
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        self._downloader = str(config.get("downloader") or "").strip()
        self._site = str(config.get("site") or "").strip()
        self._min_size = self.__safe_int(config.get("min_size"), 0, min_value=0)
        self._downloader_options = self.__build_downloader_options()
        self._site_options = self.__build_site_options()
        logger.info(
            f"未辅种检查器初始化完成：enabled={self._enabled}, "
            f"downloader={self._downloader or '未选择'}, "
            f"site={self._site or '未选择'}, min_size={self._min_size}GB"
        )
        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "notify": self._notify,
                "run_once": False,
                "downloader": self._downloader,
                "site": self._site,
                "min_size": self._min_size,
            })
            logger.info("收到配置页立即运行请求，后台启动未辅种检查任务")
            threading.Thread(target=self.run_check, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/uncross_seed_check",
                "event": EventType.PluginAction,
                "desc": "检查未辅种种子",
                "category": "站点",
                "data": {
                    "action": "uncross_seed_check"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/UnCrossSeedChecker/run",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行未辅种检查",
                "description": "按当前插件配置立即执行一次未辅种检查。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        return []

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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "downloader",
                                            "label": "下载器",
                                            "items": self._downloader_options,
                                            "placeholder": "请选择下载器"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "site",
                                            "label": "检查站点",
                                            "items": self._site_options,
                                            "placeholder": "请选择要检查的站点"
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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "min_size",
                                            "label": "最小种子大小 (GB)",
                                            "type": "number",
                                            "min": 0,
                                            "hint": "过滤掉小于此大小的种子，0 表示不过滤"
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
            "downloader": self._downloader,
            "site": self._site,
            "min_size": self._min_size,
        }

    def get_page(self) -> List[dict]:
        results = self.__get_results()
        un_cross_seeded = results.get("un_cross_seeded") or []
        cross_seeded = results.get("cross_seeded") or []
        stats = results.get("stats") or {}
        site_name = results.get("site_name") or self._site or "-"
        un_rows = []
        for t in un_cross_seeded:
            c = t.get("comment") or ""
            un_rows.append({
                "name": str(t.get("name") or ""),
                "size_text": str(t.get("size_text") or "-"),
                "available_sites": str(t.get("available_sites") or "-"),
                "available_sites_list": t.get("available_sites_list") or [],
                "duplicate_count": int(t.get("duplicate_count") or 1),
                "link": str(c) if str(c).startswith("http") else "",
            })
        cs_rows = []
        for t in cross_seeded:
            c = t.get("comment") or ""
            cs_rows.append({
                "name": str(t.get("name") or ""),
                "size_text": str(t.get("size_text") or "-"),
                "cross_seeded_sites": str(t.get("cross_seeded_sites") or "-"),
                "cross_seeded_sites_list": t.get("cross_seeded_sites_list") or [],
                "duplicate_count": int(t.get("duplicate_count") or 1),
                "link": str(c) if str(c).startswith("http") else "",
            })
        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {"component": "VCardTitle", "text": "未辅种检查结果"},
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("检查站点", site_name),
                                    self.__info_col("下载器种子数", stats.get("raw_total", 0)),
                                    self.__info_col("去重后内容数", stats.get("unique_total", 0)),
                                    self.__info_col("涉及站点数", stats.get("site_count", 0)),
                                ]
                            },
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("已有该站点", stats.get("cross_seeded_count", 0)),
                                    self.__info_col("未有该站点", stats.get("un_cross_seeded_count", 0)),
                                    self.__info_col("检查时间", results.get("checked_at") or "-"),
                                    self.__info_col("下载器", results.get("downloader") or "-"),
                                ]
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
                        "props": {"cols": 12, "md": 6},
                        "content": [
                            {
                                "component": "VCard",
                                "props": {"variant": "outlined"},
                                "content": [
                                    {"component": "VCardTitle", "text": f"未有该站点 - 可去发种 ({len(un_rows)})"},
                                    {
                                        "component": "VCardText",
                                        "props": {"style": "max-height:500px;overflow-y:auto;"},
                                        "content": self.__build_list(un_rows)
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 6},
                        "content": [
                            {
                                "component": "VCard",
                                "props": {"variant": "outlined"},
                                "content": [
                                    {"component": "VCardTitle", "text": f"已有该站点 ({len(cs_rows)})"},
                                    {
                                        "component": "VCardText",
                                        "props": {"style": "max-height:500px;overflow-y:auto;"},
                                        "content": self.__build_list(cs_rows, show_cross=True)
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        pass

    def __build_list(self, rows: list, show_cross: bool = False) -> list:
        if not rows:
            return [{"component": "div", "props": {"class": "text-body-2"}, "text": "暂无数据"}]
        items = []
        for r in rows:
            if show_cross:
                site_list = r.get("cross_seeded_sites_list") or []
            else:
                site_list = r.get("available_sites_list") or []
            chips = []
            for s in site_list:
                url = s.get("url") or ""
                chip_props = {"size": "small", "class": "ma-1", "variant": "tonal", "color": "primary"}
                if url:
                    chip_props["href"] = url
                    chip_props["target"] = "_blank"
                chips.append({
                    "component": "VChip",
                    "props": chip_props,
                    "text": s.get("name") or ""
                })
            item_content = [
                {
                    "component": "VListItemTitle",
                    "text": r.get("name") or "-"
                },
                {
                    "component": "VListItemSubtitle",
                    "content": [
                        {"component": "span", "text": f"大小：{r.get('size_text', '-')}"},
                    ]
                },
            ]
            if chips:
                item_content.append({
                    "component": "div",
                    "props": {"class": "mt-1"},
                    "content": chips
                })
            item = {
                "component": "VListItem",
                "content": item_content
            }
            link = r.get("link") or ""
            if link:
                item["props"] = {"href": link, "target": "_blank"}
            items.append(item)
            items.append({"component": "VDivider"})
        return [{"component": "VList", "props": {"lines": "two"}, "content": items}]

    def run_once_api(self) -> Dict[str, Any]:
        if self._lock.locked():
            logger.warn("立即检查请求被忽略：已有检查任务正在执行")
            return {"success": False, "message": "已有检查任务正在执行"}
        logger.info("收到 API 立即检查请求，后台启动未辅种检查任务")
        threading.Thread(target=self.run_check, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会按配置发送通知"}

    @eventmanager.register(EventType.PluginAction)
    def run_once_command(self, event: Event = None):
        event_data = event.event_data if event else {}
        if not event_data or event_data.get("action") != "uncross_seed_check":
            return
        channel = event_data.get("channel")
        userid = event_data.get("user")
        if self._lock.locked():
            logger.warn("TG 命令立即检查请求被忽略：已有检查任务正在执行")
            self.post_message(
                channel=channel,
                userid=userid,
                mtype=NotificationType.Plugin,
                title="【未辅种检查器】",
                text="已有检查任务正在执行，请等待当前任务结束。"
            )
            return
        logger.info("收到 TG 命令立即检查请求，后台启动未辅种检查任务")
        threading.Thread(target=self.run_check, daemon=True).start()
        self.post_message(
            channel=channel,
            userid=userid,
            mtype=NotificationType.Plugin,
            title="【未辅种检查器】",
            text="任务已开始，完成后会按配置发送通知。"
        )

    def run_check(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            logger.warn("检查任务启动失败：已有任务正在执行")
            return {"success": False, "message": "已有检查任务正在执行"}
        try:
            if not self._downloader:
                logger.warn("检查任务终止：未选择下载器")
                return {"success": False, "message": "请先选择下载器"}
            if not self._site:
                logger.warn("检查任务终止：未选择站点")
                return {"success": False, "message": "请先选择检查站点"}

            site_display_name = self._site
            try:
                site = SiteOper().get_by_domain(self._site)
                if site:
                    site_display_name = site.name
            except Exception:
                pass

            target_site_title = None
            for opt in self._site_options:
                if opt.get("value") == self._site:
                    target_site_title = opt.get("title")
                    break

            logger.info(
                f"未辅种检查任务开始：downloader={self._downloader}, "
                f"site={site_display_name}({self._site}), min_size={self._min_size}GB"
            )

            all_torrents = self.__get_all_torrents()
            if all_torrents is None:
                logger.warn("检查任务终止：无法获取种子列表")
                return {"success": False, "message": "无法获取下载器种子列表"}

            logger.info(f"获取到 {len(all_torrents)} 个种子")

            all_sites = set()
            for t in all_torrents:
                site_name = self.__identify_site(t["trackers"])
                if site_name:
                    all_sites.add(site_name)
                t["site_name"] = site_name or "未知站点"
                t["size_text"] = self.__format_size(t.get("size", 0))
                t["added_on_text"] = self.__format_timestamp(t.get("added_on"))
                tracker_domain = self.__get_primary_tracker_domain(t["trackers"])
                t["tracker_domain"] = tracker_domain or "-"

            site_url_map = {}
            for opt in self._site_options:
                site_url_map[opt.get("title")] = f"https://{opt.get('value')}"

            content_map = {}
            for t in all_torrents:
                if self._min_size > 0 and t.get("size", 0) < self._min_size * 1024 * 1024 * 1024:
                    continue
                key = self.__content_key(t)
                if key not in content_map:
                    content_map[key] = {"sites": {}, "representative": t, "count": 0}
                site_name = t.get("site_name") or "未知站点"
                comment = t.get("comment") or ""
                if "localhost" in comment or "127.0.0.1" in comment:
                    comment = ""
                if site_name not in content_map[key]["sites"] or comment:
                    content_map[key]["sites"][site_name] = comment
                content_map[key]["count"] += 1
                if not content_map[key]["representative"].get("comment") and comment:
                    content_map[key]["representative"]["comment"] = comment

            logger.info(
                f"内容去重完成：原始种子={len(all_torrents)}, "
                f"去重后内容数={len(content_map)}, 涉及站点={len(all_sites)}"
            )

            un_cross_seeded = []
            cross_seeded = []
            for key, info in content_map.items():
                rep = info["representative"]
                sites_dict = info["sites"]
                site_names = set(sites_dict.keys())
                if target_site_title and target_site_title in site_names:
                    other_sites = site_names - {target_site_title}
                    rep["cross_seeded_sites_list"] = [
                        {"name": s, "url": sites_dict.get(s, "") or site_url_map.get(s, "")}
                        for s in sorted(other_sites)
                    ]
                    rep["cross_seeded_sites"] = "、".join(sorted(other_sites)) if other_sites else "-"
                    rep["duplicate_count"] = info["count"]
                    cross_seeded.append(rep)
                else:
                    rep["available_sites_list"] = [
                        {"name": s, "url": sites_dict.get(s, "") or site_url_map.get(s, "")}
                        for s in sorted(site_names)
                    ]
                    rep["available_sites"] = "、".join(sorted(site_names))
                    rep["duplicate_count"] = info["count"]
                    un_cross_seeded.append(rep)

            un_cross_seeded.sort(key=lambda x: x.get("size", 0), reverse=True)
            cross_seeded.sort(key=lambda x: x.get("size", 0), reverse=True)

            results = {
                "site_name": site_display_name,
                "downloader": self._downloader,
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "stats": {
                    "raw_total": len(all_torrents),
                    "unique_total": len(content_map),
                    "cross_seeded_count": len(cross_seeded),
                    "un_cross_seeded_count": len(un_cross_seeded),
                    "site_count": len(all_sites),
                },
                "un_cross_seeded": un_cross_seeded,
                "cross_seeded": cross_seeded,
            }

            self.save_data("results", results)
            logger.info(
                f"未辅种检查任务结束：原始={len(all_torrents)}, 去重={len(content_map)}, "
                f"已有目标站点={len(cross_seeded)}, 未有目标站点={len(un_cross_seeded)}"
            )

            if self._notify:
                self.__send_notification(results)

            return {"success": True, "results": results}
        finally:
            self._lock.release()

    def __get_all_torrents(self) -> Optional[List[dict]]:
        try:
            from app.helper.downloader import DownloaderHelper
            services = DownloaderHelper().get_services(name_filters=[self._downloader])
            if not services:
                logger.warn(f"未找到下载器：{self._downloader}")
                return None
            for name, service_info in services.items():
                dl_type = service_info.type
                instance = service_info.instance
                if dl_type == "qbittorrent":
                    torrents, ok = instance.get_torrents(status=None)
                    if not torrents:
                        logger.warn("qBittorrent 获取种子列表为空")
                        return None
                    result = []
                    for t in torrents:
                        norm = self.__normalize_qb(t)
                        try:
                            trackers = instance.qbc.torrents_trackers(torrent_hash=norm["hash"])
                            norm["trackers"] = [
                                tr.get("url", "") for tr in (trackers or [])
                                if tr.get("url") and tr.get("tier", -1) >= 0
                            ]
                        except Exception:
                            pass
                        result.append(norm)
                    return result
                elif dl_type == "transmission":
                    torrents, ok = instance.get_torrents(status=None)
                    if not torrents:
                        logger.warn("Transmission 获取种子列表为空")
                        return None
                    return [self.__normalize_tr(t) for t in torrents]
            return None
        except Exception as err:
            logger.error(f"获取下载器种子列表异常：{err}")
            return None

    @staticmethod
    def __normalize_qb(torrent) -> dict:
        return {
            "hash": torrent.get("hash"),
            "name": torrent.get("name"),
            "size": torrent.get("size"),
            "tags": torrent.get("tags", ""),
            "trackers": [],
            "save_path": torrent.get("save_path"),
            "added_on": torrent.get("added_on"),
            "comment": torrent.get("comment") or "",
        }

    @staticmethod
    def __normalize_tr(torrent) -> dict:
        trackers = []
        for t in (torrent.trackers or []):
            announce = getattr(t, "announce", "") or ""
            if announce:
                trackers.append(announce)
        added_on = 0
        if torrent.added_date:
            try:
                added_on = int(torrent.added_date.timestamp())
            except Exception:
                pass
        return {
            "hash": torrent.hashString,
            "name": torrent.name,
            "size": torrent.total_size,
            "tags": ",".join(torrent.labels or []),
            "trackers": trackers,
            "save_path": torrent.download_dir,
            "added_on": added_on,
            "comment": getattr(torrent, "comment", "") or "",
        }

    def __identify_site(self, trackers: List[str]) -> Optional[str]:
        for tracker_url in trackers:
            tracker_domain = StringUtils.get_url_domain(tracker_url)
            if not tracker_domain:
                continue
            for opt in self._site_options:
                site_domain = opt.get("value") or ""
                if not site_domain:
                    continue
                if (site_domain in tracker_domain
                        or tracker_domain in site_domain
                        or self.__domain_base(site_domain) == self.__domain_base(tracker_domain)):
                    return opt.get("title") or site_domain
        return None

    @staticmethod
    def __domain_base(domain: str) -> str:
        parts = domain.rsplit(".", 1)
        return parts[0] if len(parts) == 2 else domain

    def __get_primary_tracker_domain(self, trackers: List[str]) -> Optional[str]:
        for tracker_url in trackers:
            domain = StringUtils.get_url_domain(tracker_url)
            if domain:
                return domain
        return None

    @staticmethod
    def __content_key(torrent: dict) -> str:
        size = torrent.get("size", 0)
        name = torrent.get("name", "")
        return f"{size}:{name}"

    def __build_downloader_options(self) -> List[dict]:
        try:
            from app.helper.downloader import DownloaderHelper
            configs = DownloaderHelper().get_configs()
            return [{"title": name, "value": name} for name in configs.keys()]
        except Exception as err:
            logger.debug(f"获取下载器列表失败：{err}")
            return []

    def __build_site_options(self) -> List[dict]:
        try:
            sites = SiteOper().list_active()
            return [{"title": site.name, "value": site.domain} for site in (sites or []) if site.name and site.domain]
        except Exception as err:
            logger.debug(f"获取站点列表失败：{err}")
            return []

    def __send_notification(self, results: Dict[str, Any]):
        stats = results.get("stats") or {}
        site_name = results.get("site_name") or self._site
        title = "【未辅种检查器】"
        text = (
            f"检查站点：{site_name}\n"
            f"下载器种子数：{stats.get('raw_total', 0)}\n"
            f"去重后：{stats.get('unique_total', 0)}\n"
            f"已有该站点：{stats.get('cross_seeded_count', 0)}\n"
            f"{site_name}可发种：{stats.get('un_cross_seeded_count', 0)}"
        )
        logger.info(f"准备发送未辅种检查通知：title={title}")
        self.post_message(mtype=NotificationType.Plugin, title=title, text=text)

    def __get_results(self) -> Dict[str, Any]:
        results = self.get_data("results") or {}
        return results if isinstance(results, dict) else {}

    @staticmethod
    def __format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    @staticmethod
    def __format_timestamp(timestamp: Any) -> str:
        if not timestamp:
            return "-"
        try:
            ts = int(timestamp)
            if ts <= 0:
                return "-"
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            return "-"

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
    def __safe_int(value: Any, default: int, min_value: Optional[int] = None) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        if min_value is not None:
            number = max(number, min_value)
        return number
