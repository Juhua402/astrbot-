from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools
from astrbot.api import logger
import httpx
import json
from datetime import datetime


class GoonsPlugin(Star):
    API_URL = "https://eftarkov.com/news/data.json"
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_keepalive_connections=5),
            http2=True
        )
        
        logger.info("✅ Goons位置查询插件初始化完成")
    
    async def _get_data_from_api(self):
        try:
            timestamp = int(datetime.now().timestamp() * 1000)
            url = f"{self.API_URL}?_={timestamp}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://eftarkov.com/news/web_206.html",
                "Accept": "application/json"
            }
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
            
        except Exception:
            return None
    
    def _get_map_display_name(self, api_map_name):
        if " / " in api_map_name:
            return api_map_name.split(" / ")[1]
        return api_map_name
    
    def _format_time(self, time_str):
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%m-%d %H:%M:%S")
        except ValueError:
            return time_str
    
    def _analyze_goons_location(self, data):
        pvp_latest = {}
        pve_latest = {}
        
        if not data:
            return pvp_latest, pve_latest
        
        for record in data.get("PVP", []):
            map_name = record.get("map", "")
            update_time = record.get("update_time", "")
            
            if map_name and update_time:
                display_name = self._get_map_display_name(map_name)
                if display_name not in pvp_latest:
                    pvp_latest[display_name] = update_time
                else:
                    try:
                        old_time = datetime.strptime(pvp_latest[display_name], "%Y-%m-%d %H:%M:%S")
                        new_time = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                        if new_time > old_time:
                            pvp_latest[display_name] = update_time
                    except ValueError:
                        pvp_latest[display_name] = update_time
        
        for record in data.get("PVE", []):
            map_name = record.get("map", "")
            update_time = record.get("update_time", "")
            
            if map_name and update_time:
                display_name = self._get_map_display_name(map_name)
                if display_name not in pve_latest:
                    pve_latest[display_name] = update_time
                else:
                    try:
                        old_time = datetime.strptime(pve_latest[display_name], "%Y-%m-%d %H:%M:%S")
                        new_time = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                        if new_time > old_time:
                            pve_latest[display_name] = update_time
                    except ValueError:
                        pve_latest[display_name] = update_time
        
        return pvp_latest, pve_latest
    
    @filter.command("三狗", alias={"goons", "三狗位置", "goons位置"}, args=["event"])
    async def query_goons(self, event: AstrMessageEvent):
        try:
            yield event.plain_result("🔄 正在获取最新上传的三狗位置数据...")
            
            data = await self._get_data_from_api()
            
            if not data:
                yield event.plain_result("❌ 获取数据失败，请检查网络或稍后再试")
                return
            
            pvp_latest, pve_latest = self._analyze_goons_location(data)
            
            result = "🐺 Goons小队（三狗）最新位置：\n\n"
            
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
            
            result += "\n📊 数据来源：eftarkov.com"
            
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"查询三狗位置时出错：{str(e)}")
            yield event.plain_result("❌ 查询三狗位置时出现错误，请稍后再试")
    
    async def terminate(self):
        await self.client.aclose()
        logger.info("🔌 三狗位置查询插件已卸载")


if __name__ == "__main__":
    logger.info("🐺 塔科夫三狗位置查询插件启动测试")
