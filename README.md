<div align="center">

# astrbot_plugin_ExchangeRateQuery

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 实时货币汇率查询插件 ✨_
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)

</div>

> [!NOTE]  使用前请配置API, 可前往[OpenExchangeRates](https://openexchangerates.org/)获取api key

## 📦 安装

- 可以直接在astrbot的插件市场搜索astrbot_plugin_ExchangeRateQuery，点击安装，耐心等待安装完成即可
- 或者可以直接克隆源码到插件文件夹：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/MoonShadow1976/astrbot_plugin_ExchangeRateQuery
# 控制台重启AstrBot
```

## ⚙️ 配置

请在astrbot面板配置，插件管理 -> astrbot_plugin_ExchangeRateQuery -> 操作 -> 插件配置

其中 `base_amount` 控制汇率显示基准值，默认为 `100`；`enable_reverse_rate` 控制是否显示反向汇率。

## ⌨️ 命令

|      命令      |          说明          |
| :------------: | :--------------------: |
|   /汇率帮助   |      获取插件帮助      |
|   /汇率代码   |   获取支持货币代码     |
|   /汇率usage   |   查看API的余额信息   |
|     /汇率     | 查询配置的默认货币汇率 |
| /汇率 USD JPY |    查询指定货币汇率    |
| /汇率 JPY 200 |    查询200 JPY兑换基准货币的汇率    |
| /汇率 200JPY 或 /汇率 JPY200 |    支持金额与货币代码连写    |
