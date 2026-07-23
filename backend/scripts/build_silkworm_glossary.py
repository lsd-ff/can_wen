"""Build a traceable silkworm-domain glossary from Markdown corpora.

The script deliberately uses a curated seed vocabulary instead of treating every
high-frequency token as a domain term. Each retained term is checked against the
input documents, receives exact-match evidence, and is exported as reviewable
Markdown, structured JSON, and a Jieba/BM25 user dictionary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


SCHEMA_LABELS = {
    "Disease": "疾病/病害",
    "DiseaseCategory": "疾病类别",
    "Cause": "病原/致病因素",
    "Symptom": "典型病征",
    "Lesion": "病理变化",
    "Part": "侵染/受害部位",
    "Route": "传播/侵入/暴露途径",
    "Condition": "发生条件/诱因",
    "Stage": "发病阶段/时期",
    "Diagnosis": "诊断依据",
    "Measure": "防治措施",
}

AUXILIARY_LABELS = {
    "DomainConcept": "领域通用概念",
    "HusbandryOperation": "饲养生产操作",
    "FacilityTool": "场所/设施/蚕具",
    "DisinfectantDrug": "消毒剂/药剂",
    "MaterialFeed": "物料/桑叶/样本",
    "MetricUnit": "指标/参数/单位",
}


@dataclass(frozen=True)
class Seed:
    name: str
    label: str
    subtype: str = ""
    aliases: tuple[str, ...] = ()
    related_terms: tuple[str, ...] = ()
    note: str = ""
    keep_if_missing: bool = False


def terms(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


DISEASE_GROUPS: list[tuple[str, list[str]]] = [
    ("病毒病", terms("核型多角体病|质型多角体病|病毒性软化病|浓核病|隐潜病毒病")),
    ("细菌病", terms("细菌性败血病|细菌性中毒病|细菌性肠道病")),
    (
        "真菌病",
        terms("白僵病|黄僵病|绿僵病|曲霉病|灰僵病|黑僵病|赤僵病|草僵病|镰刀菌病|酵母菌病"),
    ),
    (
        "微孢子虫病/原生动物病",
        terms("微粒子病|具褶孢子虫病|泰罗汉孢子虫病|锥虫病|变形虫病|球虫病"),
    ),
    ("线虫寄生病", terms("线虫病")),
    ("节肢动物病害", terms("多化性蝇蛆病|蛹蛆病|蒲螨病")),
    ("其他非传染性病害", terms("蜇伤症|创伤病")),
    (
        "农药/药剂中毒",
        terms(
            "有机磷杀虫剂中毒|有机氮农药中毒|有机氯农药中毒|拟除虫菊酯类杀虫剂中毒|"
            "沙蚕毒素类杀虫剂中毒|氨基甲酸酯类杀虫剂中毒|新烟碱类杀虫剂中毒|"
            "苯醚类杀虫剂中毒|抗生素类杀虫剂中毒|植物源类杀虫剂中毒|鱼尼丁受体类杀虫剂中毒"
        ),
    ),
    (
        "工业废气/化学因素/重金属中毒",
        terms(
            "氟化物中毒|二氧化硫中毒|硫化氢中毒|氯化物中毒|碘化物中毒|氮化物中毒|"
            "煤气中毒|镉中毒|锌中毒|铅、砷和铜中毒"
        ),
    ),
    ("饲料/叶质因素病害", terms("叶质中毒")),
]


NORMALIZATION_RULES = [
    ("血液型脓病", "核型多角体病", "alias_of", "confirmed"),
    ("血液型脓", "核型多角体病", "short_name_of", "confirmed"),
    ("体腔型脓病", "核型多角体病", "alias_of", "confirmed"),
    ("体腔型脓", "核型多角体病", "short_name_of", "confirmed"),
    ("中肠型脓病", "质型多角体病", "alias_of", "confirmed"),
    ("中肠型脓", "质型多角体病", "short_name_of", "confirmed"),
    ("传染性软化病", "病毒性软化病", "alias_of", "confirmed"),
    ("卒倒病", "细菌性中毒病", "alias_of", "confirmed"),
    ("黑胸败血病", "细菌性败血病", "subtype_of", "confirmed"),
    ("青头败血病", "细菌性败血病", "subtype_of", "confirmed"),
    ("灵菌败血病", "细菌性败血病", "subtype_of", "confirmed"),
    ("绢白僵病", "白僵病", "alias_or_subtype_of", "confirmed"),
    ("镰刀霉病", "镰刀菌病", "alias_of", "confirmed"),
    ("酵菌病", "酵母菌病", "alias_of", "confirmed"),
    ("虱螨病", "蒲螨病", "alias_of", "confirmed"),
    ("壁虱病", "蒲螨病", "alias_of", "confirmed"),
    ("玫烟僵病", "赤僵病/灰僵病", "ambiguous_alias", "expert_review"),
    ("玫烟色僵病", "赤僵病/灰僵病", "ambiguous_alias", "expert_review"),
    ("蝇蛆病", "多化性蝇蛆病/蛹蛆病", "broader_term", "context_required"),
]

NORMALIZATION_NOTES = {
    "玫烟僵病": "Schema 指向赤僵病或灰僵病，禁止无上下文自动归一。",
    "玫烟色僵病": (
        "首批文献存在口径差异：《常见蚕病防治》将其标为灰僵病，"
        "《家蚕病理学》在赤僵病条目下记载玫烟色棒束孢，需专家裁定。"
    ),
    "蝇蛆病": "语义范围大于单一病种；上下文可能指多化性蝇蛆病，也可能泛指蛹蛆病。",
}


def build_seeds() -> list[Seed]:
    seeds: list[Seed] = []
    aliases_by_canonical: dict[str, list[str]] = defaultdict(list)
    related_by_canonical: dict[str, list[str]] = defaultdict(list)
    for surface, canonical, relation, status in NORMALIZATION_RULES:
        if status != "confirmed" or "/" in canonical:
            continue
        if relation in {"alias_of", "short_name_of", "alias_or_subtype_of"}:
            aliases_by_canonical[canonical].append(surface)
        elif relation == "subtype_of":
            related_by_canonical[canonical].append(surface)

    for subtype, names in DISEASE_GROUPS:
        for name in names:
            seeds.append(
                Seed(
                    name=name,
                    label="Disease",
                    subtype=subtype,
                    aliases=tuple(aliases_by_canonical[name]),
                    related_terms=tuple(related_by_canonical[name]),
                    note="Schema 核心病种；未命中文献时仍保留并标记为 schema_only。",
                    keep_if_missing=True,
                )
            )

    category_terms = terms(
        "传染性蚕病|非传染性蚕病|病毒病|细菌病|真菌病|原虫病|微孢子虫病|"
        "原生动物寄生病害|线虫寄生病害|节肢动物寄生病害|动物性寄生病害|"
        "中毒症|农药中毒|工业废气中毒|重金属中毒|叶质因素病害"
    )
    seeds.extend(Seed(name, "DiseaseCategory") for name in category_terms)

    cause_groups = {
        "病毒": terms(
            "家蚕核型多角体病毒|核型多角体病毒|BmNPV|NPV|家蚕质型多角体病毒|"
            "质型多角体病毒|BmCPV|CPV|家蚕传染性软化病病毒|传染性软化病病毒|"
            "BmIFV|IFV|家蚕浓核病毒|浓核病毒|BmDNV|DNV|家蚕隐潜病毒|隐潜病毒|"
            "病毒|杆状病毒|多角体病毒"
        ),
        "细菌": terms(
            "苏云金杆菌|蜡状芽孢杆菌|枯草杆菌|大肠杆菌|链球菌|葡萄球菌|"
            "沙雷氏菌|红色灵杆菌|灵菌|假单胞菌|变形杆菌|败血病菌|芽孢杆菌|"
            "细菌|芽孢"
        ),
        "真菌": terms(
            "白僵菌|球孢白僵菌|黄僵菌|绿僵菌|金龟子绿僵菌|曲霉菌|黄曲霉|"
            "黑曲霉|灰僵菌|黑僵菌|赤僵菌|草僵菌|镰刀菌|酵母菌|玫烟色棒束孢|"
            "玫烟色拟青霉|玫烟色拟青霉菌|玫烟色棒束菌|真菌|孢子|分生孢子|"
            "芽生孢子|气生菌丝|菌丝"
        ),
        "微孢子虫/原生动物/寄生虫": terms(
            "家蚕微粒子虫|微粒子虫|微孢子虫|具褶孢子虫|泰罗汉孢子虫|"
            "锥虫|变形虫|球虫|线虫|多化性蚕蛆蝇|蚕蛆蝇|蛹蛆蝇|蒲螨|蚕虱|"
            "原生动物|寄生虫|微粒子孢子|极丝"
        ),
        "农药类别": terms(
            "有机磷杀虫剂|有机氮农药|有机氯农药|氨基甲酸酯类杀虫剂|"
            "拟除虫菊酯类杀虫剂|苯甲酰苯脲类杀虫剂|氯化烟酰类杀虫剂|"
            "新烟碱类杀虫剂|大环内酯类杀虫剂|沙蚕毒素类杀虫剂|"
            "抗生素类杀虫剂|植物源类杀虫剂|鱼尼丁受体类杀虫剂|生物源杀虫剂|"
            "胃毒剂|触杀剂|熏蒸剂|内吸剂|神经毒剂|呼吸毒剂|生长发育调节剂"
        ),
        "具体农药": terms(
            "敌敌畏|久效磷|对硫磷|乐果|脱叶磷|敌百虫|苯硫磷|甲胺磷|"
            "乙酰甲胺磷|西维因|混灭威|灭多威|氯氰菊酯|溴氰菊酯|氟氯氰菊酯|"
            "氯氟氰菊酯|醚菊酯|除虫脲|氟啶脲|氟铃脲|氟虫脲|噻嗪酮|"
            "噻虫啉|吡虫啉|啶虫脒|噻虫嗪|阿维菌素|埃玛菌素|伊维菌素|"
            "甲维盐|多杀菌素|氟虫酰胺|氯虫酰胺|鱼藤酮|溴虫腈"
        ),
        "化学/污染因素": terms(
            "氟化物|二氧化硫|硫化氢|氯化物|碘化物|氮化物|煤气|重金属|"
            "镉|锌|铅|砷|铜|农药残留|有害气体|工业废气|煤烟"
        ),
        "生物与环境因素": terms(
            "病原体|病原微生物|病原物|病原孢子|多角体|病毒粒子|细菌芽孢|"
            "真菌孢子|叶质不良|有毒物质|机械创伤"
        ),
    }
    for subtype, names in cause_groups.items():
        seeds.extend(Seed(name, "Cause", subtype=subtype) for name in names)

    symptom_groups = {
        "取食/排泄异常": terms(
            "食欲减退|停止食桑|拒食|厌食|吐液|吐肠液|排软粪|下痢|空头蚕|"
            "蚕粪软化|蚕粪变色"
        ),
        "行为/发育异常": terms(
            "行动迟缓|爬行不止|狂躁|痉挛|麻痹|侧倒|卷曲|不眠蚕|迟眠蚕|"
            "起缩蚕|缩蚕|不蜕皮|蜕皮不良|发育不齐|龄期延长|早熟|早结茧"
        ),
        "体表/体色异常": terms(
            "体躯肿胀|环节肿胀|体节隆起|体壁易破|体色乳白|体色污暗|体色青白|"
            "体色发黑|胸部透明|头胸部膨大|黑胸|青头|斑点蚕|黑斑|锈色斑|"
            "油渍状病斑|皮肤病斑|腹足乳白|尾足黑褐色|黑色喇叭状病斑|蛆孔"
        ),
        "尸体/病征特征": terms(
            "脓汁流出|尸体软化|尸体硬化|尸体腐烂|尸体发臭|尸体干瘪|"
            "尸体潮湿|尸体僵硬|白色粉末|绿色分生孢子|黄色分生孢子|"
            "红色分生孢子|黑色分生孢子|体表长出菌丝"
        ),
        "生产性状异常": terms(
            "不结茧|畸形茧|薄皮茧|死笼茧|结茧率下降|茧质下降|产量下降|"
            "孵化率下降|死卵增多|不受精卵增多"
        ),
    }
    for subtype, names in symptom_groups.items():
        seeds.extend(Seed(name, "Symptom", subtype=subtype) for name in names)

    lesion_groups = {
        "细胞病变": terms(
            "血细胞坏死|细胞核膨大|细胞核肥大|核膜破裂|核崩解|细胞质空泡化|"
            "细胞变性|细胞坏死|多角体形成|病毒增殖|细胞溶解"
        ),
        "组织/器官病变": terms(
            "中肠细胞病变|中肠上皮细胞脱落|中肠组织崩解|中肠病变|脂肪体病变|"
            "丝腺病变|真皮细胞病变|围食膜损伤|组织液化|组织坏死|消化管空虚|"
            "中肠乳白|肠壁透明|体壁破裂"
        ),
        "体液/生理病变": terms(
            "血液乳白|血液混浊|体液混浊|败血症|神经系统功能紊乱|"
            "乙酰胆碱酯酶抑制|氧化磷酸化受阻|呼吸链阻断"
        ),
    }
    for subtype, names in lesion_groups.items():
        seeds.extend(Seed(name, "Lesion", subtype=subtype) for name in names)

    part_groups = {
        "体表/附肢": terms(
            "体表|体壁|表皮|上表皮|原表皮|真皮细胞|口器|气门|胸足|腹足|尾足|尾角"
        ),
        "消化/排泄系统": terms(
            "消化管|消化道|前肠|中肠|后肠|中肠上皮|中肠上皮细胞|肠壁|围食膜|"
            "消化液|肠液|马氏管"
        ),
        "循环/免疫系统": terms("血液|血淋巴|血细胞|血腔|血浆|脂肪体"),
        "呼吸/神经/运动系统": terms(
            "气管|微气管|气管系统|神经系统|中枢神经系统|肌肉|血脑屏障"
        ),
        "生殖/发育组织": terms("丝腺|生殖腺|卵巢|精巢|胚胎|蚕卵|母蛾"),
        "细胞结构": terms("细胞核|细胞质|细胞膜|核膜|内质网|线粒体|质膜"),
    }
    for subtype, names in part_groups.items():
        seeds.extend(Seed(name, "Part", subtype=subtype) for name in names)

    route_groups = {
        "传染途径": terms(
            "经口传染|食下传染|经皮传染|创伤传染|接触传染|经卵传染|胚种传染|"
            "水平传染|垂直传染|交叉感染|空气传播|气流传播|蚕座内传染"
        ),
        "侵入途径": terms("经口侵入|体壁侵入|创伤侵入|气门侵入|口器进入|消化管侵入"),
        "污染/媒介途径": terms(
            "桑叶污染|蚕沙传播|蚕粪传播|尸体传播|蚕具传播|蚕室传播|"
            "野外昆虫传播|水源污染|空气污染|废气污染"
        ),
        "毒物暴露途径": terms("食下农药|接触农药|农药飘移|污染桑叶食下|有害气体吸入"),
    }
    for subtype, names in route_groups.items():
        seeds.extend(Seed(name, "Route", subtype=subtype) for name in names)

    condition_groups = {
        "温湿度/环境": terms(
            "高温|低温|高湿|低湿|高温高湿|低温多湿|多湿环境|通风不良|闷热|"
            "温差过大|连续阴雨|夏秋高温|大蚕期高温高湿"
        ),
        "饲料/营养": terms(
            "叶质不良|桑叶萎凋|桑叶发酵|桑叶污染|食桑不足|营养不良|"
            "氟污染桑叶|农药污染桑叶"
        ),
        "卫生/饲养": terms(
            "消毒不彻底|蚕座潮湿|蚕座拥挤|饲养过密|密度过大|蚕座蒸热|"
            "病原污染|病原数量大|混批饲养"
        ),
        "宿主/诱因": terms(
            "蚕体虚弱|抗病力降低|易感品种|机械创伤|交叉感染|桑园治虫|"
            "野外害虫多|微量农药"
        ),
        "污染环境": terms("农药污染|氟污染|工业废气污染|煤烟污染|有害气体污染"),
    }
    for subtype, names in condition_groups.items():
        seeds.extend(Seed(name, "Condition", subtype=subtype) for name in names)

    stage_groups = {
        "发育阶段": terms(
            "蚕卵期|胚胎期|催青期|收蚁期|蚁蚕|稚蚕期|壮蚕期|小蚕期|大蚕期|"
            "眠期|起蚕期|蜕皮期|熟蚕期|上蔟期|结茧期|蛹期|蛾期|母蛾期"
        ),
        "龄期": terms("一龄|二龄|三龄|四龄|五龄|一龄期|二龄期|三龄期|四龄期|五龄期"),
        "季节蚕期": terms("春蚕期|夏蚕期|秋蚕期|夏秋蚕期|早秋蚕期|晚秋蚕期"),
        "病程阶段": terms("潜伏期|发病初期|发病盛期|发病后期|死亡后|急性期|慢性期"),
    }
    for subtype, names in stage_groups.items():
        seeds.extend(Seed(name, "Stage", subtype=subtype) for name in names)

    diagnosis_groups = {
        "现场/外观诊断": terms(
            "肉眼观察|外观诊断|病征诊断|病症观察|蚕体观察|蚕粪观察|"
            "发育观察|眠起观察|食桑观察|现场调查|流行病学调查"
        ),
        "显微/解剖检查": terms(
            "显微镜检查|显微观察|显微镜检|镜检|涂片检查|染色检查|解剖检查|"
            "血液检查|体液检查|中肠检查|母蛾镜检|微粒子孢子镜检"
        ),
        "病原/实验室检测": terms(
            "病原检测|病原分离|培养检查|实验室诊断|血清学诊断|荧光抗体法|"
            "酶联免疫吸附试验|ELISA|PCR检测|核酸检测|生物测定|鉴别诊断"
        ),
        "检验检疫": terms(
            "母蛾检验|母蛾检验检疫|蚕卵检验|成品卵检验|成品卵检验检疫|蚕种检疫"
        ),
        "中毒检测": terms(
            "乙酰胆碱酯酶活性检验法|桑叶农药检测|蚕体农药检测|"
            "桑叶含氟量检测|大气氟化物检测|中毒病征诊断"
        ),
    }
    for subtype, names in diagnosis_groups.items():
        seeds.extend(Seed(name, "Diagnosis", subtype=subtype) for name in names)

    measure_groups = {
        "消毒防病": terms(
            "蚕室消毒|蚕具消毒|蚕体消毒|蚕座消毒|环境消毒|桑叶消毒|蚕卵消毒|"
            "养蚕前消毒|蚕期消毒|回山消毒|预防消毒|终末消毒|补湿消毒|"
            "物理消毒|化学消毒|喷雾消毒|浸渍消毒|熏烟消毒|熏蒸消毒|"
            "撒粉消毒|蒸汽消毒|煮沸消毒|日光消毒|焚烧消毒|严格消毒|定期消毒"
        ),
        "隔离/无害化处理": terms(
            "隔离病蚕|淘汰病蚕|深埋病蚕|焚烧病蚕|病蚕处理|病尸处理|"
            "切断传染途径|阻断传染源|控制蔓延"
        ),
        "环境/饲养控制": terms(
            "换桑|止桑|给新鲜桑|除沙|扩座|稀放饲养|通风换气|降温排湿|"
            "控制温湿度|提青分批|分批提青|淘汰弱小蚕|小蚕共育|大、小蚕分养|"
            "良桑饱食|适熟叶|增强蚕体抵抗力|加强饲养管理"
        ),
        "检验检疫/综合治理": terms(
            "检验检疫|母蛾淘汰|母蛾检验|成品卵检验|蚕种检疫|桑园治虫|"
            "防除敌害|综合防治|农业综合防治|防病卫生制度"
        ),
    }
    for subtype, names in measure_groups.items():
        seeds.extend(Seed(name, "Measure", subtype=subtype) for name in names)

    auxiliary_groups = {
        "DomainConcept": {
            "核心对象": terms(
                "家蚕|蚕体|蚕儿|健蚕|病蚕|死蚕|僵蚕|蚕蛹|蚕蛾|幼虫|寄主|宿主"
            ),
            "疾病与病理": terms(
                "蚕病|疾病|病害|病原|病原性|致病性|致病因素|病因|病征|病症|症状|"
                "病变|病理变化|病程|发病|染病|致病|死亡|感染|侵染|寄生|增殖|发芽|"
                "僵病|脓病|败血病|软化病|中毒"
            ),
            "传播与流行": terms(
                "传染|传播|扩散|流行|暴发|传染源|传播媒介|传染途径|"
                "潜伏感染|隐性感染|显性感染|混合感染|继发感染|原发感染|感染力|毒力"
            ),
            "免疫与易感性": terms(
                "抗病力|抗病性|抗逆性|易感性|易感期|抵抗力|抵抗性|感染抵抗力|"
                "免疫|先天免疫|细胞免疫|体液免疫|防御机制"
            ),
            "生产领域": terms(
                "蚕业|蚕区|蚕桑生产|养蚕生产|蚕种生产|丝茧育|原蚕|病原库|"
                "消毒剂|消毒液|农药|杀虫剂|药剂|原药|主剂|辅剂|桑树"
            ),
        },
        "HusbandryOperation": {
            "养蚕流程": terms(
                "养蚕|饲育|饲养|催青|收蚁|给桑|除沙|扩座|分箔|提青|眠起处理|"
                "上蔟|上簇|采茧|制种|补催青|匀座|眠前除沙|起除|桑叶贮藏"
            )
        },
        "FacilityTool": {
            "场所": terms("蚕室|贮桑室|催青室|上蔟室|蚕种场|原蚕区|桑园|晒场"),
            "蚕具/设施": terms(
                "蚕具|蚕座|蚕匾|蚕架|蚕网|簇具|方格簇|塑料折蔟|尼龙薄膜|给桑架|"
                "喷雾器|温湿度计|显微镜|防毒面具"
            ),
        },
        "DisinfectantDrug": {
            "含氯消毒剂": terms(
                "漂白粉|漂粉精|消特灵|二氯异氰尿酸钠|优氯净|三氯异氰尿酸|"
                "强氯精|蚕用消毒净|亚迪蚕保|亚迪净|亚迪欣|二氧化氯|次氯酸|"
                "有效氯|含氯消毒剂"
            ),
            "甲醛类消毒剂": terms(
                "甲醛|福尔马林|多聚甲醛|固体甲醛|防病一号|毒消散|蚕座净|甲醛消毒剂"
            ),
            "石灰类消毒剂": terms(
                "石灰|生石灰|熟石灰|消石灰|石灰粉|新鲜石灰粉|石灰浆|石灰乳|防僵粉"
            ),
            "其他消毒/防病药剂": terms(
                "季铵盐类消毒剂|蚕季安Ⅰ号|蚕季安Ⅱ号|新洁尔灭|蚕康宁|百菌清|"
                "抗菌剂402|苯甲酸|水杨酸|盐酸|硫酸|灭蚕蝇|灭蚕蝇乳剂|灭蚕蝇片"
            ),
        },
        "MaterialFeed": {
            "桑叶/饲料": terms(
                "桑叶|新鲜桑叶|萎凋桑叶|污染桑叶|氟污染桑叶|农药污染桑叶|叶质|适熟叶"
            ),
            "排泄物/污染物": terms("蚕沙|蚕粪|病蚕尸体|病尸|病蛹|病蛾"),
            "蚕种/样本": terms("蚕种|蚕卵|种茧|母蛾|血液样本|中肠样本|桑叶样本"),
        },
        "MetricUnit": {
            "指标/参数": terms(
                "温度|相对湿度|有效氯浓度|药液浓度|用药量|作用时间|残效期|潜伏期|"
                "感染率|发病率|死亡率|结茧率|孵化率|含氟量|摄食量|体重|龄期|蚕期"
            ),
            "常用单位": terms("℃|mg/kg|mg/m³|g/m³|mL/m²|mg/L|μg/g|小时|分钟"),
        },
    }
    for label, groups in auxiliary_groups.items():
        for subtype, names in groups.items():
            seeds.extend(Seed(name, label, subtype=subtype) for name in names)

    # Stable de-duplication: a surface can be useful in several contexts, but each
    # canonical glossary term has one primary label. Schema labels take precedence.
    priority = list(SCHEMA_LABELS) + list(AUXILIARY_LABELS)
    priority_index = {label: index for index, label in enumerate(priority)}
    best: dict[str, Seed] = {}
    for seed in seeds:
        current = best.get(seed.name)
        if current is None or priority_index[seed.label] < priority_index[current.label]:
            best[seed.name] = seed
    return list(best.values())


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class Document:
    path: Path
    name: str
    text: str
    lines: list[str]
    heading_at_line: list[str]
    sha256: str


def load_document(path: Path) -> Document:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    stack: list[str] = []
    heading_at_line: list[str] = []
    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = re.sub(r"\s+", " ", match.group(2)).strip()
            stack = stack[: level - 1]
            stack.append(title)
        heading_at_line.append(" > ".join(stack))
    return Document(
        path=path,
        name=path.stem,
        text=text,
        lines=lines,
        heading_at_line=heading_at_line,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def non_overlapping_matches(text: str, surfaces: Iterable[str]) -> tuple[int, Counter[str]]:
    occupied: list[tuple[int, int]] = []
    counts: Counter[str] = Counter()
    for surface in sorted(set(surfaces), key=lambda item: (-len(item), item)):
        if not surface:
            continue
        for match in re.finditer(re.escape(surface), text, flags=re.IGNORECASE if surface.isascii() else 0):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            counts[surface] += 1
    return sum(counts.values()), counts


def evidence_for(doc: Document, surfaces: Iterable[str], limit: int = 3) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    ordered = sorted(set(surfaces), key=lambda item: (-len(item), item))
    for line_number, line in enumerate(doc.lines, start=1):
        matches = [surface for surface in ordered if surface.lower() in line.lower()]
        if not matches:
            continue
        surface = matches[0]
        excerpt = re.sub(r"\s+", " ", line).strip()
        if len(excerpt) > 180:
            position = excerpt.lower().find(surface.lower())
            start = max(0, position - 65)
            end = min(len(excerpt), position + len(surface) + 95)
            excerpt = ("…" if start else "") + excerpt[start:end] + ("…" if end < len(excerpt) else "")
        results.append(
            {
                "document": doc.name,
                "line": line_number,
                "heading_path": doc.heading_at_line[line_number - 1],
                "matched_surface": surface,
                "excerpt": excerpt,
            }
        )
        if len(results) >= limit:
            break
    return results


def assign_ids(records: list[dict[str, object]]) -> None:
    prefixes = {
        "Disease": "D",
        "DiseaseCategory": "DC",
        "Cause": "CA",
        "Symptom": "SY",
        "Lesion": "LE",
        "Part": "PT",
        "Route": "RT",
        "Condition": "CN",
        "Stage": "ST",
        "Diagnosis": "DG",
        "Measure": "MS",
        "HusbandryOperation": "HO",
        "FacilityTool": "FT",
        "DisinfectantDrug": "DD",
        "MaterialFeed": "MF",
        "MetricUnit": "MU",
        "DomainConcept": "TC",
    }
    counters: Counter[str] = Counter()
    for record in records:
        label = str(record["label"])
        counters[label] += 1
        width = 3
        record["id"] = f"{prefixes[label]}{counters[label]:0{width}d}"


def build_records(documents: list[Document]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    label_order = list(SCHEMA_LABELS) + list(AUXILIARY_LABELS)
    label_index = {label: index for index, label in enumerate(label_order)}
    disease_sequence = {
        name: sequence
        for sequence, name in enumerate(
            [name for _, names in DISEASE_GROUPS for name in names], start=1
        )
    }

    for seed in build_seeds():
        searchable_surfaces = [seed.name, *seed.aliases, *seed.related_terms]
        source_documents: list[str] = []
        mention_count = 0
        surface_mentions: Counter[str] = Counter()
        evidence: list[dict[str, object]] = []
        for doc in documents:
            count, counts = non_overlapping_matches(doc.text, searchable_surfaces)
            if count:
                source_documents.append(doc.name)
                mention_count += count
                surface_mentions.update(counts)
                evidence.extend(evidence_for(doc, searchable_surfaces, limit=2))
        if not mention_count and not seed.keep_if_missing:
            continue
        status = "corpus_verified" if mention_count else "schema_only"
        record: dict[str, object] = {
            "id": "",
            "name": seed.name,
            "label": seed.label,
            "label_zh": SCHEMA_LABELS.get(seed.label, AUXILIARY_LABELS.get(seed.label, seed.label)),
            "subtype": seed.subtype,
            "aliases": list(seed.aliases),
            "related_terms": list(seed.related_terms),
            "status": status,
            "mention_count": mention_count,
            "surface_mentions": dict(sorted(surface_mentions.items())),
            "source_documents": source_documents,
            "evidence": evidence[:6],
            "note": seed.note,
        }
        if seed.label == "Disease":
            record["schema_sequence"] = disease_sequence[seed.name]
        records.append(record)

    records.sort(
        key=lambda record: (
            label_index[str(record["label"])],
            disease_sequence.get(str(record["name"]), 10_000)
            if record["label"] == "Disease"
            else str(record["subtype"]),
            -int(record["mention_count"]),
            str(record["name"]),
        )
    )
    assign_ids(records)
    return records


def normalization_payload(documents: list[Document]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for surface, canonical, relation, review_status in NORMALIZATION_RULES:
        count = 0
        source_documents: list[str] = []
        evidence: list[dict[str, object]] = []
        for doc in documents:
            doc_count, _ = non_overlapping_matches(doc.text, [surface])
            if not doc_count:
                continue
            count += doc_count
            source_documents.append(doc.name)
            evidence.extend(evidence_for(doc, [surface], limit=1))
        payload.append(
            {
                "surface": surface,
                "canonical": canonical,
                "relation": relation,
                "review_status": review_status,
                "corpus_mention_count": count,
                "source_documents": source_documents,
                "evidence": evidence,
                "note": NORMALIZATION_NOTES.get(surface, ""),
            }
        )
    return payload


def build_payload(
    documents: list[Document], schema_path: Path, records: list[dict[str, object]]
) -> dict[str, object]:
    schema_raw = schema_path.read_bytes()
    by_label = Counter(str(record["label"]) for record in records)
    by_status = Counter(str(record["status"]) for record in records)
    normalization_rules = normalization_payload(documents)
    return {
        "glossary_name": "养蚕领域首批文献词表",
        "version": "1.0.0",
        "generated_on": date.today().isoformat(),
        "extraction_method": {
            "mode": "curated_seed_plus_exact_corpus_verification",
            "description": (
                "以疾病 Schema 和养蚕专业候选词为种子，对五份 Markdown 做不重叠精确命中、"
                "来源定位与标题路径回溯；非疾病候选词未命中即剔除。"
            ),
            "limitations": [
                "词频为字面命中统计，不代表实体关系抽取结果。",
                "schema_only 病种仅说明 Schema 预置，不能据此认定首批文献已有事实证据。",
                "玫烟僵病/玫烟色僵病等歧义名称禁止自动合并，须专家审核或结合上下文。",
                "短英文缩写可能存在普通文本误命中，KG 抽取时仍需上下文校验。",
            ],
        },
        "schema": {
            "name": schema_path.stem,
            "path": str(schema_path),
            "sha256": hashlib.sha256(schema_raw).hexdigest(),
            "labels": [
                {"label": label, "name_zh": name} for label, name in SCHEMA_LABELS.items()
            ],
        },
        "source_documents": [
            {
                "name": doc.name,
                "path": str(doc.path),
                "sha256": doc.sha256,
                "bytes": doc.path.stat().st_size,
                "line_count": len(doc.lines),
            }
            for doc in documents
        ],
        "statistics": {
            "term_count": len(records),
            "schema_term_count": sum(by_label[label] for label in SCHEMA_LABELS),
            "auxiliary_term_count": sum(by_label[label] for label in AUXILIARY_LABELS),
            "corpus_verified_count": by_status["corpus_verified"],
            "schema_only_count": by_status["schema_only"],
            "by_label": dict(by_label),
        },
        "quality_review_queue": {
            "schema_only_terms": [
                {"id": record["id"], "name": record["name"], "reason": "首批文献未命中"}
                for record in records
                if record["status"] == "schema_only"
            ],
            "normalization_rules": [
                rule for rule in normalization_rules if rule["review_status"] != "confirmed"
            ],
        },
        "normalization_rules": normalization_rules,
        "terms": records,
    }


def md_escape(value: object) -> str:
    text = str(value or "—").replace("|", "\\|").replace("\n", " ")
    return text


def render_markdown(payload: dict[str, object]) -> str:
    stats = payload["statistics"]
    documents = payload["source_documents"]
    records = payload["terms"]
    rules = payload["normalization_rules"]
    lines = [
        "# 养蚕领域首批文献词表",
        "",
        f"> 版本：{payload['version']}；生成日期：{payload['generated_on']}。",
        "> 本文件是 RAG 分词/检索与 KG 实体归一的首版种子词表，不是已完成的知识图谱。",
        "",
        "## 一、提取口径",
        "",
        "- 以《家蚕疾病知识图谱 Schema 完整版》的 52 个核心病种与 11 类节点为主骨架。",
        "- 对五份真实 Markdown 文献做字面命中、来源文档、首处行号和标题路径回溯。",
        "- 非疾病候选词只有命中文献才进入词表；Schema 核心病种即使未命中也保留为 `schema_only`。",
        "- 同义词、旧称和亚型使用显式归一规则；歧义名称不自动并入具体病种。",
        "- 额外保留饲养操作、蚕具、药剂、物料和参数单位，供 Jieba/BM25 和后续 QA 检索使用。",
        "",
        "## 二、统计摘要",
        "",
        f"- 词条总数：**{stats['term_count']}**",
        f"- Schema 节点类词条：**{stats['schema_term_count']}**",
        f"- 检索辅助词条：**{stats['auxiliary_term_count']}**",
        f"- 五份文献已命中：**{stats['corpus_verified_count']}**",
        f"- 仅 Schema 预置：**{stats['schema_only_count']}**",
        "",
        "### 来源文献",
        "",
        "| 文献 | 行数 | 字节数 | SHA-256 |",
        "|---|---:|---:|---|",
    ]
    for doc in documents:
        lines.append(
            f"| {md_escape(doc['name'])} | {doc['line_count']} | {doc['bytes']} | `{doc['sha256']}` |"
        )

    lines.extend(
        [
            "",
            "## 三、别名与归一规则",
            "",
            "| 表面词 | 归一目标 | 关系 | 审核状态 | 语料命中 | 说明 |",
            "|---|---|---|---|---:|---|",
        ]
    )
    for rule in rules:
        lines.append(
            "| {surface} | {canonical} | `{relation}` | `{status}` | {count} | {note} |".format(
                surface=md_escape(rule["surface"]),
                canonical=md_escape(rule["canonical"]),
                relation=rule["relation"],
                status=rule["review_status"],
                count=rule["corpus_mention_count"],
                note=md_escape(rule["note"]),
            )
        )

    label_names = {**SCHEMA_LABELS, **AUXILIARY_LABELS}
    for index, (label, label_zh) in enumerate(label_names.items(), start=1):
        group = [record for record in records if record["label"] == label]
        if not group:
            continue
        lines.extend(
            [
                "",
                f"## {index + 3}、{label_zh}（`{label}`）",
                "",
                "| ID | 标准词 | 子类 | 别名/相关词 | 状态 | 命中 | 来源 |",
                "|---|---|---|---|---|---:|---|",
            ]
        )
        for record in group:
            aliases = [*record["aliases"], *record["related_terms"]]
            alias_text = "、".join(aliases) if aliases else "—"
            sources = "、".join(record["source_documents"]) if record["source_documents"] else "—"
            lines.append(
                "| {id} | {name} | {subtype} | {aliases} | `{status}` | {count} | {sources} |".format(
                    id=record["id"],
                    name=md_escape(record["name"]),
                    subtype=md_escape(record["subtype"]),
                    aliases=md_escape(alias_text),
                    status=record["status"],
                    count=record["mention_count"],
                    sources=md_escape(sources),
                )
            )

    lines.extend(
        [
            "",
            "## 使用约束",
            "",
            "1. `corpus_verified` 只表示词面在至少一份文献出现；事实、关系和因果仍须由 KG 抽取与证据审核确认。",
            "2. `schema_only` 不得作为文献证据使用，可作为后续增量文献的召回词。",
            "3. `expert_review` 与 `context_required` 的归一规则不得在入图前自动执行。",
            "4. JSON 内每个词条保留 `evidence`（文献、行号、标题路径、命中词面和短摘录），用于人工复核。",
            "5. Jieba 用户词典同时包含标准词、确认别名和歧义检索词；是否归一应由 JSON 规则决定，而不是由分词词典决定。",
            "",
        ]
    )
    return "\n".join(lines)


def jieba_tag(label: str) -> str:
    return {
        "Disease": "nz",
        "DiseaseCategory": "nz",
        "Cause": "nz",
        "Symptom": "n",
        "Lesion": "n",
        "Part": "n",
        "Route": "n",
        "Condition": "n",
        "Stage": "t",
        "Diagnosis": "n",
        "Measure": "vn",
        "HusbandryOperation": "vn",
        "FacilityTool": "n",
        "DisinfectantDrug": "nz",
        "MaterialFeed": "n",
        "MetricUnit": "n",
        "DomainConcept": "n",
    }[label]


def render_jieba(records: list[dict[str, object]], rules: list[dict[str, object]]) -> str:
    entries: dict[str, tuple[int, str]] = {}
    for record in records:
        label = str(record["label"])
        base = 100_000 if label == "Disease" else 60_000 if label in SCHEMA_LABELS else 35_000
        frequency = base + min(int(record["mention_count"]), 999) * 20
        tag = jieba_tag(label)
        for surface in [str(record["name"]), *map(str, record["aliases"]), *map(str, record["related_terms"])]:
            if len(surface.strip()) < 2 or surface.isascii():
                continue
            current = entries.get(surface)
            if current is None or frequency > current[0]:
                entries[surface] = (frequency, tag)
    for rule in rules:
        surface = str(rule["surface"])
        if len(surface) >= 2 and not surface.isascii():
            entries.setdefault(surface, (80_000, "nz"))
    return "\n".join(
        f"{surface} {frequency} {tag}"
        for surface, (frequency, tag) in sorted(entries.items(), key=lambda item: (-len(item[0]), item[0]))
    ) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--documents", required=True, type=Path, nargs="+")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    missing = [path for path in [args.schema, *args.documents] if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing input files: " + ", ".join(map(str, missing)))

    documents = [load_document(path.resolve()) for path in args.documents]
    records = build_records(documents)
    payload = build_payload(documents, args.schema.resolve(), records)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    json_path = args.output_dir / "silkworm_domain_glossary.json"
    markdown_path = args.output_dir / "silkworm_domain_glossary.md"
    jieba_path = args.output_dir / "jieba_silkworm_userdict.txt"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    jieba_path.write_text(
        render_jieba(payload["terms"], payload["normalization_rules"]), encoding="utf-8"
    )

    print(json.dumps({
        "outputs": [str(json_path), str(markdown_path), str(jieba_path)],
        "statistics": payload["statistics"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
