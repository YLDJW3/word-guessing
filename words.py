# -*- coding: utf-8 -*-
"""Curated pool of everyday Chinese words used as candidate secret answers.

These are common nouns / verbs / adjectives that are reliably present in the
Tencent embedding vocabulary, so a randomly chosen secret is always guessable.
game.py intersects this list with the loaded vocab at startup and drops any
that happen to be missing.
"""

CANDIDATE_WORDS = [
    # 动物 animals
    "猫", "狗", "老虎", "大象", "熊猫", "兔子", "老鼠", "马", "牛", "羊",
    "猴子", "狮子", "鲨鱼", "鲸鱼", "蝴蝶", "蜜蜂", "青蛙", "乌龟", "麻雀", "老鹰",
    # 食物 food
    "苹果", "香蕉", "西瓜", "葡萄", "橘子", "米饭", "面条", "包子", "饺子", "面包",
    "牛奶", "鸡蛋", "豆腐", "辣椒", "巧克力", "咖啡", "啤酒", "蛋糕", "披萨", "火锅",
    # 自然 nature
    "太阳", "月亮", "星星", "天空", "海洋", "河流", "高山", "森林", "沙漠", "草原",
    "下雨", "下雪", "台风", "彩虹", "闪电", "花朵", "树木", "石头", "泥土", "火焰",
    # 情感 / 抽象 emotions & abstract
    "爱", "恨", "快乐", "悲伤", "愤怒", "恐惧", "希望", "梦想", "孤独", "幸福",
    "自由", "勇气", "友谊", "回忆", "时间", "命运", "真理", "秘密", "谎言", "缘分",
    # 日常物品 everyday objects
    "手机", "电脑", "电视", "汽车", "自行车", "飞机", "火车", "轮船", "雨伞", "眼镜",
    "钥匙", "钱包", "书本", "铅笔", "椅子", "桌子", "沙发", "冰箱", "洗衣机", "空调",
    # 地点 places
    "学校", "医院", "银行", "公园", "机场", "车站", "超市", "餐厅", "图书馆", "博物馆",
    "城市", "乡村", "海边", "山顶", "工厂", "办公室", "教室", "厨房", "卧室", "花园",
    # 人物 / 职业 people & roles
    "老师", "学生", "医生", "护士", "警察", "士兵", "工人", "农民", "厨师", "司机",
    "画家", "歌手", "作家", "科学家", "运动员", "父亲", "母亲", "孩子", "朋友", "陌生人",
    # 活动 / 动词 activities
    "跑步", "游泳", "唱歌", "跳舞", "睡觉", "读书", "画画", "旅行", "购物", "做饭",
    "工作", "学习", "比赛", "战争", "和平", "结婚", "毕业", "旅游", "运动", "休息",
    # 颜色 & 形容 colors & descriptors
    "红色", "蓝色", "绿色", "黑色", "白色", "金色", "美丽", "丑陋", "聪明", "勇敢",
    "温柔", "冷静", "疯狂", "神秘", "危险", "安全", "寒冷", "炎热", "明亮", "黑暗",
    # 时间 / 节日 time & festivals
    "春天", "夏天", "秋天", "冬天", "早晨", "夜晚", "周末", "假期", "春节", "生日",
    # 概念 concepts
    "音乐", "电影", "游戏", "历史", "科学", "艺术", "文化", "语言", "数学", "宇宙",
]

# De-duplicate while keeping order.
CANDIDATE_WORDS = list(dict.fromkeys(CANDIDATE_WORDS))
