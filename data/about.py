# -*- coding: utf-8 -*-
"""品种背景资料：项目 / 公司 / 产品 / 创始人。

行情接口只给数字，用户看不懂「这个代码背后是什么」。这里维护一份离线
中文资料库，覆盖主流加密资产与常见股票，字段统一为：

    title     项目/公司中文名
    category  类型（公链 / 交易所 / 支付网络 / 白酒 / 半导体 …）
    founder   创始人 / 核心创办者 / 现任掌门
    since     创立或上市年份
    product   代表产品或主营业务
    summary   一段介绍（做什么、靠什么、有什么特点）
    source    资料来源说明

离线优先：断网、刚启动、后台线程还没回来时也能立刻显示，不阻塞界面。
未收录的品种按市场生成兜底简介，保证「资料」一栏永远不是空白。
"""
from data import timeline as timeline_db
from data.universe import market_of, name_of

_MARKET_DEFAULT = {
    "crypto": {"category": "加密资产", "product": "链上代币",
               "summary": "该品种为加密资产，价格由市场供需决定，波动通常较高。"
                          "详情可查看项目官网、白皮书与链上浏览器。"},
    "cn": {"category": "A 股上市公司", "product": "主营业务见公司年报",
           "summary": "该公司在中国内地证券交易所上市，业务与财务数据"
                      "以定期报告与交易所公告为准。"},
    "hk": {"category": "港股上市公司", "product": "主营业务见公司年报",
           "summary": "该公司在中国香港交易所上市，业务与财务数据"
                      "以港交所披露易公告为准。"},
    "us": {"category": "美股上市公司", "product": "主营业务见公司财报",
           "summary": "该公司在美国证券市场上市，业务与财务数据"
                      "以 SEC 备案文件与季度财报为准。"},
}

