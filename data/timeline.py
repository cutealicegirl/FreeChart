# -*- coding: utf-8 -*-
"""品种发展历程与档案（离线结构化资料库）。

行情接口只回答「现在多少钱」，回答不了「这个品种从哪来、经历过什么」。
本模块补这一层，和 data/about.py 的分工：

  about.py    一段式背景介绍（做什么 / 谁做的 / 什么时候）
  timeline.py 按时间排序的里程碑事件 + 可核对的档案字段

资料整理原则（**准确性优先于篇幅**）：

1. 只收录能被公开资料核对的事件：交易所与公司公告、项目官方文档 /
   白皮书、监管机构公告、上市地交易所的公司概况页；
2. 日期按可信粒度写：能核到日就写 YYYY-MM-DD，只能核到月写 YYYY-MM，
   只有年份可靠的写 YYYY —— 绝不把「大概」补成精确日期；
3. 不写价格、市值、收益率这类会随时间失效的数字，也不写预测 / 前景；
4. 每条事件带 src 说明来源类型；整库带统一核验日期，UI 上明确标注；
5. 资料库未收录的品种返回空列表 + 明确提示，不用「通用市场说明」
   冒充该品种的历史（这是 v37 修正的一个准确性问题）。

本库由 AI 依据公开资料整理，关键日期经联网检索核对（上交所公司概况、
港交所上市资料、SEC 执法公告、Nasdaq / 公司 IR、项目官方文档）。
核验日期：2026-11-14。内容仅供了解品种背景，不构成投资建议。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from data.universe import market_of

VERIFIED_AT = "2026-11-14"
SOURCE_NOTE = ("AI 依据公开资料整理 · 核验于 2026-11-14 · "
               "关键日期经交易所公告 / 项目官方文档 / 监管公告核对")
NO_DATA = "— 资料库未收录该品种的发展历程，请以官方披露为准"

# 来源标签：简短、可核对，不写具体链接（链接会失效）
S_OFFICIAL = "项目官方文档 / 白皮书"
S_EXCHANGE = "交易所公告 / 公司概况"
S_REG = "监管机构公告"
S_IR = "公司年报 / 投资者关系"
S_MEDIA = "公开资料整理"


def _e(date: str, title: str, detail: str = "", src: str = S_MEDIA) -> dict:
    """一条里程碑。date 支持 YYYY / YYYY-MM / YYYY-MM-DD。"""
    return {"date": date, "title": title, "detail": detail, "src": src}


# ---------------------------------------------------------------------------
# 发展历程：symbol -> [事件]
# ---------------------------------------------------------------------------
TIMELINE: Dict[str, List[dict]] = {
    # ============================ 加密资产 ============================
    "BTC": [
        _e("2008-10-31", "白皮书发布", "中本聪在密码学邮件列表发表《Bitcoin: A Peer-to-Peer Electronic Cash System》。", S_OFFICIAL),
        _e("2009-01-03", "创世区块挖出", "比特币网络正式上线，创世区块内嵌当日《泰晤士报》头版标题。", S_OFFICIAL),
        _e("2009-01-12", "第一笔转账", "中本聪向 Hal Finney 转出 10 BTC，是网络内首笔点对点交易。", S_OFFICIAL),
        _e("2010-05-22", "披萨日：首次实物交易", "程序员用 10,000 BTC 换两份披萨，比特币第一次有了可观察的交换价格。", S_MEDIA),
        _e("2012-11-28", "第一次产量减半", "区块奖励由 50 BTC 降至 25 BTC，减半周期约四年一次。", S_OFFICIAL),
        _e("2016-07-09", "第二次减半", "区块奖励降至 12.5 BTC。", S_OFFICIAL),
        _e("2017-08", "SegWit 激活与 BCH 分叉", "隔离见证软分叉激活；同期社区因扩容路线分歧分叉出 Bitcoin Cash。", S_MEDIA),
        _e("2020-05-11", "第三次减半", "区块奖励降至 6.25 BTC。", S_OFFICIAL),
        _e("2021-09-07", "萨尔瓦多将其列为法定货币", "首个主权国家以立法形式承认比特币为法定货币。", S_REG),
        _e("2024-01-10", "美国现货 ETF 获批", "SEC 批准首批 11 只比特币现货 ETF，传统账户可直接配置。", S_REG),
        _e("2024-04-20", "第四次减半", "区块奖励降至 3.125 BTC，总量上限仍为 2100 万枚。", S_OFFICIAL),
    ],
    "ETH": [
        _e("2013-11", "以太坊白皮书发布", "Vitalik Buterin 提出可运行智能合约的可编程区块链。", S_OFFICIAL),
        _e("2014-07", "公开发行众筹", "通过比特币众筹为协议开发募集资金，以太坊基金会成立。", S_OFFICIAL),
        _e("2015-07-30", "Frontier 主网上线", "以太坊主网正式运行，开发者可用第一个准可用版本部署合约。", S_OFFICIAL),
        _e("2016-07-20", "The DAO 硬分叉", "为应对 The DAO 合约漏洞导致的资金被转移，社区硬分叉，形成 ETH 与 ETC 两条链。", S_MEDIA),
        _e("2020-12-01", "信标链上线", "权益证明链与原有工作量证明主链并行运行，为合并做准备。", S_OFFICIAL),
        _e("2021-08-05", "伦敦升级 / EIP-1559", "引入按需求浮动的基础费并销毁，改变手续费与发行机制。", S_OFFICIAL),
        _e("2022-09-15", "The Merge 合并", "执行层与共识层合并，正式由工作量证明转为权益证明。", S_OFFICIAL),
        _e("2023-04-12", "上海 / Capella 升级", "开放验证者质押 ETH 与奖励的提款。", S_OFFICIAL),
        _e("2024-03-13", "Dencun 升级 / EIP-4844", "引入 blob 数据交易，显著降低 Layer2 Rollup 的数据成本。", S_OFFICIAL),
        _e("2024-05-23", "美国现货 ETH ETF 获批", "SEC 批准现货以太坊 ETF 的 19b-4 申请。", S_REG),
    ],
    "SOL": [
        _e("2017-11", "历史证明 PoH 论文", "Anatoly Yakovenko 提出用可验证时间序列提升出块效率的方案。", S_OFFICIAL),
        _e("2020-03", "主网 Beta 上线", "Solana 主网以 Beta 状态开放，主打高吞吐与低手续费。", S_OFFICIAL),
        _e("2021", "生态快速扩张", "DeFi、NFT 与高频交易类应用在链上集中涌现。", S_MEDIA),
        _e("2022-11", "FTX 事件冲击", "FTX / Alameda 崩溃，因其持有并抵押大量 SOL，生态资金与币价受重创。", S_MEDIA),
        _e("2023", "Firedancer 独立客户端", "Jump Crypto 开发的第二客户端推进验证，目标是提升客户端多样性。", S_OFFICIAL),
    ],
    "BNB": [
        _e("2017-07", "币安成立与 BNB 发行", "BNB 以交易所平台币身份发行，用于抵扣交易手续费。", S_OFFICIAL),
        _e("2019-04", "Binance Chain 主网", "上线专注资产发行与交易的公链。", S_OFFICIAL),
        _e("2020-09", "BSC 智能合约链上线", "兼容 EVM 的 Binance Smart Chain 主网启动，链上 DeFi 生态展开。", S_OFFICIAL),
        _e("2022-02", "品牌统一为 BNB Chain", "Binance Chain 与 BSC 统一归入 BNB Chain 生态。", S_OFFICIAL),
    ],
    "XRP": [
        _e("2012", "XRP Ledger 上线", "采用独特节点共识（RPCA）的支付账本启动，无需挖矿。", S_OFFICIAL),
        _e("2020-12-22", "SEC 提起诉讼", "美国 SEC 起诉 Ripple，主张其 XRP 销售属未注册证券发行。", S_REG),
        _e("2023-07-13", "法院部分裁决", "纽约南区联邦法院裁定 XRP 本身不当然构成证券，机构直销与交易所程序化销售结论不同。", S_REG),
        _e("2024-08-07", "一审终判", "法院作出最终判决，对 Ripple 处以 1.2503515 亿美元民事罚款并发出禁令。", S_REG),
        _e("2025-08-07", "双方撤回上诉，案件终结", "SEC 与 Ripple 共同提交撤回上诉的联合协议，民事执法程序结束，一审判决继续有效。", S_REG),
    ],
    "DOGE": [
        _e("2013-12", "狗狗币发布", "Billy Markus 与 Jackson Palmer 以柴犬迷因创建社区型代币，采用通胀型无限供应。", S_OFFICIAL),
        _e("2014", "打赏文化形成", "社区用 DOGE 进行小额打赏与公益募捐，形成以社区为核心的使用场景。", S_MEDIA),
        _e("2021", "进入主流视野", "社交媒体带动关注度大幅上升，价格与讨论度高度受情绪驱动。", S_MEDIA),
    ],
    "LTC": [
        _e("2011-10", "莱特币发布", "Charlie Lee 基于比特币代码推出区块时间更短、采用 Scrypt 算法的支付币。", S_OFFICIAL),
        _e("2017", "SegWit 激活", "莱特币率先激活隔离见证，为闪电网络等方案铺路。", S_OFFICIAL),
        _e("2019-08", "第二次减半", "区块奖励由 25 LTC 降至 12.5 LTC。", S_OFFICIAL),
        _e("2022-05", "MWEB 隐私扩展激活", "MimbleWimble 扩展区块上线，提供可选的机密交易能力。", S_OFFICIAL),
    ],
    "ADA": [
        _e("2015", "项目启动", "Charles Hoskinson 离开以太坊后创立 IOHK，启动 Cardano。", S_MEDIA),
        _e("2017-09", "Byron 主网上线", "首个主网版本开放，支持 ADA 转账。", S_OFFICIAL),
        _e("2020-07", "Shelley 升级", "引入权益委托与社区质押池，向去中心化质押过渡。", S_OFFICIAL),
        _e("2021-09", "Alonzo 升级", "主网支持 Plutus 智能合约，链上应用生态起步。", S_OFFICIAL),
        _e("2022-09", "Vasil 升级", "提升脚本性能与吞吐量，优化 UTXO 处理。", S_OFFICIAL),
    ],
    "AVAX": [
        _e("2018", "Avalanche 共识论文", "Emin Gün Sirer 团队公布基于亚采样投票的共识研究。", S_OFFICIAL),
        _e("2020-09", "主网上线", "Avalanche 主网启动，包含 X / P / C 三条链结构。", S_OFFICIAL),
        _e("2022", "子网（Subnet）推广", "面向机构与游戏的专用子网成为主要扩展方向。", S_MEDIA),
    ],
    "DOT": [
        _e("2016", "Polkadot 白皮书", "Gavin Wood 提出中继链 + 平行链共享安全的跨链架构。", S_OFFICIAL),
        _e("2017-10", "DOT 公开销售", "通过代币销售为 Web3 基金会开发筹资。", S_OFFICIAL),
        _e("2020-05", "主网上线", "Polkadot 主网分阶段启动，先以 PoA 运行再过渡到 NPoS。", S_OFFICIAL),
        _e("2021-12", "首批平行链插槽拍卖完成", "平行链开始接入中继链共享安全性。", S_OFFICIAL),
    ],
    "LINK": [
        _e("2017-09", "LINK 代币发行", "Chainlink 通过代币销售筹资，目标是给智能合约提供链外数据。", S_OFFICIAL),
        _e("2019", "去中心化价格喂价上线", "多节点聚合的价格喂价网络成为 DeFi 借贷与衍生品的基础设施。", S_OFFICIAL),
        _e("2023", "CCIP 跨链协议发布", "推出跨链互操作协议，扩展到预言机之外的消息传递。", S_OFFICIAL),
    ],
    "UNI": [
        _e("2018-11", "Uniswap v1 上线", "Hayden Adams 在以太坊部署首个恒定乘积自动做市商协议。", S_OFFICIAL),
        _e("2020-05", "v2 发布", "加入 ERC-20 直接交易对、闪电兑换与价格预言机改进。", S_OFFICIAL),
        _e("2020-09", "UNI 治理代币发行", "向历史用户空投并启动协议治理。", S_OFFICIAL),
        _e("2021-05", "v3 发布", "引入集中流动性，做市商可指定价格区间。", S_OFFICIAL),
    ],
    "TRX": [
        _e("2017", "TRON 项目与代币发行", "孙宇晨创立 TRON，定位高吞吐的内容娱乐公链。", S_MEDIA),
        _e("2018-05", "主网上线", "TRON 独立主网启动，从 ERC-20 代币完成迁移。", S_OFFICIAL),
        _e("2018-07", "收购 BitTorrent", "把点对点文件分发协议纳入生态。", S_MEDIA),
        _e("2020", "USDT-TRC20 成为主要场景", "低费用稳定币转账成为链上最主要的交易场景之一。", S_MEDIA),
    ],
    "NEAR": [
        _e("2018", "NEAR 成立", "Illia Polosukhin 与 Alexander Skidanov 启动分片公链项目。", S_OFFICIAL),
        _e("2020-04", "主网上线", "NEAR 主网启动，支持人类可读账户名。", S_OFFICIAL),
        _e("2021", "Nightshade 分片推进", "分片扩容路线分阶段落地，同时推出账户抽象能力。", S_OFFICIAL),
    ],
    "ARB": [
        _e("2021-08", "Arbitrum One 开放", "Offchain Labs 的 Optimistic Rollup 二层网络向用户开放。", S_OFFICIAL),
        _e("2022-08", "Nitro 升级", "重写执行层，降低费用并提升吞吐。", S_OFFICIAL),
        _e("2023-03", "ARB 治理代币发行", "启动 DAO 治理并向生态用户空投。", S_OFFICIAL),
    ],
    "OP": [
        _e("2021", "OP Mainnet 开放", "Optimism 的 Optimistic Rollup 网络面向公众开放。", S_OFFICIAL),
        _e("2022-05", "OP 代币发行", "启动治理代币与 Optimism Collective 治理实验。", S_OFFICIAL),
        _e("2023", "OP Stack / Superchain", "开源 L2 技术栈，被多家机构用于搭建自己的链。", S_OFFICIAL),
    ],
    "ATOM": [
        _e("2016", "Cosmos 白皮书", "提出用 Tendermint 与 IBC 连接多条独立链的「区块链互联网」。", S_OFFICIAL),
        _e("2017", "ATOM 代币销售", "为 Cosmos Hub 开发筹资。", S_OFFICIAL),
        _e("2019-03", "Cosmos Hub 主网上线", "首个 Hub 启动，采用权益证明。", S_OFFICIAL),
        _e("2021-02", "Stargate / IBC 启用", "跨链通信协议正式上线，应用链之间可互传资产与消息。", S_OFFICIAL),
    ],
    "FIL": [
        _e("2014", "IPFS 项目启动", "Protocol Labs 发布星际文件系统设计。", S_OFFICIAL),
        _e("2017", "FIL 代币销售", "为 Filecoin 激励层开发筹资。", S_OFFICIAL),
        _e("2020-10", "Filecoin 主网上线", "存储矿工以复制证明 / 时空证明获取 FIL 奖励。", S_OFFICIAL),
    ],
    "AR": [
        _e("2018-06", "Arweave 主网上线", "以一次付费永久存储为目标的 Permaweb 网络启动。", S_OFFICIAL),
        _e("2018", "永久存储基金机制", "部分手续费进入长期 endowment，用于覆盖未来存储成本。", S_OFFICIAL),
        _e("2020", "永久网页归档普及", "NFT 元数据、网页快照与历史资料成为主要用途。", S_MEDIA),
    ],
    "SUI": [
        _e("2021", "Mysten Labs 成立", "原 Meta Diem / Novi 团队成员组建，采用 Move 语言。", S_MEDIA),
        _e("2023-05", "Sui 主网上线", "基于对象模型与并行执行的高吞吐 L1 正式运行。", S_OFFICIAL),
        _e("2023", "Move 生态起步", "面向游戏与高频交互应用的开发框架与工具链发布。", S_OFFICIAL),
    ],
    "APT": [
        _e("2021", "Aptos Labs 成立", "由原 Diem 团队成员 Mo Shaikh、Avery Ching 创立。", S_MEDIA),
        _e("2022-10", "Aptos 主网上线", "采用 Move 语言与 Block-STM 并行执行引擎。", S_OFFICIAL),
        _e("2023", "生态工具链完善", "钱包、索引与开发者 SDK 逐步齐备。", S_MEDIA),
    ],
    "INJ": [
        _e("2021", "Injective 主网上线", "面向金融应用、内置链上订单簿的 L1 启动。", S_OFFICIAL),
        _e("2022", "衍生品协议扩展", "链上永续合约与现货市场基础设施上线。", S_MEDIA),
        _e("2023", "INJ 销毁与质押机制", "协议费用回购销毁机制与质押治理推进。", S_MEDIA),
    ],
    "RENDER": [
        _e("2017", "RNDR 代币发行", "OTOY 推出分布式 GPU 渲染网络的代币。", S_OFFICIAL),
        _e("2020", "渲染算力市场上线", "创作者提交渲染任务，节点运营商提供闲置 GPU 并获得代币。", S_OFFICIAL),
        _e("2023", "迁移 Solana 并更名 RENDER", "网络迁移至 Solana，代币品牌统一为 RENDER。", S_OFFICIAL),
        _e("2024", "扩展到 AI 推理算力", "算力市场从 3D 渲染延伸到生成式 AI 工作负载。", S_MEDIA),
    ],
    "TAO": [
        _e("2021", "Bittensor 网络启动", "Opentensor 用代币激励把机器学习模型组织成竞争协作的子网。", S_OFFICIAL),
        _e("2023", "子网激励模型成型", "按模型输出质量分配 TAO 奖励的机制推广。", S_MEDIA),
        _e("2024", "子网数量扩张", "多个专用任务子网上线，形成去中心化 AI 市场。", S_MEDIA),
    ],
    "HYPE": [
        _e("2023", "Hyperliquid 上线", "自建 L1、把订单簿完全放到链上的永续合约交易所开放。", S_OFFICIAL),
        _e("2024-11", "HYPE 代币发行", "通过面向用户的空投完成代币分发。", S_MEDIA),
        _e("2025", "生态扩展", "现货交易与 HyperEVM 生态陆续上线。", S_MEDIA),
    ],
    "ENA": [
        _e("2024-02", "USDe 上线", "Ethena 推出以现货抵押 + 永续空头对冲构造的合成美元。", S_OFFICIAL),
        _e("2024-04", "ENA 治理代币发行", "启动治理与 sUSDe 质押收益产品。", S_OFFICIAL),
        _e("2024", "资金费率收益机制受关注", "收益来源为衍生品资金费率与质押利差，随市场正负波动。", S_MEDIA),
    ],
    "ONDO": [
        _e("2021", "Ondo Finance 成立", "专注把现实金融资产代币化的协议启动。", S_MEDIA),
        _e("2023", "USDY / OUSG 上线", "推出代币化美国国债与货币基金类产品。", S_OFFICIAL),
        _e("2024", "ONDO 治理代币流通", "协议治理与 RWA 产品线扩展。", S_MEDIA),
    ],
    "ZEC": [
        _e("2016-10", "Zcash 主网上线", "基于 zk-SNARK 提供可选 shielded 隐私交易。", S_OFFICIAL),
        _e("2017", "可信设置与基金会治理", "Electric Coin Company 与 Zcash 基金会分工推进协议。", S_MEDIA),
        _e("2022", "NU5 / Orchard 升级", "引入新的 shielded 池与统一地址改进。", S_OFFICIAL),
    ],
    "PEPE": [
        _e("2023-04", "PEPE 代币发行", "以佩佩蛙迷因主题的纯社区型代币在以太坊上线。", S_MEDIA),
        _e("2023", "无团队预留、无实用功能", "项目方声明无税、放弃合约权限，价格高度受社区情绪驱动。", S_MEDIA),
    ],
    "WIF": [
        _e("2023-11", "dogwifhat 发行", "柴犬戴帽迷因币在 Solana 上线。", S_MEDIA),
        _e("2024", "成为 Solana Meme 代表之一", "社区传播与交易所上架推动知名度上升。", S_MEDIA),
    ],
    "PUMP": [
        _e("2024-01", "Pump.fun 上线", "Solana 上一键发币与联合曲线内盘交易平台开放。", S_MEDIA),
        _e("2024", "市值门槛自动迁移 DEX", "内盘达到市值门槛后流动性自动迁移到去中心化交易所。", S_MEDIA),
        _e("2025", "PUMP 代币发行", "平台发行治理 / 生态代币。", S_MEDIA),
    ],
    # ============================== A 股 ==============================
    "SH:600519": [
        _e("1999", "贵州茅台酒股份有限公司成立", "由茅台集团等发起设立，主营茅台酒及系列酒的生产与销售。", S_IR),
        _e("2001-07-31", "A 股首次公开发行", "发行 7,150 万股，发行价 31.39 元。", S_EXCHANGE),
        _e("2001-08-27", "上交所挂牌上市", "股票代码 600519，上市板为主板。", S_EXCHANGE),
        _e("2000 年代", "高端白酒品牌化", "以茅台镇产区、稀缺产能与经销体系形成高毛利商业模式。", S_IR),
        _e("2010 年代", "系列酒与直营渠道建设", "在飞天茅台之外扩展系列酒产品，并逐步提高直营与数字化渠道占比。", S_IR),
    ],
    "SZ:300750": [
        _e("2011", "宁德时代成立", "曾毓群创办，总部位于福建宁德，专注动力电池研发制造。", S_IR),
        _e("2018-06-11", "创业板挂牌上市", "股票代码 300750，发行价 25.14 元。", S_EXCHANGE),
        _e("2018", "动力电池装机量居全球前列", "与国内外主流车企建立供应关系，业务同时覆盖储能电池。", S_IR),
        _e("2022", "麒麟电池 / 储能产品线扩展", "发布结构与热管理升级的电池产品，并扩大储能系统业务。", S_IR),
    ],
    "SZ:002594": [
        _e("1995", "比亚迪成立", "王传福创办，从二次充电电池业务起步。", S_IR),
        _e("2002", "H 股在香港上市", "比亚迪股份先行登陆港股市场。", S_EXCHANGE),
        _e("2011-06-30", "A 股深交所上市", "股票代码 002594，发行价 18.00 元。", S_EXCHANGE),
        _e("2020", "刀片电池发布", "推出磷酸铁锂刀片电池，强调安全性与体积利用率。", S_IR),
        _e("2022", "停产燃油整车", "公司宣布停止燃油汽车整车生产，聚焦新能源车。", S_IR),
    ],
    "SH:601318": [
        _e("1988", "中国平安成立", "马明哲创办于深圳，以保险业务起家。", S_IR),
        _e("2004-06-24", "H 股港交所上市", "股票代码 02318，开启境外上市。", S_EXCHANGE),
        _e("2007-03-01", "A 股上交所上市", "股票代码 601318，形成 A+H 双上市结构。", S_EXCHANGE),
        _e("2010 年代", "综合金融与科技生态", "业务由保险扩展至银行、资产管理，并布局医疗养老与金融服务科技。", S_IR),
    ],
    # ============================== 港股 ==============================
    "HK:00700": [
        _e("1998", "腾讯成立", "马化腾、张志东、许晨晔、陈一丹、曾李青在深圳创办。", S_IR),
        _e("1999", "OICQ / QQ 上线", "即时通信产品推出，后更名为 QQ。", S_IR),
        _e("2004-06-16", "港交所挂牌上市", "股票代码 00700，以即时通信与增值服务为主要业务。", S_EXCHANGE),
        _e("2011-01", "微信发布", "移动即时通信产品上线，随后成为社交、支付与小程序生态入口。", S_IR),
        _e("2010 年代", "游戏与数字内容扩张", "网络游戏、数字内容与云服务成为重要收入来源。", S_IR),
    ],
    "HK:09988": [
        _e("1999", "阿里巴巴成立", "马云等 18 位创始人在杭州创办，以 B2B 电商起步。", S_IR),
        _e("2003", "淘宝网上线", "进入 C2C 电商市场，次年推出支付宝。", S_IR),
        _e("2009", "阿里云成立", "开始建设自研云计算基础设施。", S_IR),
        _e("2014-09-19", "纽交所上市", "集团整体在纽约证券交易所挂牌，代码 BABA。", S_EXCHANGE),
        _e("2019-11-26", "港交所二次上市", "股票代码 09988，发行价 176 港元，成为当年全球融资规模最大的 IPO 之一。", S_EXCHANGE),
    ],
    "HK:03690": [
        _e("2010", "美团成立", "王兴创办，以团购业务起步。", S_IR),
        _e("2013", "美团外卖上线", "从到店团购扩展到即时配送的外卖业务。", S_IR),
        _e("2015", "与大众点评合并", "合并后形成本地生活服务平台格局。", S_MEDIA),
        _e("2018-09-20", "港交所挂牌上市", "股票代码 03690，为港交所同股不同权改革后的新经济公司之一。", S_EXCHANGE),
        _e("2020 年代", "即时零售与新业务", "在核心本地商业之外拓展即时零售、共享出行与海外业务。", S_IR),
    ],
    # ============================== 美股 ==============================
    "US:NVDA": [
        _e("1993", "NVIDIA 成立", "黄仁勋、Chris Malachowsky、Curtis Priem 创办，主攻图形处理芯片。", S_IR),
        _e("1999-01-22", "纳斯达克上市", "股票代码 NVDA。", S_EXCHANGE),
        _e("2006", "CUDA 发布", "把 GPU 推向通用并行计算，为后来的 AI 训练生态打基础。", S_IR),
        _e("2012", "深度学习带动数据中心业务", "GPU 被大规模用于神经网络训练，业务重心逐步从游戏显卡扩展。", S_IR),
        _e("2020 年代", "AI 算力平台化", "数据中心业务成为最大收入来源，产品覆盖 GPU、网络与服务器平台。", S_IR),
    ],
    "US:AAPL": [
        _e("1976", "Apple 成立", "史蒂夫·乔布斯、史蒂夫·沃兹尼亚克、罗纳德·韦恩创办。", S_IR),
        _e("1980-12-12", "纳斯达克上市", "股票代码 AAPL。", S_EXCHANGE),
        _e("2007", "iPhone 发布", "重新定义智能手机，并逐步构建 App Store 应用生态。", S_IR),
        _e("2010 年代", "服务业务与自研芯片", "订阅服务收入占比提高，Mac 与移动设备转向自研 Apple Silicon。", S_IR),
    ],
    "US:MSFT": [
        _e("1975", "Microsoft 成立", "比尔·盖茨与保罗·艾伦创办，以 BASIC 解释器起家。", S_IR),
        _e("1986-03-13", "纳斯达克上市", "股票代码 MSFT。", S_EXCHANGE),
        _e("1990 年代", "Windows 与 Office 普及", "操作系统与办公软件成为个人电脑时代的核心产品。", S_IR),
        _e("2010 年代", "Azure 云计算转型", "业务重心转向云服务与订阅制。", S_IR),
        _e("2020 年代", "AI 助手全线整合", "通过投资与产品整合把生成式 AI 能力嵌入办公与云服务。", S_IR),
    ],
    "US:TSLA": [
        _e("2003", "Tesla 成立", "马丁·艾伯哈德与马克·塔彭宁创办，马斯克为早期投资人并长期任 CEO。", S_IR),
        _e("2010-06-29", "纳斯达克上市", "股票代码 TSLA。", S_EXCHANGE),
        _e("2012", "Model S 交付", "推出首款大规模量产的高端纯电轿车，并建设超级充电网络。", S_IR),
        _e("2017", "Model 3 量产", "面向大众市场的车型投产，产能爬坡成为阶段焦点。", S_IR),
        _e("2020 年代", "储能与自动驾驶业务", "业务延伸至储能系统、辅助驾驶软件与机器人方向。", S_IR),
    ],
    "US:AMZN": [
        _e("1994", "Amazon 成立", "杰夫·贝索斯创办，以在线书店起步。", S_IR),
        _e("1997-05-15", "纳斯达克上市", "股票代码 AMZN。", S_EXCHANGE),
        _e("2000 年代", "第三方平台与 AWS", "开放 Marketplace 并推出云计算服务 AWS，后者成为主要利润来源。", S_IR),
        _e("2010 年代", "Prime / 广告 / 物流网络", "会员体系、广告业务与自建物流构成新的增长支柱。", S_IR),
    ],
    "US:GOOGL": [
        _e("1998", "Google 成立", "拉里·佩奇与谢尔盖·布林创办搜索引擎公司。", S_IR),
        _e("2004-08-19", "纳斯达克上市", "股票代码 GOOG / GOOGL。", S_EXCHANGE),
        _e("2006", "收购 YouTube", "把在线视频纳入产品与广告体系。", S_MEDIA),
        _e("2008", "Android 与 Chrome 发布", "移动操作系统与浏览器扩展生态边界。", S_IR),
        _e("2015", "Alphabet 控股架构", "成立 Alphabet 作为控股公司，Google 成为其子公司。", S_IR),
    ],
    "US:META": [
        _e("2004", "Facebook 成立", "马克·扎克伯格等在哈佛创办校园社交网络。", S_IR),
        _e("2012-05-18", "纳斯达克上市", "股票代码 FB，后更名 META。", S_EXCHANGE),
        _e("2012", "收购 Instagram", "移动端图片社交并入产品矩阵。", S_MEDIA),
        _e("2014", "收购 WhatsApp", "即时通信纳入应用家族，并加大 VR / AR 投入。", S_MEDIA),
        _e("2021", "更名 Meta Platforms", "公司更名并强调元宇宙与 AI 方向，同时开源 Llama 系列模型。", S_IR),
    ],
    # ====================== 新增主流品种发展历程 ======================
    # ---------------------------- A 股 ----------------------------
    "SH:601939": [
        _e("1954", "建设银行成立", "前身是主管基本建设拨款的专业银行，后改制为商业银行。", S_IR),
        _e("2005-10-27", "H 股港交所上市", "国有大行股改上市先行者。", S_EXCHANGE),
        _e("2007-09-25", "A 股上交所上市", "回归 A 股，完成 A+H 双上市。", S_EXCHANGE),
    ],
    "SH:601398": [
        _e("1984", "工商银行成立", "承接人民银行工商信贷与储蓄业务。", S_IR),
        _e("2006-10-27", "A 股与 H 股同步上市", "同日登陆 A 股与 H 股，为大型银行 A+H 同步发行先例。", S_EXCHANGE),
    ],
    "SH:601288": [
        _e("1951", "农业银行前身组建", "以服务三农与县域金融为特色。", S_IR),
        _e("2010-07-15", "A 股上交所上市", "A 股挂牌，次日 H 股在港上市。", S_EXCHANGE),
    ],
    "SH:601988": [
        _e("1912", "中国银行成立", "由大清银行改组而来，历史最久。", S_IR),
        _e("2006-06-01", "H 股港交所上市", "先于 A 股在港上市。", S_EXCHANGE),
        _e("2006-07-05", "A 股上交所上市", "回归 A 股，完成 A+H。", S_EXCHANGE),
    ],
    "SH:600941": [
        _e("1997-10-23", "H 股港交所上市", "以中国电信（香港）名义在港上市。", S_EXCHANGE),
        _e("2022-01-05", "A 股上交所上市", "回 A 募资规模居当年前列。", S_EXCHANGE),
    ],
    "SH:601857": [
        _e("1999", "中国石油重组", "由中国石油天然气总公司改制。", S_IR),
        _e("2000-04-07", "H 股港交所上市", "先于 A 股在港挂牌。", S_EXCHANGE),
        _e("2007-11-05", "A 股上交所上市", "回归 A 股。", S_EXCHANGE),
    ],
    "SH:600938": [
        _e("2001-02-28", "H 股港交所上市", "以中国海洋石油有限公司名义在港上市。", S_EXCHANGE),
        _e("2022-04-21", "A 股上交所上市", "回 A 上市。", S_EXCHANGE),
    ],
    "SH:600036": [
        _e("1987", "招商银行成立", "由招商局集团发起，总部深圳。", S_IR),
        _e("2002-04-09", "A 股深交所上市", "首批按国际标准改制的上市银行之一。", S_EXCHANGE),
        _e("2006-09-22", "H 股港交所上市", "完成 A+H。", S_EXCHANGE),
    ],
    "SH:601088": [
        _e("2004-06-15", "H 股港交所上市", "神华能源在港上市。", S_EXCHANGE),
        _e("2007-10-09", "A 股上交所上市", "回 A 上市，煤炭产运销一体化。", S_EXCHANGE),
    ],
    "SH:601628": [
        _e("1949", "中国人寿前身起步", "国内最早的人寿保险机构之一。", S_IR),
        _e("2003-12-18", "H 股港交所上市", "先于 A 股在港挂牌。", S_EXCHANGE),
        _e("2007-01-09", "A 股上交所上市", "回 A 上市。", S_EXCHANGE),
    ],
    "SH:688981": [
        _e("2000", "中芯国际成立", "张汝京创办，内地晶圆代工起步。", S_IR),
        _e("2004-03-18", "H 股港交所上市", "先于 A 股在港挂牌。", S_EXCHANGE),
        _e("2020-07-16", "A 股科创板上市", "回归科创板，国产半导体旗舰。", S_EXCHANGE),
    ],
    "SH:601138": [
        _e("2018-06-08", "A 股上交所上市", "工业富联登陆主板，主打云网与精密制造。", S_EXCHANGE),
    ],
    "SH:601899": [
        _e("2003-12-23", "H 股港交所上市", "紫金矿业在港挂牌。", S_EXCHANGE),
        _e("2008-04-25", "A 股上交所上市", "回 A 上市，黄金铜矿为主。", S_EXCHANGE),
    ],
    # ---------------------------- 港股 ----------------------------
    "HK:00939": [
        _e("1954", "建设银行成立", "前身是基本建设拨款专业银行。", S_IR),
        _e("2005-10-27", "H 股港交所上市", "国有大行股改上市先行者。", S_EXCHANGE),
    ],
    "HK:00005": [
        _e("1865", "汇丰创立", "创于香港与上海，服务远东贸易。", S_IR),
        _e("1990s", "香港上市", "在香港交易所挂牌，成为蓝筹权重股。", S_EXCHANGE),
    ],
    "HK:00941": [
        _e("1997-10-23", "H 股港交所上市", "以中国电信（香港）名义上市。", S_EXCHANGE),
    ],
    "HK:00883": [
        _e("2001-02-28", "H 股港交所上市", "中国海洋石油在港挂牌。", S_EXCHANGE),
    ],
    "HK:01299": [
        _e("2010-10-29", "H 股港交所上市", "从 AIG 分拆独立上市。", S_EXCHANGE),
    ],
    "HK:01810": [
        _e("2010", "小米成立", "雷军等创办，主攻智能手机。", S_IR),
        _e("2018-07-09", "H 股港交所上市", "同股不同权架构上市。", S_EXCHANGE),
    ],
    "HK:09999": [
        _e("1997", "网易成立", "丁磊创办，以自研游戏见长。", S_IR),
        _e("2000-06-30", "纳斯达克上市", "先行赴美上市。", S_EXCHANGE),
        _e("2020-06-11", "港股二次上市", "回港二次上市。", S_EXCHANGE),
    ],
    "HK:02388": [
        _e("2002-07-25", "H 股港交所上市", "中银香港在港挂牌，香港主要发钞行。", S_EXCHANGE),
    ],
    "HK:03988": [
        _e("1912", "中国银行成立", "历史最久的银行之一。", S_IR),
        _e("2006-06-01", "H 股港交所上市", "先于 A 股在港上市。", S_EXCHANGE),
    ],
    "HK:00388": [
        _e("2000", "香港交易所成立", "联交所与期交所合并并上市。", S_EXCHANGE),
    ],
    "HK:02318": [
        _e("1988", "中国平安成立", "以保险业务起家。", S_IR),
        _e("2004-06-24", "H 股港交所上市", "先于 A 股在港上市。", S_EXCHANGE),
    ],
    "HK:00267": [
        _e("1986", "中信泰富在港上市", "中信集团旗下上市平台。", S_EXCHANGE),
        _e("2014", "集团整体上市", "中信股份绝大部分资产注入，实现整体上市。", S_IR),
    ],
    # ---------------------------- 美股 ----------------------------
    "US:GOOG": [
        _e("1998", "Google 成立", "佩奇与布林创办搜索引擎公司。", S_IR),
        _e("2004-08-19", "纳斯达克上市", "发行 GOOG（A 类）与 GOOGL（B 类）；GOOG 为无投票权 C 类。", S_EXCHANGE),
        _e("2015", "Alphabet 控股架构", "成立 Alphabet，Google 成为子公司。", S_IR),
    ],
    "US:TSM": [
        _e("1987", "台积电成立", "张忠谋创办，开创纯晶圆代工模式。", S_IR),
        _e("1997-10-08", "纽交所 ADR 上市", "以 TSM 代码在纽约证券交易所挂牌。", S_EXCHANGE),
    ],
    "US:AVGO": [
        _e("2009-08-06", "Avago 上市", "安华高在纳斯达克上市。", S_EXCHANGE),
        _e("2016", "与博通合并", "Avago 收购博通并沿用 Broadcom 名称。", S_MEDIA),
    ],
    "US:LLY": [
        _e("1876", "礼来成立", "美国历史最久的制药企业之一。", S_IR),
        _e("2020s", "GLP-1 药物放量", "降糖与减重药物推动市值跃升。", S_IR),
    ],
    "US:WMT": [
        _e("1962", "沃尔玛创立", "山姆·沃尔顿创办首家折扣店。", S_IR),
        _e("1972-08-25", "纽交所上市", "登陆纽约证券交易所。", S_EXCHANGE),
    ],
    "US:JPM": [
        _e("2000", "摩根大通合并", "J.P. Morgan 与 Chase Manhattan 合并。", S_MEDIA),
        _e("2000s", "综合银行成型", "形成投行、商行、资管与支付的综合平台。", S_IR),
    ],
    "US:AMD": [
        _e("1969", "AMD 成立", "Jerry Sanders 创办。", S_IR),
        _e("1972-09-27", "公开上市", "完成首次公开募股。", S_EXCHANGE),
    ],
    "US:MU": [
        _e("1978", "美光成立", "总部爱达荷州，专注存储芯片。", S_IR),
        _e("1984", "公开上市", "完成首次公开募股。", S_EXCHANGE),
    ],
    "US:V": [
        _e("1958", "银行卡计划启动", "作为银行信用卡计划诞生。", S_IR),
        _e("2008-03-19", "纽交所独立 IPO", "从母公司分拆独立上市。", S_EXCHANGE),
    ],
    "US:JNJ": [
        _e("1886", "强生成立", "以无菌外科敷料起家。", S_IR),
        _e("1944", "纽约证券交易所上市", "登陆纽交所。", S_EXCHANGE),
    ],
    "US:SPCX": [
        _e("2002", "SpaceX 成立", "马斯克创办，目标降低发射成本。", S_IR),
        _e("2010", "龙飞船首飞", "首次商业飞船补给国际空间站。", S_MEDIA),
        _e("2019", "星链部署", "低轨卫星互联网开始组网。", S_MEDIA),
        _e("2020s", "星舰试飞", "可完全重复使用重型火箭进入试飞阶段。", S_MEDIA),
    ],
}


# ---------------------------------------------------------------------------
# 品种档案：可核对的结构化字段
# ---------------------------------------------------------------------------
def _a(**kw) -> dict:
    return {k: v for k, v in kw.items() if v is not None}


ARCHIVE: Dict[str, dict] = {
    "BTC": _a(category="加密资产 · 点对点支付网络", launch="2009-01-03",
              consensus="工作量证明 PoW（SHA-256）", supply_cap="2100 万枚（协议固定上限）",
              website="bitcoin.org", doc="bitcoin.org/bitcoin.pdf（白皮书）"),
    "ETH": _a(category="公链 · 智能合约平台", launch="2015-07-30",
              consensus="权益证明 PoS（2022-09-15 起）", supply_cap="无固定上限",
              website="ethereum.org", doc="ethereum.org/en/whitepaper/"),
    "SOL": _a(category="公链 · 高性能 L1", launch="2020-03（主网 Beta）",
              consensus="PoH + 权益证明", website="solana.com"),
    "BNB": _a(category="交易所生态 · 公链", launch="2017-07",
              consensus="权益权威证明 PoSA", website="bnbchain.org"),
    "XRP": _a(category="跨境支付网络", launch="2012",
              consensus="RPCA 独特节点共识（无挖矿）", supply_cap="1000 亿枚（创世一次性发行）",
              website="ripple.com / xrpl.org"),
    "DOGE": _a(category="Meme 币 · 支付", launch="2013-12",
               consensus="工作量证明 Scrypt（辅助挖矿）", supply_cap="无固定上限（通胀型）",
               website="dogecoin.com"),
    "LTC": _a(category="加密资产 · 支付", launch="2011-10",
              consensus="工作量证明 Scrypt", supply_cap="8400 万枚",
              website="litecoin.org"),
    "ADA": _a(category="公链 · 学术驱动", launch="2017-09",
              consensus="Ouroboros 权益证明", supply_cap="450 亿枚",
              website="cardano.org"),
    "UNI": _a(category="DeFi · 去中心化交易所", launch="2018-11（协议）/ 2020-09（代币）",
              consensus="以太坊智能合约（非独立链）", website="uniswap.org"),
    "LINK": _a(category="去中心化预言机", launch="2017-09（代币）",
               consensus="以太坊智能合约 / 链下节点网络", website="chain.link"),
    "SH:600519": _a(category="白酒 · 食品饮料", exchange="上海证券交易所 · 主板",
                    listing_date="2001-08-27", ipo_price="31.39 元",
                    hq="贵州省仁怀市茅台镇", website="moutaichina.com",
                    board="主板"),
    "SZ:300750": _a(category="电力设备 · 电池", exchange="深圳证券交易所 · 创业板",
                    listing_date="2018-06-11", ipo_price="25.14 元",
                    hq="福建省宁德市", website="catl.com", board="创业板"),
    "SZ:002594": _a(category="汽车 · 乘用车 / 新能源", exchange="深圳证券交易所 · 主板",
                    listing_date="2011-06-30", ipo_price="18.00 元",
                    hq="广东省深圳市", website="byd.com", board="主板"),
    "SH:601318": _a(category="金融 · 综合保险", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2007-03-01（A 股）/ 2004-06-24（H 股）",
                    hq="广东省深圳市", website="pingan.cn", board="主板"),
    "HK:00700": _a(category="互联网 · 社交与游戏", exchange="香港交易所 · 主板",
                   listing_date="2004-06-16", hq="广东省深圳市",
                   website="tencent.com", board="主板"),
    "HK:09988": _a(category="电商 · 云计算", exchange="香港交易所 · 主板（二次上市）",
                   listing_date="2019-11-26", ipo_price="176 港元（港股二次上市）",
                   hq="浙江省杭州市", website="alibabagroup.com", board="主板"),
    "HK:03690": _a(category="本地生活服务", exchange="香港交易所 · 主板",
                   listing_date="2018-09-20", hq="北京市",
                   website="meituan.com", board="主板 / 同股不同权"),
    "US:NVDA": _a(category="半导体 · AI 算力", exchange="纳斯达克（NASDAQ）",
                  listing_date="1999-01-22", hq="美国加州圣克拉拉",
                  website="nvidia.com"),
    "US:AAPL": _a(category="消费电子 · 生态", exchange="纳斯达克（NASDAQ）",
                  listing_date="1980-12-12", hq="美国加州库比蒂诺",
                  website="apple.com"),
    "US:MSFT": _a(category="软件 · 云计算", exchange="纳斯达克（NASDAQ）",
                  listing_date="1986-03-13", hq="美国华盛顿州雷德蒙德",
                  website="microsoft.com"),
    "US:TSLA": _a(category="电动车 · 能源", exchange="纳斯达克（NASDAQ）",
                  listing_date="2010-06-29", hq="美国得州奥斯汀",
                  website="tesla.com"),
    "US:AMZN": _a(category="电商 · 云计算", exchange="纳斯达克（NASDAQ）",
                  listing_date="1997-05-15", hq="美国华盛顿州西雅图",
                  website="amazon.com"),
    "US:GOOGL": _a(category="搜索 · 云计算 · AI", exchange="纳斯达克（NASDAQ）",
                   listing_date="2004-08-19", hq="美国加州山景城",
                   website="abc.xyz"),
    "US:META": _a(category="社交 · 广告 · AI", exchange="纳斯达克（NASDAQ）",
                  listing_date="2012-05-18", hq="美国加州门洛帕克",
                  website="about.meta.com"),
    # ====================== 新增主流品种档案 ======================
    # ---------------------------- A 股 ----------------------------
    "SH:601939": _a(category="银行 · 国有大行", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2007-09-25（A 股）/ 2005-10-27（H 股）",
                    hq="北京市", website="ccb.com", board="主板"),
    "SH:601398": _a(category="银行 · 国有大行", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2006-10-27（A+H 同步）", hq="北京市",
                    website="icbc.com.cn", board="主板"),
    "SH:601288": _a(category="银行 · 国有大行", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2010-07-15（A 股）", hq="北京市",
                    website="abchina.com", board="主板"),
    "SH:601988": _a(category="银行 · 国有大行", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2006-07-05（A 股）/ 2006-06-01（H 股）",
                    hq="北京市", website="boc.cn", board="主板"),
    "SH:600941": _a(category="通信服务 · 运营商", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2022-01-05（A 股）/ 1997-10-23（H 股）",
                    hq="北京市", website="chinamobileltd.com", board="主板"),
    "SH:601857": _a(category="石油石化 · 能源", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2007-11-05（A 股）/ 2000-04-07（H 股）",
                    hq="北京市", website="petrochina.com.cn", board="主板"),
    "SH:600938": _a(category="石油石化 · 能源", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2022-04-21（A 股）/ 2001-02-28（H 股）",
                    hq="北京市", website="cnoocltd.com", board="主板"),
    "SH:600036": _a(category="银行 · 股份制", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2002-04-09（A 股）/ 2006-09-22（H 股）",
                    hq="广东省深圳市", website="cmbchina.com", board="主板"),
    "SH:601088": _a(category="煤炭 · 电力 · 能源", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2007-10-09（A 股）/ 2004-06-15（H 股）",
                    hq="北京市", website="shenhuachina.com", board="主板"),
    "SH:601628": _a(category="保险 · 寿险", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2007-01-09（A 股）/ 2003-12-18（H 股）",
                    hq="北京市", website="chinalife.com.cn", board="主板"),
    "SH:688981": _a(category="半导体 · 晶圆代工", exchange="上海证券交易所 · 科创板（A+H）",
                    listing_date="2020-07-16（A 股）/ 2004-03-18（H 股）",
                    hq="上海市", website="smics.com", board="科创板"),
    "SH:601138": _a(category="电子制造 · 服务器", exchange="上海证券交易所 · 主板",
                    listing_date="2018-06-08", hq="广东省深圳市",
                    website="fii-foxconn.com", board="主板"),
    "SH:601899": _a(category="有色金属 · 黄金铜矿", exchange="上海证券交易所 · 主板（A+H）",
                    listing_date="2008-04-25（A 股）/ 2003-12-23（H 股）",
                    hq="福建省龙岩市", website="zijinmining.com", board="主板"),
    # ---------------------------- 港股 ----------------------------
    "HK:00939": _a(category="银行 · 国有大行", exchange="香港交易所 · 主板",
                   listing_date="2005-10-27", hq="北京市", website="ccb.com", board="主板"),
    "HK:00005": _a(category="银行 · 国际银行", exchange="香港交易所 · 主板",
                   listing_date="香港上市（历史悠久）", hq="英国伦敦 / 香港",
                   website="hsbc.com", board="主板"),
    "HK:00941": _a(category="通信服务 · 运营商", exchange="香港交易所 · 主板",
                   listing_date="1997-10-23", hq="北京市",
                   website="chinamobileltd.com", board="主板"),
    "HK:00883": _a(category="石油石化 · 能源", exchange="香港交易所 · 主板",
                   listing_date="2001-02-28", hq="北京市",
                   website="cnoocltd.com", board="主板"),
    "HK:01299": _a(category="保险 · 寿险", exchange="香港交易所 · 主板",
                   listing_date="2010-10-29", hq="中国香港",
                   website="aia.com", board="主板"),
    "HK:01810": _a(category="消费电子 · IoT", exchange="香港交易所 · 主板（同股不同权）",
                   listing_date="2018-07-09", hq="北京市",
                   website="mi.com", board="主板 / W 股"),
    "HK:09999": _a(category="互联网 · 游戏", exchange="香港交易所 · 主板（二次上市）",
                   listing_date="2020-06-11", ipo_price="123 港元（港股二次上市）",
                   hq="浙江省杭州市", website="ir.netease.com", board="主板 / S 股"),
    "HK:02388": _a(category="银行 · 香港本地", exchange="香港交易所 · 主板",
                   listing_date="2002-07-25", hq="中国香港",
                   website="bochk.com", board="主板"),
    "HK:03988": _a(category="银行 · 国有大行", exchange="香港交易所 · 主板",
                   listing_date="2006-06-01", hq="北京市", website="boc.cn", board="主板"),
    "HK:00388": _a(category="交易所 · 金融基础设施", exchange="香港交易所 · 主板",
                   listing_date="2000", hq="中国香港", website="hkex.com.hk", board="主板"),
    "HK:02318": _a(category="综合金融 · 保险", exchange="香港交易所 · 主板（A+H）",
                   listing_date="2004-06-24（H 股）/ 2007-03-01（A 股）",
                   hq="广东省深圳市", website="pingan.cn", board="主板"),
    "HK:00267": _a(category="综合企业 · 央企", exchange="香港交易所 · 主板",
                   listing_date="2014（整体上市）/ 1986（中信泰富上市）",
                   hq="中国香港", website="citic.com", board="主板"),
    # ---------------------------- 美股 ----------------------------
    "US:GOOG": _a(category="搜索 · 云计算 · AI", exchange="纳斯达克（NASDAQ）",
                  listing_date="2004-08-19", hq="美国加州山景城", website="abc.xyz"),
    "US:TSM": _a(category="半导体 · 晶圆代工", exchange="纽约证券交易所（ADR）",
                 listing_date="1997-10-08", hq="中国台湾新竹", website="tsmc.com"),
    "US:AVGO": _a(category="半导体 · 通信芯片", exchange="纳斯达克（NASDAQ）",
                  listing_date="2009-08-06（Avago）/ 2016 合并", hq="美国加州帕洛阿尔托",
                  website="broadcom.com"),
    "US:LLY": _a(category="医药 · 生物制药", exchange="纽约证券交易所（NYSE）",
                 listing_date="纽约证券交易所上市（历史悠久）",
                 hq="美国印第安纳州印第安纳波利斯", website="lilly.com"),
    "US:WMT": _a(category="零售 · 商超", exchange="纽约证券交易所（NYSE）",
                 listing_date="1972-08-25", hq="美国阿肯色州本顿维尔",
                 website="walmart.com"),
    "US:JPM": _a(category="银行 · 综合金融", exchange="纽约证券交易所（NYSE）",
                 listing_date="纽约证券交易所上市", hq="美国纽约",
                 website="jpmorganchase.com"),
    "US:AMD": _a(category="半导体 · CPU/GPU", exchange="纳斯达克（NASDAQ）",
                 listing_date="1972-09-27", hq="美国加州圣克拉拉", website="amd.com"),
    "US:MU": _a(category="半导体 · 存储", exchange="纳斯达克（NASDAQ）",
                listing_date="1984（IPO）", hq="美国爱达荷州博伊西", website="micron.com"),
    "US:V": _a(category="支付 · 清算网络", exchange="纽约证券交易所（NYSE）",
               listing_date="2008-03-19", hq="美国加州旧金山湾区", website="visa.com"),
    "US:JNJ": _a(category="医药 · 消费健康", exchange="纽约证券交易所（NYSE）",
                 listing_date="1944", hq="美国新泽西州新不伦瑞克", website="jnj.com"),
    "US:SPCX": _a(category="航空航天 · 私营", exchange="未公开上市（二级份额转让）",
                  listing_date="— 未上市", hq="美国得州与加州", website="spacex.com"),
}

# 档案字段在 UI 上的中文标题与顺序
ARCHIVE_FIELDS = (
    ("category", "品种类别"), ("exchange", "上市交易所"), ("board", "上市板块"),
    ("listing_date", "上市日期"), ("launch", "创立 / 主网上线"),
    ("ipo_price", "发行价"), ("hq", "总部 / 注册地"),
    ("consensus", "共识 / 机制"), ("supply_cap", "供应上限"),
    ("website", "官方网站"), ("doc", "白皮书 / 文档"),
)

_EXCHANGE_BY_MARKET = {
    "cn": "中国内地证券交易所（沪深）",
    "hk": "香港交易所",
    "us": "美国证券市场",
    "crypto": "加密资产（多交易所交易）",
}


def covered(symbol: str) -> bool:
    """该品种是否有结构化发展历程资料。"""
    return (symbol or "").upper() in TIMELINE


def timeline(symbol: str) -> List[dict]:
    """按时间正序返回该品种的里程碑；未收录返回空列表。

    返回的每条都保证含 date / title / detail / src 四个键，UI 不需要再做
    判空或补全；日期只按字符串排序（YYYY / YYYY-MM / YYYY-MM-DD 天然有序）。
    """
    rows = TIMELINE.get((symbol or "").upper())
    if not rows:
        return []
    return sorted((dict(x) for x in rows), key=lambda x: x.get("date") or "")


def archive(symbol: str) -> dict:
    """返回档案字段；未收录品种只给能由代码推断的交易所，其余留白。

    绝不用「同类品种的典型值」填充某一只具体股票 / 币的档案。
    """
    key = (symbol or "").upper()
    hit = ARCHIVE.get(key)
    if hit:
        out = dict(hit)
        out["covered"] = True
        out["source"] = SOURCE_NOTE
        return out
    mkt = market_of(key)
    out = {"covered": False, "source": SOURCE_NOTE}
    if key.startswith("ONCHAIN:"):
        out["exchange"] = "链上 DEX（合约地址交易）"
        out["category"] = "链上合约代币"
    elif mkt in _EXCHANGE_BY_MARKET:
        out["exchange"] = _EXCHANGE_BY_MARKET[mkt]
    return out


def sources(symbol: str) -> List[str]:
    """该品种发展历程引用到的来源类型（去重，供「数据来源」卡展示）。"""
    seen: List[str] = []
    for ev in timeline(symbol):
        s = ev.get("src") or S_MEDIA
        if s not in seen:
            seen.append(s)
    return seen


def stats() -> dict:
    """资料库规模（供测试与「关于」页展示）。"""
    return {"symbols": len(TIMELINE),
            "events": sum(len(v) for v in TIMELINE.values()),
            "archive": len(ARCHIVE), "verified_at": VERIFIED_AT}


def short_date(date: str) -> str:
    """把 YYYY-MM-DD 规范成 UI 用的紧凑日期；已是年/月则原样返回。"""
    s = str(date or "").strip()
    if not re.match(r"^\d{4}(-\d{2})?(-\d{2})?$", s):
        return s or "—"
    return s
