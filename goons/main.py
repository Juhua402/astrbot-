from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
import httpx
import json
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from typing import Dict, List, Tuple, Optional
import asyncio


@register(
    "astrbot_plugin_goons",
    "塔科夫三狗位置查询",
    "查询逃离塔科夫中Goons小队（三狗）的实时位置",
    "1.0.0",
    "https://github.com/Juhua402/astrbot_plugin_goons"
)
class GoonsPlugin(Star):
    # API配置
    API_URL = "https://eftarkov.com/news/data.json"
    # 自动刷新间隔（秒）
    AUTO_REFRESH_INTERVAL = 5
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 插件数据目录
        self.target_data_dir = Path(StarTools.get_data_dir("astrbot_plugin_goons"))
        self.plugin_root_dir = Path(__file__).parent
        self.template_dir = self.plugin_root_dir / "templates"
        
        # 创建目录和复制模板
        self._init_directories()
        
        # 加载地图别名
        self.map_aliases = self._load_map_aliases()
        
        # 初始化数据缓存
        self.data_cache = None
        self.last_update_time = None
        self.last_successful_fetch = None
        self.last_fetch_error = None
        
        # 自动刷新任务
        self.refresh_task = None
        self.is_refreshing = False
        
        # 统计数据
        self.fetch_count = 0
        self.error_count = 0
        
        logger.info(f"✅ Goons位置查询插件初始化完成")
        logger.info(f"📁 数据目录：{self.target_data_dir}")
        logger.info(f"🗺️  已加载 {len(self.map_aliases)} 个地图别名")
        
        # 启动自动刷新
        self._start_auto_refresh()
    
    def _init_directories(self):
        """初始化目录和配置文件"""
        self.target_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 复制模板文件
        if self.template_dir.exists():
            template_file = self.template_dir / "maps.txt"
            target_file = self.target_data_dir / "maps.txt"
            
            if not target_file.exists() and template_file.exists():
                shutil.copy2(template_file, target_file)
                logger.info(f"📁 已自动创建 {target_file}（地图别名配置文件）")
        else:
            logger.warning(f"⚠️  模板目录 {self.template_dir} 不存在")
    
    def _start_auto_refresh(self):
        """启动自动刷新任务"""
        if self.refresh_task is None:
            self.refresh_task = asyncio.create_task(self._auto_refresh_loop())
            logger.info(f"🔄 已启动自动刷新，间隔 {self.AUTO_REFRESH_INTERVAL} 秒")
    
    async def _auto_refresh_loop(self):
        """自动刷新循环"""
        while True:
            try:
                await asyncio.sleep(self.AUTO_REFRESH_INTERVAL)
                await self._fetch_data_async()
            except asyncio.CancelledError:
                logger.info("⏹️  自动刷新任务已取消")
                break
            except Exception as e:
                logger.error(f"❌ 自动刷新循环出错：{str(e)}")
                self.error_count += 1
                await asyncio.sleep(60)  # 出错后等待60秒再重试
    
    async def _fetch_data_async(self):
        """异步获取数据"""
        if self.is_refreshing:
            return
        
        self.is_refreshing = True
        try:
            # 获取新数据
            new_data = await self._get_data_from_api_async()
            self.fetch_count += 1
            
            if new_data:
                old_data = self.data_cache
                self.data_cache = new_data
                self.last_update_time = datetime.now()
                self.last_successful_fetch = datetime.now()
                self.last_fetch_error = None
                
                # 记录数据变化（调试用）
                if old_data:
                    # 可以在这里添加数据变化的日志
                    pass
                
                # 每10次成功获取记录一次日志
                if self.fetch_count % 10 == 0:
                    logger.info(f"📊 自动刷新统计：成功 {self.fetch_count} 次，失败 {self.error_count} 次")
                
                return True
            else:
                self.error_count += 1
                self.last_fetch_error = datetime.now()
                return False
                
        except Exception as e:
            logger.error(f"❌ 异步获取数据失败：{str(e)}")
            self.error_count += 1
            self.last_fetch_error = datetime.now()
            return False
        finally:
            self.is_refreshing = False
    
    async def _get_data_from_api_async(self):
        """异步从API获取数据"""
        try:
            # 添加时间戳防止缓存
            timestamp = int(datetime.now().timestamp() * 1000)
            url = f"{self.API_URL}?_={timestamp}"
            
            # 使用httpx异步获取数据
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://eftarkov.com/news/web_206.html",
                "Accept": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                return data
                
        except httpx.RequestError as e:
            logger.error(f"❌ 请求API失败：{str(e)}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ API返回错误状态码：{e.response.status_code}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"❌ 解析JSON数据失败：{str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 获取数据时发生未知错误：{str(e)}")
            return None
    
    def _load_map_aliases(self) -> Dict[str, List[str]]:
        """加载地图别名配置"""
        file_path = self.target_data_dir / "maps.txt"
        map_aliases = {}
        
        # 默认的地图别名（如果配置文件不存在）
        default_aliases = {
            "海关": ["customs", "hg"],
            "森林": ["woods", "sl", "树林"],
            "立交桥": ["interchange", "ljq", "商场"],
            "海岸线": ["shoreline", "hx", "疗养院", "海滨"],
            "灯塔": ["lighthouse", "dt"],
            "街区": ["streets", "jq", "街道"],
            "工厂": ["factory", "gc"],
            "储备站": ["reserve", "cbz", "军事基地"],
            "实验室": ["lab", "sys"]
        }
        
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        
                        if "|" in line:
                            display_name, aliases_str = line.split("|", 1)
                            display_name = display_name.strip()
                            aliases = [alias.strip().lower() for alias in aliases_str.split(",") if alias.strip()]
                            map_aliases[display_name] = aliases
            except Exception as e:
                logger.error(f"❌ 读取地图别名配置文件失败：{str(e)}，使用默认配置")
                return default_aliases
        else:
            logger.warning(f"⚠️  地图别名配置文件不存在，使用默认配置")
            return default_aliases
        
        return map_aliases
    
    def _get_map_display_name(self, api_map_name: str) -> str:
        """将API返回的地图名称转换为显示名称"""
        # 例如："Customs / 海关" -> "海关"
        if " / " in api_map_name:
            return api_map_name.split(" / ")[1]
        return api_map_name
    
    def _get_display_name_by_alias(self, alias: str) -> Optional[str]:
        """通过别名获取显示名称"""
        alias = alias.lower()
        for display_name, aliases in self.map_aliases.items():
            if alias == display_name.lower() or alias in [a.lower() for a in aliases]:
                return display_name
        return None
    
    def _find_matching_api_map_name(self, display_name: str, api_data: Dict) -> Optional[str]:
        """在API数据中查找匹配的地图名称"""
        if not api_data:
            return None
        
        # 查找PVP数据
        if "PVP" in api_data:
            for record in api_data["PVP"]:
                api_map_name = record.get("map", "")
                if api_map_name:
                    api_display_name = self._get_map_display_name(api_map_name)
                    if display_name == api_display_name:
                        return api_map_name
        
        # 查找PVE数据
        if "PVE" in api_data:
            for record in api_data["PVE"]:
                api_map_name = record.get("map", "")
                if api_map_name:
                    api_display_name = self._get_map_display_name(api_map_name)
                    if display_name == api_display_name:
                        return api_map_name
        
        # 如果没有完全匹配，尝试部分匹配
        for api_key in ["PVP", "PVE"]:
            if api_key in api_data:
                for record in api_data[api_key]:
                    api_map_name = record.get("map", "")
                    if api_map_name and display_name in api_map_name:
                        return api_map_name
        
        return None
    
    def _format_time(self, time_str: str) -> str:
        """格式化时间显示"""
        try:
            # 解析API返回的时间
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            # 转换为本地时间显示
            return dt.strftime("%m-%d %H:%M:%S")
        except:
            return time_str
    
    def _format_duration(self, seconds: int) -> str:
        """格式化时间间隔"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}分钟"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}小时{minutes}分钟"
    
    def _analyze_goons_location(self, data: Dict) -> Tuple[Dict, Dict]:
        """分析Goons小队的位置
        
        返回: (pvp_latest, pve_latest)
        """
        pvp_latest = {}
        pve_latest = {}
        
        if not data:
            return pvp_latest, pve_latest
        
        # 分析PVP数据
        if "PVP" in data and data["PVP"]:
            for record in data["PVP"]:
                map_name = record.get("map", "")
                update_time = record.get("update_time", "")
                
                if map_name and update_time:
                    # 使用显示名称作为键
                    display_name = self._get_map_display_name(map_name)
                    # 只保留最新的记录
                    if display_name not in pvp_latest:
                        pvp_latest[display_name] = update_time
                    else:
                        # 如果已有记录，比较时间
                        try:
                            old_time = datetime.strptime(pvp_latest[display_name], "%Y-%m-%d %H:%M:%S")
                            new_time = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                            if new_time > old_time:
                                pvp_latest[display_name] = update_time
                        except:
                            pvp_latest[display_name] = update_time
        
        # 分析PVE数据
        if "PVE" in data and data["PVE"]:
            for record in data["PVE"]:
                map_name = record.get("map", "")
                update_time = record.get("update_time", "")
                
                if map_name and update_time:
                    # 使用显示名称作为键
                    display_name = self._get_map_display_name(map_name)
                    # 只保留最新的记录
                    if display_name not in pve_latest:
                        pve_latest[display_name] = update_time
                    else:
                        # 如果已有记录，比较时间
                        try:
                            old_time = datetime.strptime(pve_latest[display_name], "%Y-%m-%d %H:%M:%S")
                            new_time = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                            if new_time > old_time:
                                pve_latest[display_name] = update_time
                        except:
                            pve_latest[display_name] = update_time
        
        return pvp_latest, pve_latest
    
    @filter.command("三狗", alias={"goons", "三狗位置", "goons位置"}, args=["event"])
    async def query_goons(self, event: AstrMessageEvent):
        """查询三狗位置主命令"""
        try:
            # 如果数据为空，先尝试获取一次
            if self.data_cache is None:
                await self._fetch_data_async()
            
            data = self.data_cache
            
            if not data:
                if self.last_fetch_error:
                    error_time = self._format_duration(int((datetime.now() - self.last_fetch_error).total_seconds()))
                    yield event.plain_result(f"❌ 获取三狗位置数据失败（最近一次错误发生在{error_time}前）\n请稍后再试或使用 /刷新三狗")
                else:
                    yield event.plain_result("❌ 获取三狗位置数据失败，请稍后再试")
                return
            
            # 分析数据
            pvp_latest, pve_latest = self._analyze_goons_location(data)
            
            # 构建回复消息
            result = "🐺 Goons小队（三狗）最新位置：\n\n"
            
            # PVP位置
            result += "🎮 PVP模式：\n"
            if pvp_latest:
                for map_name, time_str in pvp_latest.items():
                    formatted_time = self._format_time(time_str)
                    result += f"  • {map_name} - {formatted_time}\n"
            else:
                result += "  暂无数据\n"
            
            result += "\n💀 PVE模式：\n"
            if pve_latest:
                for map_name, time_str in pve_latest.items():
                    formatted_time = self._format_time(time_str)
                    result += f"  • {map_name} - {formatted_time}\n"
            else:
                result += "  暂无数据\n"
            
            # 添加状态信息
            if self.last_update_time:
                update_diff = int((datetime.now() - self.last_update_time).total_seconds())
                result += f"\n⏰ 数据更新时间：{self.last_update_time.strftime('%m-%d %H:%M:%S')}（{update_diff}秒前）"
            
            result += f"\n🔄 自动刷新：每{self.AUTO_REFRESH_INTERVAL}秒"
            result += f"\n⚠️ 数据来源：eftarkov.com"
            
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"❌ 查询三狗位置时出错：{str(e)}")
            yield event.plain_result("❌ 查询三狗位置时出现错误，请稍后再试")
    
    @filter.command("三狗地图", alias={"goons地图", "地图三狗"}, args=["event"])
    async def query_goons_by_map(self, event: AstrMessageEvent):
        """按地图查询三狗位置"""
        try:
            # 获取消息内容
            raw_msg = event.message_obj.message_str.strip()
            
            # 提取地图名称
            if raw_msg.startswith("/三狗地图"):
                map_input = raw_msg[5:].strip()
            elif raw_msg.startswith("/goons地图"):
                map_input = raw_msg[10:].strip()
            elif raw_msg.startswith("/地图三狗"):
                map_input = raw_msg[4:].strip()
            else:
                yield event.plain_result("❌ 命令格式错误，请使用：/三狗地图 [地图名]")
                return
            
            if not map_input:
                yield event.plain_result("❌ 请提供要查询的地图名称\n例如：/三狗地图 海关")
                return
            
            # 如果数据为空，先尝试获取一次
            if self.data_cache is None:
                await self._fetch_data_async()
            
            data = self.data_cache
            
            if not data:
                yield event.plain_result("❌ 获取数据失败，请稍后再试")
                return
            
            # 通过别名获取显示名称
            display_name = self._get_display_name_by_alias(map_input)
            
            # 如果没有找到别名匹配，尝试使用输入的名称
            if not display_name:
                display_name = map_input
            
            # 在API数据中查找匹配的地图名称
            api_map_name = self._find_matching_api_map_name(display_name, data)
            
            if not api_map_name:
                # 列出可用的地图
                available_maps = set()
                if "PVP" in data and data["PVP"]:
                    for record in data["PVP"][:10]:  # 检查前10条记录
                        map_name = record.get("map", "")
                        if map_name:
                            available_maps.add(self._get_map_display_name(map_name))
                
                if "PVE" in data and data["PVE"]:
                    for record in data["PVE"][:10]:  # 检查前10条记录
                        map_name = record.get("map", "")
                        if map_name:
                            available_maps.add(self._get_map_display_name(map_name))
                
                if available_maps:
                    result = f"❌ 未找到地图 '{map_input}' 的记录\n\n"
                    result += "📋 当前数据中可用的地图：\n"
                    for map_name in sorted(available_maps):
                        result += f"  • {map_name}\n"
                    result += "\n💡 提示：可以使用 /三狗 查看所有最新位置"
                else:
                    result = f"❌ 未找到地图 '{map_input}' 的记录，且当前无可用数据"
                
                yield event.plain_result(result)
                return
            
            result = f"🗺️  地图：{self._get_map_display_name(api_map_name)}\n\n"
            
            # 查询PVP数据
            pvp_records = []
            if "PVP" in data and data["PVP"]:
                for record in data["PVP"]:
                    if record.get("map") == api_map_name:
                        pvp_records.append(record)
            
            # 查询PVE数据
            pve_records = []
            if "PVE" in data and data["PVE"]:
                for record in data["PVE"]:
                    if record.get("map") == api_map_name:
                        pve_records.append(record)
            
            # 显示结果
            if pvp_records:
                result += "🎮 PVP模式最新记录：\n"
                # 按时间排序，最新的在前面
                pvp_records.sort(key=lambda x: x.get("update_time", ""), reverse=True)
                # 只显示最新的5条记录
                for record in pvp_records[:5]:
                    time_str = self._format_time(record.get("update_time", ""))
                    result += f"  • {time_str}\n"
                if len(pvp_records) > 5:
                    result += f"  ... 还有 {len(pvp_records) - 5} 条更早记录\n"
            else:
                result += "🎮 PVP模式：暂无记录\n"
            
            result += "\n"
            
            if pve_records:
                result += "💀 PVE模式最新记录：\n"
                # 按时间排序，最新的在前面
                pve_records.sort(key=lambda x: x.get("update_time", ""), reverse=True)
                # 只显示最新的5条记录
                for record in pve_records[:5]:
                    time_str = self._format_time(record.get("update_time", ""))
                    result += f"  • {time_str}\n"
                if len(pve_records) > 5:
                    result += f"  ... 还有 {len(pve_records) - 5} 条更早记录\n"
            else:
                result += "💀 PVE模式：暂无记录\n"
            
            # 统计信息
            result += f"\n📊 统计："
            result += f" PVP记录 {len(pvp_records)} 条，"
            result += f" PVE记录 {len(pve_records)} 条"
            
            # 添加更新时间
            if self.last_update_time:
                update_diff = int((datetime.now() - self.last_update_time).total_seconds())
                result += f"\n⏰ 数据更新时间：{self.last_update_time.strftime('%H:%M:%S')}（{update_diff}秒前）"
            
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"❌ 按地图查询时出错：{str(e)}")
            yield event.plain_result("❌ 查询时出现错误，请稍后再试")
    
    @filter.command("刷新三狗", alias={"刷新goons", "更新三狗"}, args=["event"])
    async def refresh_goons(self, event: AstrMessageEvent):
        """强制刷新三狗数据"""
        try:
            yield event.plain_result("🔄 正在刷新三狗数据...")
            
            success = await self._fetch_data_async()
            
            if success:
                if self.last_update_time:
                    update_diff = int((datetime.now() - self.last_update_time).total_seconds())
                    result = f"✅ 三狗数据已刷新！\n"
                    result += f"📊 数据统计：成功获取 {self.fetch_count} 次\n"
                    result += f"⏰ 更新时间：{self.last_update_time.strftime('%H:%M:%S')}（{update_diff}秒前）\n"
                    result += f"🔄 可以使用 /三狗 查看最新位置"
                else:
                    result = "✅ 三狗数据已刷新！\n可以使用 /三狗 查看最新位置"
            else:
                if self.last_fetch_error:
                    error_time = self._format_duration(int((datetime.now() - self.last_fetch_error).total_seconds()))
                    result = f"❌ 刷新数据失败（最近一次错误发生在{error_time}前）\n请稍后再试"
                else:
                    result = "❌ 刷新数据失败，请稍后再试"
            
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"❌ 刷新数据时出错：{str(e)}")
            yield event.plain_result("❌ 刷新数据时出现错误")
    
    @filter.command("三狗状态", alias={"goons状态", "状态三狗"}, args=["event"])
    async def goons_status(self, event: AstrMessageEvent):
        """显示插件状态"""
        try:
            status = "📊 三狗位置查询插件状态：\n\n"
            
            # 基本信息
            status += f"🔄 自动刷新间隔：{self.AUTO_REFRESH_INTERVAL}秒\n"
            
            # 数据状态
            if self.data_cache:
                # 统计记录数量
                pvp_count = len(self.data_cache.get("PVP", []))
                pve_count = len(self.data_cache.get("PVE", []))
                status += f"📁 数据记录：PVP {pvp_count} 条，PVE {pve_count} 条\n"
            else:
                status += "📁 数据记录：暂无数据\n"
            
            # 更新时间
            if self.last_update_time:
                update_diff = int((datetime.now() - self.last_update_time).total_seconds())
                status += f"⏰ 最后更新：{self.last_update_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                status += f"   （{update_diff}秒前）\n"
            else:
                status += "⏰ 最后更新：从未成功获取\n"
            
            # 统计信息
            status += f"📈 统计信息：\n"
            status += f"  • 成功获取：{self.fetch_count} 次\n"
            status += f"  • 失败次数：{self.error_count} 次\n"
            
            if self.last_successful_fetch:
                success_diff = int((datetime.now() - self.last_successful_fetch).total_seconds())
                status += f"  • 最后成功：{self._format_duration(success_diff)}前\n"
            
            if self.last_fetch_error:
                error_diff = int((datetime.now() - self.last_fetch_error).total_seconds())
                status += f"  • 最后错误：{self._format_duration(error_diff)}前\n"
            
            # 刷新任务状态
            if self.refresh_task and not self.refresh_task.done():
                status += f"✅ 自动刷新：运行中\n"
            else:
                status += f"❌ 自动刷新：已停止\n"
            
            # 地图别名
            status += f"🗺️  地图别名：已加载 {len(self.map_aliases)} 个\n"
            
            status += "\n💡 使用 /三狗帮助 查看完整命令"
            
            yield event.plain_result(status)
            
        except Exception as e:
            logger.error(f"❌ 获取插件状态时出错：{str(e)}")
            yield event.plain_result("❌ 获取插件状态时出现错误")
    
    @filter.command("三狗帮助", alias={"goons帮助", "三狗说明"}, args=["event"])
    async def goons_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = f"""🐺 Goons小队（三狗）位置查询插件帮助：

基础命令：
/三狗 或 /goons - 查询三狗的最新位置
/三狗地图 [地图名] - 查询指定地图的三狗记录
/刷新三狗 - 强制刷新数据（自动刷新每{self.AUTO_REFRESH_INTERVAL}秒一次）
/三狗状态 - 查看插件运行状态
/三狗帮助 - 显示此帮助信息

示例：
/三狗
/三狗地图 海关
/三狗地图 customs
/goons地图 woods
/刷新三狗
/三狗状态

支持的地图别名：
海关 - customs, hg
森林 - woods, sl, 树林
立交桥 - interchange, ljq, 商场
海岸线 - shoreline, hx, 疗养院
灯塔 - lighthouse, dt
街区 - streets, jq, 街道
工厂 - factory, gc
储备站 - reserve, cbz, 军事基地
实验室 - lab, sys

插件特性：
• 每{self.AUTO_REFRESH_INTERVAL}秒自动刷新数据
• 支持地图别名查询
• 实时显示数据更新时间
• 错误自动重试机制

注意：数据来源于 eftarkov.com，更新可能有延迟
地图别名可以在 maps.txt 文件中自定义"""
        
        yield event.plain_result(help_text)
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        # 停止自动刷新任务
        if self.refresh_task:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"📊 插件运行统计：成功 {self.fetch_count} 次，失败 {self.error_count} 次")
        logger.info("🔌 三狗位置查询插件已卸载")


if __name__ == "__main__":
    logger.info("🐺 塔科夫三狗位置查询插件启动测试")