# symbol -> 资料。股票 key 用统一代码（SH:600519 / HK:00700 / US:NVDA）。
ABOUT = {
    # ---------------- 加密资产 ----------------
    "BTC": dict(title="比特币 Bitcoin", category="加密资产 · 点对点支付网络",
                founder="中本聪 Satoshi Nakamoto（匿名）", since="2009",
                product="BTC 代币、比特币区块链",
                summary="第一个真正落地的去中心化数字货币。总量固定 2100 万枚，"
                        "由全球节点通过工作量证明共同记账，约每四年产量减半。"
                        "定位更接近「数字黄金」与价值储存，而非支付应用。"),
    "ETH": dict(title="以太坊 Ethereum", category="公链 · 智能合约平台",
                founder="Vitalik Buterin 等 8 位联合创始人", since="2015",
                product="ETH、EVM 智能合约、Layer2 生态",
                summary="首个图灵完备的智能合约公链，DeFi、NFT、稳定币与"
                        "绝大多数链上应用的底层结算层。2022 年转为权益证明，"
                        "并通过 EIP-1559 引入基础费销毁机制。"),
    "SOL": dict(title="Solana", category="公链 · 高性能 L1",
                founder="Anatoly Yakovenko、Raj Gokal", since="2020",
                product="SOL、Solana 主网、Firedancer 客户端",
                summary="以历史证明 PoH 配合权益证明实现高吞吐、低费用，"
                        "主攻高频交易、支付与消费级链上应用。生态以 DePIN、"
                        "Meme 与 DEX 交易活跃著称。"),
    "BNB": dict(title="BNB / BNB Chain", category="交易所生态 · 公链",
                founder="赵长鹏 CZ（币安创始人）", since="2017",
                product="BNB、BNB Smart Chain、币安交易所",
                summary="最初是币安交易所的平台币，后扩展为 BNB Chain 公链生态，"
                        "用于支付链上手续费、参与 Launchpad 与链上治理。"),
    "XRP": dict(title="XRP / Ripple", category="跨境支付网络",
                founder="Chris Larsen、Jed McCaleb、David Schwartz",
                since="2012",
                product="XRP Ledger、RippleNet 跨境结算",
                summary="面向银行与支付机构的低成本跨境清算网络，"
                        "XRP 作为桥接资产。2020 年 12 月美国 SEC 起诉 Ripple，"
                        "2023 年 7 月法院作出部分裁决，2024 年 8 月一审终判"
                        "（1.25 亿美元民事罚款）；2025 年 8 月 7 日双方共同"
                        "撤回上诉，案件终结，一审判决继续有效。"),
    "DOGE": dict(title="狗狗币 Dogecoin", category="Meme 币 · 支付",
                 founder="Billy Markus、Jackson Palmer", since="2013",
                 product="DOGE 代币",
                 summary="从柴犬表情包玩笑起步的社区型加密货币，"
                        "采用通胀型无限供应，以打赏、小额支付与强社区文化闻名。"),
    "LTC": dict(title="莱特币 Litecoin", category="加密资产 · 支付",
                founder="Charlie Lee 李启威", since="2011",
                product="LTC 代币",
                summary="比特币的早期分叉改进版，区块时间更短、采用 Scrypt 算法，"
                        "常被称作「数字白银」，用于快速小额转账。"),
    "ADA": dict(title="Cardano", category="公链 · 学术驱动",
                founder="Charles Hoskinson（以太坊联合创始人）", since="2017",
                product="ADA、Ouroboros 权益证明",
                summary="以同行评审与形式化验证为特色的权益证明公链，"
                        "由 IOHK / Emurgo / Cardano 基金会共同推进，"
                        "强调可持续性与链上治理。"),
    "AVAX": dict(title="Avalanche", category="公链 · 子网架构",
                 founder="Emin Gün Sirer、Ava Labs", since="2020",
                 product="AVAX、Avalanche C-Chain、Subnet 子网",
                 summary="主打可定制子网与快速最终性的 L1，"
                        "机构级资产上链与游戏专用链是其主要落地方向。"),
    "DOT": dict(title="Polkadot", category="跨链 · 中继链",
                founder="Gavin Wood（以太坊联合创始人）", since="2020",
                product="DOT、Substrate 开发框架、平行链",
                summary="通过中继链 + 平行链让多条专用链共享安全性与互操作性，"
                        "Substrate 是业内常用的区块链开发框架。"),
    "LINK": dict(title="Chainlink", category="去中心化预言机",
                 founder="Sergey Nazarov、Steve Ellis", since="2017",
                 product="LINK、CCIP、价格喂价网络",
                 summary="为智能合约提供链外数据（价格、天气、赛事等）的"
                        "去中心化预言机网络，是 DeFi 基础设施的关键一环。"),
    "UNI": dict(title="Uniswap", category="DeFi · 去中心化交易所",
                founder="Hayden Adams", since="2018",
                product="UNI、Uniswap AMM 协议",
                summary="以太坊上最大的自动做市商协议，用恒定乘积公式"
                        "替代传统订单簿，UNI 为协议治理代币。"),
    "TRX": dict(title="TRON", category="公链 · 内容娱乐",
                founder="孙宇晨 Justin Sun", since="2017",
                product="TRX、TRON 主网、USDT-TRC20",
                summary="面向高吞吐与低费用的公链，链上稳定币转账"
                        "（尤其 USDT-TRC20）是其主要使用场景。"),
    "NEAR": dict(title="NEAR Protocol", category="公链 · 分片",
                 founder="Illia Polosukhin、Alexander Skidanov", since="2020",
                 product="NEAR、Nightshade 分片、账户抽象",
                 summary="以可用性和开发者体验为核心的权益证明公链，"
                        "采用分片扩容并支持人类可读账户名。"),
    "ARB": dict(title="Arbitrum", category="以太坊 Layer2",
                founder="Offchain Labs（Steven Goldfeder 等）", since="2021",
                product="Arbitrum One、Nitro、ARB 治理代币",
                summary="基于 Optimistic Rollup 的以太坊二层网络，"
                        "把交易搬到链下批量执行再回传主网，手续费显著更低。"),
    "OP": dict(title="Optimism", category="以太坊 Layer2",
               founder="Optimism PBC（Jinglan Wang、Ben Jones 等）",
               since="2021",
               product="OP Mainnet、OP Stack、Superchain",
               summary="Optimistic Rollup 二层网络，OP Stack 开源后被多家"
                        "交易所与项目用于搭建自己的 L2 链。"),
    "ATOM": dict(title="Cosmos", category="跨链生态",
                 founder="Ethan Buchman、Jae Kwon", since="2019",
                 product="ATOM、Tendermint、IBC 协议",
                 summary="「区块链互联网」思路：用 Tendermint 共识 + IBC 协议"
                        "让各条应用专用链互相通信。"),
    "FIL": dict(title="Filecoin", category="去中心化存储",
                founder="Juan Benet / Protocol Labs", since="2020",
                product="FIL、IPFS 激励层",
                summary="把闲置硬盘空间组织成可验证的分布式存储市场，"
                        "存储提供者需提交复制证明与时空证明。"),
    "AR": dict(title="Arweave", category="永久存储",
               founder="Andrew Williams、Sam Williams", since="2018",
               product="AR、Permaweb 永久网络",
               summary="一次付费、永久保存数据的存储网络，常用于"
                        "NFT 元数据、网页归档与链上历史资料。"),
    "SUI": dict(title="Sui", category="公链 · 对象模型",
                founder="Mysten Labs（Evan Cheng 等，原 Meta Diem 团队）",
                since="2023",
                product="SUI、Move 语言、Sui 主网",
                summary="基于 Move 语言与对象-centric 数据模型的高吞吐 L1，"
                        "支持并行执行，面向游戏与高频交互应用。"),
    "APT": dict(title="Aptos", category="公链 · Move",
                founder="Aptos Labs（Mo Shaikh、Avery Ching，原 Diem 团队）",
                since="2022",
                product="APT、Aptos 主网、Block-STM",
                summary="同样源自 Meta Diem 技术路线，用 Block-STM 并行执行"
                        "提升吞吐，强调安全性与可升级性。"),
    "INJ": dict(title="Injective", category="金融专用 L1",
                founder="Eric Chen 等 / Injective Labs", since="2021",
                product="INJ、链上订单簿、衍生品协议",
                summary="为 DeFi 交易打造的公链，内置链上订单簿与"
                        "衍生品基础设施，支持现货、永续合约市场。"),
    "RENDER": dict(title="Render Network", category="分布式 GPU 渲染",
                   founder="Jules Urbach / OTOY", since="2020",
                   product="RNDR / RENDER、GPU 算力市场",
                   summary="把闲置 GPU 算力对接给 3D 渲染与 AI 推理需求，"
                           "创作者付费获取算力，节点运营商获得代币奖励。"),
    "TAO": dict(title="Bittensor", category="去中心化 AI",
                founder="Jacob Steeves、Ala Shaabana（Opentensor）",
                since="2021",
                product="TAO、子网激励网络",
                summary="用代币激励把机器学习模型组织成竞争协作的"
                        "「智能市场」，按模型贡献分配 TAO 奖励。"),
    "HYPE": dict(title="Hyperliquid", category="链上衍生品交易所",
                 founder="Jeff Yan 等（Hyperliquid 团队）", since="2023",
                 product="HYPE、HyperCore 链上永续合约",
                 summary="自建 L1 的链上永续合约交易所，把订单簿完全放到链上，"
                         "以低延迟、无 KYC 与自建流动性著称。"),
    "ENA": dict(title="Ethena", category="合成美元稳定币",
                founder="Guy Young / Ethena Labs", since="2024",
                product="USDe、sUSDe、ENA 治理代币",
                summary="用现货抵押 + 永续合约空头对冲构造 delta 中性"
                        "合成美元 USDe，收益来自资金费率与质押利差。"),
    "ONDO": dict(title="Ondo Finance", category="RWA 现实资产上链",
                 founder="Nathan Allman 等", since="2021",
                 product="USDY、OUSG 代币化美债",
                 summary="把美国国债、货币基金等现实资产代币化，"
                         "为链上资金提供合规收益类产品。"),
    "ZEC": dict(title="Zcash", category="隐私币",
                founder="Zooko Wilcox / Electric Coin Company", since="2016",
                product="ZEC、zk-SNARK  shielded 交易",
                summary="基于零知识证明的可选隐私加密货币，"
                        " shielded 地址可隐藏交易双方与金额。"),
    "PEPE": dict(title="Pepe", category="Meme 币",
                 founder="匿名社区项目", since="2023",
                 product="PEPE 代币",
                 summary="以「佩佩蛙」网络迷因为主题的纯社区型 Meme 币，"
                         "无团队预留与实用功能，价格高度受情绪驱动。"),
    "WIF": dict(title="dogwifhat", category="Meme 币 · Solana 生态",
                founder="匿名社区项目", since="2023",
                product="WIF 代币",
                summary="Solana 上走红的柴犬戴帽迷因币，"
                        "社区传播是其最主要的价值来源。"),
    "PUMP": dict(title="Pump.fun", category="Meme 币发行平台",
                 founder="Noah Tweedale 等", since="2024",
                 product="一键发币平台、 bonding curve 内盘",
                 summary="Solana 上的一键发币与内盘交易平台，"
                         "用联合曲线定价，达到市值门槛后自动迁移到 DEX。"),
    # ---------------- 股票 ----------------
    "SH:600519": dict(title="贵州茅台", category="白酒 · 消费",
                      founder="中国贵州茅台酒厂（集团）有限责任公司",
                      since="1999 成立 / 2001 上市",
                      product="飞天茅台、系列酒",
                      summary="中国高端白酒龙头，产自贵州仁怀茅台镇，"
                              "以稀缺产能、经销体系与品牌溢价著称，"
                              "是 A 股最具代表性的高毛利消费股。"),
    "SZ:300750": dict(title="宁德时代 CATL", category="动力电池 · 新能源",
                      founder="曾毓群", since="2011 成立 / 2018 上市",
                      product="动力电池、储能电池、麒麟电池",
                      summary="全球动力电池装机量长期居首，客户覆盖国内外"
                              "主流车企，同时布局储能系统与电池回收。"),
    "SZ:002594": dict(title="比亚迪", category="新能源车 · 电池",
                      founder="王传福", since="1995 成立 / 2011 A 股上市",
                      product="王朝/海洋系列电动车、刀片电池、半导体",
                      summary="从电池起家的新能源整车企业，垂直整合电池、"
                              "电机、电控与车规级芯片，兼营电子代工。"),
    "SH:601318": dict(title="中国平安", category="综合金融 · 保险",
                      founder="马明哲", since="1988 成立 / 2004 港股上市",
                      product="寿险、财险、银行、资产管理",
                      summary="国内领先的综合金融集团，以保险为核心，"
                              "并向银行、科技与医疗养老生态延伸。"),
    "HK:00700": dict(title="腾讯控股", category="互联网 · 社交与游戏",
                     founder="马化腾、张志东、许晨晔、陈一丹、曾李青",
                     since="1998 成立 / 2004 港股上市",
                     product="微信、QQ、王者荣耀、腾讯云、金融科技",
                     summary="中国最大的社交与游戏平台公司，"
                             "业务覆盖社交、数字内容、云服务与支付，"
                             "并持有大量互联网公司股权。"),
    "HK:09988": dict(title="阿里巴巴-W", category="电商 · 云计算",
                     founder="马云等 18 位创始人", since="1999 成立 / 2019 港股上市",
                     product="淘宝天猫、阿里云、菜鸟、国际数字商业",
                     summary="以电商平台起家，阿里云是国内领先的公有云厂商，"
                             "近年聚焦电商与云两大核心、推进组织与资本结构改革。"),
    "HK:03690": dict(title="美团-W", category="本地生活服务",
                     founder="王兴", since="2010 成立 / 2018 港股上市",
                     product="美团外卖、到店酒旅、即时零售",
                     summary="以团购起家的本地生活平台，"
                             "外卖与到店业务为核心，并拓展即时零售与海外业务。"),
    "US:NVDA": dict(title="NVIDIA 英伟达", category="半导体 · AI 算力",
                   founder="黄仁勋 Jensen Huang、Chris Malachowsky、"
                           "Curtis Priem",
                   since="1993 成立 / 1999 上市",
                   product="GPU、CUDA、H100/Blackwell、AI 服务器平台",
                   summary="从游戏显卡起家，凭 CUDA 生态成为 AI 训练与推理"
                           "算力的核心供应商，数据中心业务已是最大收入来源。"),
    "US:AAPL": dict(title="Apple 苹果", category="消费电子 · 生态",
                   founder="史蒂夫·乔布斯、史蒂夫·沃兹尼亚克、罗纳德·韦恩",
                   since="1976 成立 / 1980 上市",
                   product="iPhone、Mac、iPad、App Store、服务订阅",
                   summary="全球最大的消费电子公司之一，"
                           "以自研芯片 + 硬件软件一体化生态 + 服务收入构建护城河。"),
    "US:MSFT": dict(title="Microsoft 微软", category="软件 · 云计算",
                   founder="比尔·盖茨、保罗·艾伦", since="1975 成立 / 1986 上市",
                   product="Windows、Office、Azure、Copilot",
                   summary="以操作系统与办公软件起家，Azure 为全球第二大公有云，"
                           "近年通过投资与整合把 AI 助手嵌入全线产品。"),
    "US:TSLA": dict(title="Tesla 特斯拉", category="电动车 · 能源",
                   founder="马丁·艾伯哈德、马克·塔彭宁（埃隆·马斯克"
                           "为早期投资人并长期任 CEO）",
                   since="2003 成立 / 2010 上市",
                   product="Model 3/Y、Cybertruck、储能、FSD 辅助驾驶",
                   summary="推动电动车主流化的整车厂，"
                           "业务延伸至储能、充电网络、自动驾驶与机器人。"),
    "US:AMZN": dict(title="Amazon 亚马逊", category="电商 · 云计算",
                   founder="杰夫·贝索斯", since="1994 成立 / 1997 上市",
                   product="电商自营与三方平台、AWS、Prime、广告",
                   summary="全球最大电商平台之一，AWS 是其利润核心，"
                           "另有广告、流媒体与物流网络。"),
    "US:GOOGL": dict(title="Alphabet / Google", category="搜索 · 云计算 · AI",
                    founder="拉里·佩奇、谢尔盖·布林",
                    since="1998 成立 / 2004 上市",
                    product="Google 搜索、YouTube、Android、Gemini、GCP",
                    summary="以搜索引擎与广告为基本盘，旗下还有 YouTube、"
                            "Android、Google Cloud 与 DeepMind 的 AI 研究。"),
    "US:META": dict(title="Meta Platforms", category="社交 · 广告 · AI",
                   founder="马克·扎克伯格等", since="2004 成立 / 2012 上市",
                   product="Facebook、Instagram、WhatsApp、Quest、Llama",
                   summary="全球最大社交广告平台之一，"
                           "同时开源 Llama 模型并长期投入 VR/AR 与元宇宙。"),
    # ---------------- 新增主流品种（A股 / 港股 / 美股 TOP） ----------------
    # ===== A 股（国有大行 / 能源 / 运营商 / 半导体 / 有色） =====
    "SH:601939": dict(title="建设银行", category="银行 · 国有大行",
                      founder="中央汇金投资有限责任公司（控股股东）",
                      since="1954 成立 / 2005 港股 / 2007 A股",
                      product="存贷款、理财、投行、托管",
                      summary="中国四大国有商业银行之一，前身是 1954 年成立的"
                              "基本建设拨款银行，后改制为商业银行；业务以公司"
                              "金融、个人金融与资金业务为主，境内网点密集，"
                              "并在香港等境外市场展业。"),
    "SH:601398": dict(title="工商银行", category="银行 · 国有大行",
                      founder="财政部、中央汇金（发起股东）",
                      since="1984 成立 / 2006 A+H 同步上市",
                      product="存贷款、结算、理财、投行",
                      summary="按资产规模长期居全球前列的商业银行，2006 年 A 股"
                              "与 H 股同步上市；业务覆盖公司、个人、机构与"
                              "金融市场，境内外一体化经营。"),
    "SH:601288": dict(title="农业银行", category="银行 · 国有大行",
                      founder="中央汇金、财政部（发起股东）",
                      since="1951 前身 / 2010 A+H 上市",
                      product="涉农金融、存贷款、理财",
                      summary="以服务三农与县域金融为特色的大型国有商业银行，"
                              "网点下沉至县乡，2010 年 A 股与 H 股先后上市。"),
    "SH:601988": dict(title="中国银行", category="银行 · 国有大行",
                      founder="由大清银行改组（1912 年成立）",
                      since="1912 成立 / 2006 A+H 上市",
                      product="外汇结算、存贷款、投行",
                      summary="中国持续经营时间最久的银行，国际化与外汇业务"
                              "历史最长，2006 年先后登陆 H 股与 A 股，"
                              "海外机构覆盖面广。"),
    "SH:600941": dict(title="中国移动", category="通信服务 · 运营商",
                      founder="中国电信体制改革组建",
                      since="1997 港股 / 2022 A股",
                      product="移动通信、宽带、算力网络",
                      summary="中国规模最大的移动通信运营商，用户数与营收居"
                              "行业首位，1997 年先在港股上市、2022 年回归 A 股，"
                              "同时布局算力与政企数字化。"),
    "SH:601857": dict(title="中国石油", category="石油石化 · 能源",
                      founder="国家石油公司改制",
                      since="1999 重组 / 2000 港股 / 2007 A股",
                      product="勘探开采、炼油、化工、销售",
                      summary="上中下游一体化的国有能源巨头，业务涵盖油气"
                              "勘探开发、炼化与成品油销售、化工与管道运输，"
                              "2007 年 A 股上市。"),
    "SH:600938": dict(title="中国海油", category="石油石化 · 能源",
                      founder="中国海洋石油总公司改制",
                      since="2001 港股 / 2022 A股",
                      product="海上油气勘探开发、天然气",
                      summary="以海上油气勘探开发为主营的国有能源企业，"
                              "2001 年登陆 H 股、2022 年回归 A 股，"
                              "在国内海域与海外均有油气资产。"),
    "SH:600036": dict(title="招商银行", category="银行 · 股份制",
                      founder="招商局集团发起",
                      since="1987 成立 / 2002 A股 / 2006 港股",
                      product="零售银行、财富管理、信用卡",
                      summary="以零售银行与财富管理见长的股份制商业银行，"
                              "零售客户与信用卡业务行业领先，2002 年 A 股上市。"),
    "SH:601088": dict(title="中国神华", category="煤炭 · 电力 · 能源",
                      founder="神华集团改制",
                      since="2004 港股 / 2007 A股",
                      product="煤炭、发电、铁路、港口、煤化工",
                      summary="煤炭产运销一体化、并向电力延伸的综合能源企业，"
                              "拥有煤矿、铁路与港口的纵向产业链，2007 年 A 股上市。"),
    "SH:601628": dict(title="中国人寿", category="保险 · 寿险",
                      founder="中国人寿保险（集团）公司",
                      since="1949 起步 / 2003 港股 / 2007 A股",
                      product="寿险、年金、健康险、资管",
                      summary="中国最大的寿险公司之一，2003 年先行 H 股上市、"
                              "2007 年回归 A 股，主营人寿、年金与资产管理业务。"),
    "SH:688981": dict(title="中芯国际", category="半导体 · 晶圆代工",
                      founder="张汝京等",
                      since="2000 成立 / 2004 港股 / 2020 科创板",
                      product="集成电路晶圆代工",
                      summary="中国内地规模最大的集成电路晶圆代工厂，提供从"
                              "成熟到先进节点的代工服务，2020 年登陆科创板。"),
    "SH:601138": dict(title="工业富联", category="电子制造 · 服务器",
                      founder="富士康工业互联网（鸿海旗下）",
                      since="2018 A股上市",
                      product="云计算服务器、通信设备、精密制造",
                      summary="鸿海集团旗下工业互联网平台，主营云网设备、"
                              "通信网络设备与精密结构件，2018 年 A 股上市，"
                              "深度参与 AI 服务器代工。"),
    "SH:601899": dict(title="紫金矿业", category="有色金属 · 黄金铜矿",
                      founder="福建省上杭县矿业公司改制",
                      since="2003 港股 / 2008 A股",
                      product="黄金、铜、锌等矿产开采冶炼",
                      summary="以黄金与铜为主的多金属矿业集团，通过国内外"
                              "并购持续扩张资源储量，2008 年 A 股上市。"),
    # ===== 港股（银行 / 运营商 / 保险 / 科技 / 交易所） =====
    "HK:00939": dict(title="建设银行", category="银行 · 国有大行",
                     founder="中央汇金（控股股东）",
                     since="1954 成立 / 2005 港股 / 2007 A股",
                     product="存贷款、理财、投行",
                     summary="中国四大国有商业银行之一，2005 年先于 H 股上市，"
                             "是国有大行股改上市的先行者，业务覆盖全牌照"
                             "商业银行业务。"),
    "HK:00005": dict(title="汇丰控股", category="银行 · 国际银行",
                     founder="1865 年创于香港与上海",
                     since="1865 创立",
                     product="环球银行、工商金融、财富管理",
                     summary="总部位于伦敦、根植香港与上海的国际性银行集团，"
                             "在亚洲、欧洲与北美均有布局，是港交所蓝筹权重股。"),
    "HK:00941": dict(title="中国移动", category="通信服务 · 运营商",
                     founder="中国电信体制改革组建",
                     since="1997 港股上市",
                     product="移动通信、宽带、算力网络",
                     summary="中国规模最大的移动通信运营商，1997 年即在港股"
                             "上市，并为恒生指数重磅成分股，同步推进算力与"
                             "政企业务。"),
    "HK:00883": dict(title="中国海洋石油", category="石油石化 · 能源",
                     founder="中国海洋石油总公司改制",
                     since="2001 港股上市",
                     product="海上油气勘探开发、天然气",
                     summary="以海上油气勘探开发为主营的国有能源企业，"
                             "2001 年登陆 H 股，国内外均有油气资产。"),
    "HK:01299": dict(title="友邦保险", category="保险 · 寿险",
                     founder="原美国国际集团 AIG 亚太业务",
                     since="2010 港股上市",
                     product="寿险、健康险、退休金",
                     summary="泛亚地区领先的人寿保险集团，2010 年从 AIG 分拆"
                             "并在港独立上市，深耕中国内地、香港、东南亚市场。"),
    "HK:01810": dict(title="小米集团-W", category="消费电子 · IoT",
                     founder="雷军等",
                     since="2010 成立 / 2018 港股上市",
                     product="智能手机、IoT 设备、汽车",
                     summary="以智能手机起家的消费电子与 IoT 公司，2018 年港股"
                             "上市（同股不同权），近年切入智能电动车赛道。"),
    "HK:09999": dict(title="网易-S", category="互联网 · 游戏",
                     founder="丁磊",
                     since="1997 成立 / 2000 纳斯达克 / 2020 港股二次上市",
                     product="游戏、有道、云音乐、电商",
                     summary="以自研游戏见长的互联网公司，2000 年先行赴美上市，"
                             "2020 年在港二次上市，游戏、教育（有道）与音乐并重。"),
    "HK:02388": dict(title="中银香港", category="银行 · 香港本地",
                     founder="中国银行（香港）有限公司",
                     since="2002 港股上市",
                     product="零售银行、人民币业务、跨境金融",
                     summary="中国银行在港旗舰机构，香港主要发钞行与人民币"
                             "清算行，2002 年于港交所上市。"),
    "HK:03988": dict(title="中国银行", category="银行 · 国有大行",
                     founder="1912 年成立",
                     since="1912 创立 / 2006 港股 / 2006 A股",
                     product="外汇结算、存贷款、投行",
                     summary="国际化与外汇业务历史最长的国有大行，2006 年 H 股"
                             "上市后很快回归 A 股，海外机构覆盖面广。"),
    "HK:00388": dict(title="香港交易所", category="交易所 · 金融基础设施",
                     founder="香港期货交易与联交所合并",
                     since="2000 港股上市",
                     product="上市、交易、结算、数据服务",
                     summary="香港证券市场的运营者与金融基础设施，2000 年完成"
                             "联交所与期交所合并并上市，业务含现货、衍生品与结算。"),
    "HK:02318": dict(title="中国平安", category="综合金融 · 保险",
                     founder="马明哲",
                     since="1988 成立 / 2004 港股上市",
                     product="寿险、财险、银行、资产管理",
                     summary="国内领先的综合金融集团，以保险为核心并向银行、"
                             "科技与医疗养老生态延伸，2004 年先于 H 股上市。"),
    "HK:00267": dict(title="中信股份", category="综合企业 · 央企",
                     founder="中信集团",
                     since="1986 港股（中信泰富）/ 2014 整体上市",
                     product="金融、资源能源、制造、地产",
                     summary="中信集团在港上市旗舰，2014 年集团绝大部分资产"
                             "注入实现整体上市，业务横跨金融、资源、制造与地产。"),
    # ===== 美股（半导体 / 医药 / 零售 / 金融 / 支付） =====
    "US:GOOG": dict(title="Alphabet / Google（C 类）", category="搜索 · 云计算 · AI",
                    founder="拉里·佩奇、谢尔盖·布林",
                    since="1998 成立 / 2004 上市",
                    product="Google 搜索、YouTube、Android、Gemini、GCP",
                    summary="与 GOOGL 同属 Alphabet 的普通股，区别在无投票权；"
                            "业务与 GOOGL 完全一致，搜索广告为基本盘，"
                            "并拥有 YouTube、Android、Google Cloud 与 DeepMind。"),
    "US:TSM": dict(title="台积电 TSMC", category="半导体 · 晶圆代工",
                   founder="张忠谋",
                   since="1987 成立 / 1997 纽交所 ADR",
                   product="先进与成熟制程晶圆代工",
                   summary="全球最大的半导体晶圆代工厂，为苹果、英伟达等"
                           "设计公司代工，1997 年于纽约证券交易所挂牌 ADR。"),
    "US:AVGO": dict(title="Broadcom 博通", category="半导体 · 通信芯片",
                    founder="Avago（2005）/ 2016 与博通合并",
                    since="1961 前身 / 2009 Avago 上市 / 2016 合并",
                    product="网络芯片、无线射频、企业软件",
                    summary="由 Avago 与博通 2016 年合并而成的半导体与"
                            "基础设施软件公司，产品覆盖网络、宽带、无线"
                            "与 VMware 等企业软件。"),
    "US:LLY": dict(title="Eli Lilly 礼来", category="医药 · 生物制药",
                   founder="Eli Lilly 上校",
                   since="1876 成立 / 纽约证券交易所上市",
                   product="糖尿病、肿瘤、免疫、减重药物",
                   summary="美国历史最悠久的制药企业之一，近年凭借 GLP-1 类"
                           "降糖与减重药物成为全球医药市值前列公司。"),
    "US:WMT": dict(title="Walmart 沃尔玛", category="零售 · 商超",
                   founder="山姆·沃尔顿",
                   since="1962 创立 / 1972 纽交所上市",
                   product="大卖场、山姆会员店、电商",
                   summary="全球最大的零售商，以连锁大卖场与会员制仓储店"
                           "（山姆会员店）为核心，并大力发展电商与全渠道履约。"),
    "US:JPM": dict(title="JPMorgan Chase 摩根大通", category="银行 · 综合金融",
                   founder="2000 由 J.P. Morgan 与 Chase 合并",
                   since="2000 合并 / 渊源可溯至 1799",
                   product="商业与投资银行、资管、支付",
                   summary="美国资产规模最大的银行控股公司之一，由 J.P. Morgan "
                           "与 Chase Manhattan 于 2000 年合并而成，业务覆盖"
                           "投行、商行、资管与证券交易。"),
    "US:AMD": dict(title="AMD 超威半导体", category="半导体 · CPU/GPU",
                   founder="Jerry Sanders",
                   since="1969 成立 / 1972 上市",
                   product="CPU、GPU、数据中心与嵌入式处理器",
                   summary="与英特尔、英伟达竞争的芯片公司，在 PC 与服务器 CPU、"
                           "独立显卡及数据中心加速器领域持续扩张。"),
    "US:MU": dict(title="Micron 美光", category="半导体 · 存储",
                  founder="Ward Parkinson 等",
                  since="1978 成立 / 1984 上市",
                  product="DRAM、NAND 闪存",
                  summary="全球主要存储芯片厂商之一，主营 DRAM 与 NAND 闪存，"
                          "受益于 AI 服务器对高带宽内存（HBM）的需求增长。"),
    "US:V": dict(title="Visa 维萨", category="支付 · 清算网络",
                 founder="1958 年作为银行信用卡计划",
                 since="2008 纽交所上市",
                 product="银行卡清算、跨境支付网络",
                 summary="全球最大的银行卡支付清算网络之一，自身不发卡、不授信，"
                         "靠交易清算与跨境手续费盈利，2008 年完成独立 IPO。"),
    "US:JNJ": dict(title="Johnson & Johnson 强生", category="医药 · 消费健康",
                   founder="Robert Wood Johnson 等",
                   since="1886 成立 / 纽约证券交易所上市",
                   product="处方药、医疗器械、消费品",
                   summary="业务横跨处方药、医疗器械与消费健康的跨国医疗企业，"
                           "旗下拥有众多知名非处方药与医疗器械品牌。"),
    "US:SPCX": dict(title="SpaceX", category="航空航天 · 私营",
                    founder="埃隆·马斯克",
                    since="2002 成立",
                    product="猎鹰火箭、龙飞船、星链、星舰",
                    summary="私营航天与卫星互联网公司，主营可回收运载火箭、"
                            "载人/货运飞船与星链（Starlink）低轨卫星互联网；"
                            "未公开上市，行情价格来自二级份额转让估值，仅供参考。"),
}


