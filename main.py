from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.api import logger

from .OpenExchangeRate import OpenExchangeRate
from .src import EXCHANGE_RATE_TMPL

from datetime import datetime, timedelta
import math
import re
from typing import Any, List


@register(
    "astrbot_plugin_ExchangeRateQuery",
    "MoonShadow1976",
    "查询货币汇率的插件",
    "1.3.3",
    "https://github.com/MoonShadow1976/astrbot_plugin_ExchangeRateQuery",
)
class ExchangeRateQueryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.api_key: str = config.get("api_key", "")
        self.past_day: int = config.get("past_day", 7)
        self.base_currency: str = config.get("base_currency", "CNY")
        self.default_currencies: list[str] = config.get(
            "target_currencies", ["USD", "RUB", "EUR", "JPY"]
        )
        self.base_amount: float = self._parse_config_amount(
            config.get("base_amount", 100), 100
        )
        self.enable_reverse_rate: bool = config.get("enable_reverse_rate", True)
        self.enable_t2i: bool = config.get("enable_t2i", False)
        self._currency_cache: tuple[datetime, dict[str, str]] | None = None
        self._rate_cache: dict[
            tuple[str, str], tuple[datetime, dict[str, float], dict[str, float]]
        ] = {}

        if not self.api_key:
            logger.error("未配置OpenExchangeRates API KEY!")

        self.client = OpenExchangeRate(self.api_key)


    @filter.command("汇率帮助", alias={"汇率查询"})
    async def exchange_query_help(self, event: AstrMessageEvent):
        """获取汇率查询帮助"""
        report = [
            "📅【汇率查询帮助】\n",
            "请先于控制台配置默认基准货币和目标货币\n",
            "默认查询命令：\n",
            "/汇率代码 :获取支持的货币代码与名称\n",
            "/汇率usage :查询key的健康值\n",
            "/汇率 :查询默认配置的汇率\n",
            "/汇率 USD JPY EUR :查询美元对日元和欧元的汇率\n",
            "/汇率 JPY 200（或200JPY、JPY200）:查询金额兑换基准货币的汇率\n",
        ]
        if self.enable_t2i:
            url = await self.text_to_image("\n".join(report))
            yield event.image_result(url)
        else:
            yield event.plain_result("\n".join(report))


    @filter.command("汇率代码", alias={"货币代码"})
    async def currencies_query(self, event: AstrMessageEvent):
        """获取支持的货币代码与名称"""
        currencies = await self.client.fetch_currencies()

        # 格式化货币代码输出
        formatted_currencies = "🏦【支持的货币代码】\n\n"
        for code, name in sorted(currencies.items()):
            formatted_currencies += f"• {code}: {name}\n\n"

        if self.enable_t2i:
            url = await self.text_to_image(formatted_currencies)
            yield event.image_result(url)
        else:
            yield event.plain_result(formatted_currencies)


    @filter.command("汇率usage", alias={"健康值"})
    async def usage_query(self, event: AstrMessageEvent):
        """获取OpenExchangeRates API KEY健康值"""
        if not self.api_key:
            yield event.plain_result("控制台未配置API密钥")
            return

        try:
            # 获取API使用信息
            usage_info = await self.client.check_usage_info()
            logger.debug(f"查询usage: {usage_info}")

            # 安全获取数据字段
            data = usage_info.get("data", {})
            usage_data = data.get("usage", {})
            plan_data = data.get("plan", {})

            # 构建健康报告
            report = [
                "【OpenExchangeRates API 健康报告】\n",
                f"📊 套餐计划: {plan_data.get('name', '未知')}\n",
                f"🔢 更新频率: {plan_data.get('update_frequency', 0)}\n",
                f"📈 请求限额: {usage_data.get('requests_quota', 0)} 次/月\n",
                f"• 已用请求: {usage_data.get('requests', 0)} 次\n",
                f"• 剩余额度: {usage_data.get('requests_remaining', 0)} 次\n",
                f"• 本月已过: {usage_data.get('days_elapsed', 0)} 天\n",
                f"• 剩余天数: {usage_data.get('days_remaining', 0)} 天\n",
                f"📅 日均用量: {usage_data.get('daily_average', 0)} 次/天\n",
            ]

            # 计算健康指标
            remaining_percent = (
                usage_data.get("requests_remaining", 0)
                / usage_data.get("requests_quota", 1)
            ) * 100
            health_icon = (
                "✅"
                if remaining_percent > 20
                else "⚠️" if remaining_percent > 5 else "❌"
            )

            report.append(
                f"\n{health_icon} 健康状态: {remaining_percent:.1f}% 剩余额度"
            )

            if self.enable_t2i:
                url = await self.text_to_image("\n".join(report))
                yield event.image_result(url)
            else:
                yield event.plain_result("\n".join(report))

        except Exception as e:
            logger.error(f"健康值查询失败: {str(e)}")
            yield event.plain_result("获取健康值失败，请检查服务器日志")


    @filter.command("汇率", alias={"汇率查询"})
    async def exchange_rate_query(self, event: AstrMessageEvent):
        """查询货币汇率"""
        if not self.api_key:
            yield event.plain_result("控制台未配置API密钥")
            return

        # 解析用户输入
        parts = event.message_str.strip().split()
        base_currency = self.base_currency
        target_currencies = self.default_currencies
        display_amount = self.base_amount
        logger.info(f"查询汇率: 用户输入：{parts}")

        amount_query = self._parse_amount_query(parts)
        if amount_query is not None:
            base_currency, display_amount = amount_query
            if not math.isfinite(display_amount) or display_amount <= 0:
                yield event.plain_result("查询金额必须是大于0的数字")
                return
            # /汇率 JPY 200、/汇率 200JPY、/汇率 JPY200 都表示金额兑换基准货币。
            target_currencies = [self.base_currency]
        elif len(parts) > 1:
            base_currency = parts[1].upper()
            target_currencies = [
                c.upper() for c in parts[2:]
            ] or self.default_currencies

        try:
            # 获取支持的货币代码与名称
            currencies = await self._fetch_currencies_cached()

            # 获取当前和一周前汇率
            current_date = datetime.now()
            week_ago = current_date - timedelta(days=self.past_day)
            historical_date = week_ago.strftime("%Y-%m-%d")

            current_rates, historical_rates = await self._fetch_rates_cached(
                base_currency, historical_date
            )

            if self.enable_t2i:
                # 使用自定义HTML模板渲染图片
                html_data = self._format_html_comparison(
                    currencies,
                    base_currency,
                    current_rates,
                    historical_rates,
                    target_currencies,
                    display_amount,
                )
                try:
                    url = await self.html_render(EXCHANGE_RATE_TMPL, html_data)
                    yield event.image_result(url)
                except Exception as e:
                    logger.error(f"HTML渲染失败: {str(e)}")
                    # 生成对比结果
                    text_result = self._format_text_comparison(
                        currencies,
                        base_currency,
                        current_rates,
                        historical_rates,
                        target_currencies,
                        display_amount,
                    )
                    yield event.plain_result(text_result)
            else:
                # 生成对比结果
                text_result = self._format_text_comparison(
                    currencies,
                    base_currency,
                    current_rates,
                    historical_rates,
                    target_currencies,
                    display_amount,
                )
                yield event.plain_result(text_result)

        except Exception as e:
            logger.error(f"汇率查询失败: {str(e)}")
            yield event.plain_result("汇率查询失败，请稍后再试")


    def _format_text_comparison(
        self,
        currencies: dict[str, str],
        base: str,
        current: dict[str, float],
        historical: dict[str, float],
        targets: list[str],
        amount: float | None = None,
    ) -> str:
        """格式化汇率对比结果为文本形式"""
        amount = self._get_display_amount(amount)
        show_reverse = getattr(self, "enable_reverse_rate", True)
        base_currency_name = currencies.get(base, base)
        result = [f"💱 【{base}({base_currency_name}) 汇率对比报告】"]
        result.append(f"📊 对比时间范围: {self.past_day}天前 vs 当前")
        result.append("")
        
        for currency in targets:
            curr_rate = current.get(currency)
            hist_rate = historical.get(currency)

            if curr_rate is not None and hist_rate is not None:
                current_value = amount * curr_rate
                historical_value = amount * hist_rate
                change = current_value - historical_value
                change_percent = (change / historical_value) * 100 if historical_value else 0
                arrow = "📈" if change > 0 else ("📉" if change < 0 else "➡️")
                trend = "上涨" if change > 0 else ("下跌" if change < 0 else "持平")
                
                currency_name = currencies.get(currency, currency)
                
                result.append(f"💰 {currency}({currency_name}):")
                result.append(
                    f"   • 当前汇率: {self._format_amount(amount)} {base} = "
                    f"{current_value:.4f} {currency}"
                )
                result.append(
                    f"   • {self.past_day}天前: {self._format_amount(amount)} {base} = "
                    f"{historical_value:.4f} {currency}"
                )
                if show_reverse and curr_rate > 0:
                    reverse_value = amount / curr_rate
                    result.append(
                        f"   • 反向汇率: {self._format_amount(amount)} {currency} = "
                        f"{reverse_value:.4f} {base}"
                    )
                result.append(f"   • 变化: {arrow} {change:+.4f} ({change_percent:+.2f}%) {trend}")
                result.append("")

        if len(result) == 3:  # 只有标题和时间范围，没有有效数据
            result.append("❌ 未找到有效的汇率数据")

        return "\n".join(result)


    def _format_html_comparison(
        self,
        currencies: dict[str, str],
        base: str,
        current: dict[str, float],
        historical: dict[str, float],
        targets: list[str],
        amount: float | None = None,
    ) -> dict[str, str | int | list[Any]]:
        """准备HTML模板渲染所需的数据"""
        amount = self._get_display_amount(amount)
        show_reverse = getattr(self, "enable_reverse_rate", True)
        base_currency_name = currencies.get(base, base)
        comparisons = []
        
        for currency in targets:
            curr_rate = current.get(currency)
            hist_rate = historical.get(currency)

            if curr_rate is not None and hist_rate is not None:
                current_value = amount * curr_rate
                historical_value = amount * hist_rate
                change = current_value - historical_value
                change_percent = (change / historical_value) * 100 if historical_value else 0
                trend = "up" if change > 0 else ("down" if change < 0 else "same")
                trend_text = "上涨" if change > 0 else ("下跌" if change < 0 else "持平")
                arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
                
                comparison = {
                    "currency_code": currency,
                    "currency_name": currencies.get(currency, currency),
                    "current_rate": (
                        f"{self._format_amount(amount)} {base} = "
                        f"{current_value:.4f} {currency}"
                    ),
                    "historical_rate": (
                        f"{self._format_amount(amount)} {base} = "
                        f"{historical_value:.4f} {currency}"
                    ),
                    "change_value": f"{change:+.4f}",
                    "change_percent": f"{change_percent:+.2f}%",
                    "trend": trend,
                    "trend_text": trend_text,
                    "arrow": arrow
                }
                if show_reverse and curr_rate > 0:
                    comparison["reverse_rate"] = (
                        f"反向汇率: {self._format_amount(amount)} {currency} = "
                        f"{amount / curr_rate:.4f} {base}"
                    )
                comparisons.append(comparison)

        return {
            "base_currency": base,
            "base_currency_name": base_currency_name,
            "past_days": self.past_day,
            "comparisons": comparisons,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

    @staticmethod
    def _parse_config_amount(value: Any, fallback: float) -> float:
        """读取并校验配置中的显示基准值。"""
        try:
            amount = float(value)
            if math.isfinite(amount) and amount > 0:
                return amount
        except (TypeError, ValueError):
            pass
        return fallback

    def _get_display_amount(self, amount: float | None) -> float:
        """获取查询使用的金额，兼容旧的格式化方法调用。"""
        if amount is None:
            amount = getattr(self, "base_amount", 100)
        return self._parse_config_amount(amount, 100)

    @staticmethod
    def _format_amount(amount: float) -> str:
        """以适合消息展示的形式格式化金额，避免显示无意义的 .0。"""
        if amount.is_integer():
            return str(int(amount))
        return f"{amount:.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _next_hour(now: datetime) -> datetime:
        """返回当前时间之后的下一个整点。"""
        return (now + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )

    async def _fetch_currencies_cached(self) -> dict[str, str]:
        """缓存货币列表，直到下一个整点。"""
        now = datetime.now()
        cached = getattr(self, "_currency_cache", None)
        if cached is not None and now < cached[0]:
            return cached[1]

        currencies = await self.client.fetch_currencies()
        self._currency_cache = (self._next_hour(now), currencies)
        return currencies

    async def _fetch_rates_cached(
        self, base_currency: str, historical_date: str
    ) -> tuple[dict[str, float], dict[str, float]]:
        """缓存当前及历史汇率，直到下一个整点。"""
        now = datetime.now()
        rate_cache = getattr(self, "_rate_cache", {})
        self._rate_cache = rate_cache

        # 清理过期项，避免长时间运行后缓存键持续增长。
        expired_keys = [
            key for key, cached in rate_cache.items() if now >= cached[0]
        ]
        for key in expired_keys:
            del rate_cache[key]

        cache_key = (base_currency, historical_date)
        cached = rate_cache.get(cache_key)
        if cached is not None and now < cached[0]:
            return cached[1], cached[2]

        current_rates = await self.client.fetch_latest_rates(base_currency)
        historical_rates = await self.client.fetch_historical_rates(
            historical_date, base_currency
        )
        rate_cache[cache_key] = (
            self._next_hour(now),
            current_rates,
            historical_rates,
        )
        return current_rates, historical_rates

    @staticmethod
    def _parse_amount_query(parts: list[str]) -> tuple[str, float] | None:
        """解析金额换算语法，兼容空格和货币代码/金额连写。"""
        amount_pattern = r"(?:\d+(?:\.\d*)?|\.\d+)"
        currency_pattern = r"[A-Za-z]{3}"

        if len(parts) == 3:
            # 支持 /汇率 JPY 200 和 /汇率 200 JPY。
            for currency_token, amount_token in (
                (parts[1], parts[2]),
                (parts[2], parts[1]),
            ):
                if not re.fullmatch(currency_pattern, currency_token):
                    continue
                if not re.fullmatch(amount_pattern, amount_token):
                    continue
                return currency_token.upper(), float(amount_token)

        if len(parts) == 2:
            # 支持 /汇率 200JPY 和 /汇率 JPY200。
            compact_pattern = re.compile(
                rf"(?:({amount_pattern})({currency_pattern})|"
                rf"({currency_pattern})({amount_pattern}))",
                re.IGNORECASE,
            )
            match = compact_pattern.fullmatch(parts[1])
            if match:
                amount_token = match.group(1) or match.group(4)
                currency_token = match.group(2) or match.group(3)
                return currency_token.upper(), float(amount_token)

        return None


    async def terminate(self):
        await self.client.close()
        logger.info("货币汇率查询插件已安全停止")