def _attach_db(out: dict, symbol: str) -> dict:
    """把 v37 的发展历程 / 档案挂到 about() 返回值上。

    时间线是「有没有」而不是「要不要补」：资料库未收录就是空列表 +
    NO_DATA 提示，界面据此明确留白，不用通用市场说明冒充具体品种历史。
    """
    sym = (symbol or "").upper()
    tl = timeline_db.timeline(sym)
    out["timeline"] = tl
    out["timeline_note"] = (timeline_db.SOURCE_NOTE if tl
                            else timeline_db.NO_DATA)
    out["timeline_sources"] = timeline_db.sources(sym)
    out["timeline_verified_at"] = timeline_db.VERIFIED_AT
    out["archive"] = timeline_db.archive(sym)
    out["archive_fields"] = [list(x) for x in timeline_db.ARCHIVE_FIELDS]
    return out


def about(symbol: str, name: str = "") -> dict:
    """取品种背景资料；未收录时按市场给出兜底简介。

    返回键（原有）：title / category / founder / since / product /
    summary / source。

    阶段 1 增加结构化分区：background（项目背景）、business（业务介绍）、
    highlights（核心特点）、purpose（项目用途）、outlook（发展前景）。
    **这些分区只重组资料库里已经核实的字段，不新增任何事实陈述，也不写
    预测性内容**；没有依据的分区一律为 None，由界面显示「暂无公开资料」。
    代币分配 / 解锁 / 协议收入 / 营收 / 利润同理保持 None —— 本程序目前
    没有接入对应数据源，宁可留白也不编造。

    v37 准确性修正：资料库未收录的品种，不再把「市场通用说明」塞进
    business / highlights / purpose 冒充该品种的业务与特点，这些分区
    一律为 None；新增 timeline / archive 两组结构化资料（见 timeline.py）。
    """
    # 链上合约地址大小写敏感，且资料库里没有对应的项目背景；
    # 直接返回「可核实字段 + 明确留白」，不要用加密货币通用简介冒充。
    if isinstance(symbol, str) and symbol.startswith("ONCHAIN:"):
        from data import onchain
        addr = onchain.address_of(symbol)
        chain = onchain.chain_of(addr) or "公链"
        out = {
            "title": name or onchain.short_address(addr),
            "category": f"{chain} 链上合约代币",
            "founder": None, "since": None, "product": None,
            "summary": None, "background": None, "business": None,
            "highlights": None, "purpose": None, "outlook": None,
            "contract": addr, "source": "链上合约地址",
            "source_note": "项目背景 / 业务 / 核心特点 / 前景暂无公开资料，"
                           "不展示推测内容",
            "covered": False,
        }
        return _attach_db(out, symbol)
    sym = (symbol or "").upper()
    hit = ABOUT.get(sym)
    if hit:
        out = dict(hit)
        out["source"] = "内置资料库"
        out["source_note"] = "内置离线资料库（公开资料整理）"
        covered = True
    else:
        mkt = market_of(sym)
        d = dict(_MARKET_DEFAULT.get(mkt, _MARKET_DEFAULT["crypto"]))
        label = name or name_of(sym) or sym.split(":")[-1]
        out = {
            "title": label,
            "category": d["category"],
            "founder": "—",
            "since": "—",
            "product": d["product"],
            "summary": ("资料库未收录该品种的结构化介绍。以下为市场通用说明，"
                        f"不代表该品种的业务或背景事实：{d['summary']}"),
            "source": "市场通用说明（非该品种资料）",
            "source_note": "资料库未收录该品种；通用说明不作为该品种背景",
        }
        covered = False

    founder = out.get("founder") or ""
    since = out.get("since") or ""
    bits = []
    if since and since != "—":
        # since 本身可能已经是「1999 成立 / 2001 上市」，别再叠一遍
        bits.append(since if any(w in since for w in ("成立", "上市", "创立"))
                    else f"{since} 创立 / 上市")
    if founder and founder != "—":
        bits.append(f"创始团队：{founder}")
    if covered:
        # 只把已有字段拼成一句背景，不添加任何新事实
        out["background"] = (f"{out.get('title') or sym}：" +
                             "，".join(bits) + "。") if bits else None
        out["business"] = out.get("product") or None
        out["highlights"] = out.get("summary") or None
        out["purpose"] = (
            f"{out.get('category') or ''}；{out.get('product') or ''}".strip("；")
            or None)
    else:
        # 未收录：通用市场说明不得冒充 business / highlights / purpose
        out["background"] = None
        out["business"] = None
        out["highlights"] = None
        out["purpose"] = None
    # 以下均为「暂无公开数据」，界面会明确标注，不得填充推测值
    out["outlook"] = None
    out["token_allocation"] = None
    out["unlock_schedule"] = None
    out["protocol_revenue"] = None
    out["revenue"] = None
    out["profit"] = None
    out["liquidity"] = None
    out["covered"] = covered
    return _attach_db(out, sym)
