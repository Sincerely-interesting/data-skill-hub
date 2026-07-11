# 标注标准规范 (Labeling Criteria)

> 本文档定义电商素材标注的完整标准体系,包括标签定义、判定规则、边界案例处理和质量评估方法。

## 标签体系总览

### 8大业务标签

| 标签ID | 中文名称 | 英文名称 | 优先级 | 典型占比 |
|--------|----------|----------|--------|----------|
| `celebrity_empty` | 明星空镜 | Celebrity Empty Shot | P0 | 2-5% |
| `draft_core` | 空镜草稿(核心款) | Draft - Core Product | P0 | 25-35% |
| `draft_regular` | 空镜草稿(常规款) | Draft - Regular Product | P1 | 5-10% |
| `single_display` | 单品展示(上脚) | Single Display (On-foot) | P0 | 10-20% |
| `creative_still` | 创意静物 | Creative Still Life | P1 | 3-8% |
| `still_display` | 静物展示 | Standard Still Display | P1 | 5-15% |
| `performance_test` | 性能测试 | Performance Test | P2 | 1-3% |
| `other` | 其他 | Other / Uncategorized | P3 | <20% |

**质量阈值**:
- ⚠️ "其他"标签占比 > 20% → 需要审查标签体系完整性
- ✅ 各标签分布相对均衡,无明显倾斜
- 🔍 定期(每周)抽检各标签准确率,目标 > 90%

---

## 详细标签定义

### 1. 明星空镜 (Celebrity Empty Shot)

**定义**: 
画面中包含**知名人物**(明星、KOL、代言人),且背景简洁,无产品或产品非主体焦点。

**核心特征**:
- ✅ 人物是画面的**绝对主体**(占比>60%)
- ✅ 背景**干净简约**(纯色/虚化/简单纹理)
- ❌ 产品**不是视觉焦点**(即使存在也是点缀)
- ✅ 人物姿态自然,**非产品展示姿势**

**典型场景**:
- 明星代言宣传照
- KOL社交媒体头像
- 代言人特写/肖像
- 明星街拍(背景简洁时)
- 品牌活动明星亮相

**示例描述**:
```
✅ 正例:
- "某明星正面特写,黑色T恤,白色纯色背景,目光看镜头"
- "代言人侧脸轮廓照,灰色渐变背景,光线柔和"

❌ 反例:
- "明星手持运动鞋展示" → 应为 single_display
- "明星穿着羽绒服在雪地行走" → 可能是 creative_still 或 other
```

**判定优先级**:
1. **人物存在且可识别为知名人士** (必须)
2. **背景简洁** (必须)
3. **产品非主体** (必须)

---

### 2. 空镜草稿(核心款) (Draft - Core Product)

**定义**: 
**主推产品**的空镜拍摄图,背景通常为纯色或简约场景,**产品清晰居中**,用于展示产品本身的设计和细节。

**核心特征**:
- ✅ **产品是唯一主体**(100%聚焦)
- ✅ 背景为**纯色/渐变/极简场景**
- ✅ 产品**居中或黄金分割位置**
- ✅ 属于**当前季度/季节的核心主推款**
- ✅ 拍摄角度标准(正视图/45度/俯视图)

**典型场景**:
- 新品首发官方图
- 主推款产品白底图
- 核心SKU的标准照
- 电商详情页主图
- 广告投放素材原图

**如何识别"核心款"**:
- 通常在文件名中标记: `core`, `main`, `hero`, `key`
- 位于Excel/素材列表的前部
- 高分辨率(>2000px)
- 多角度拍摄(3张以上同产品不同角度)

**示例描述**:
```
✅ 正例:
- "白色运动鞋,45度角拍摄,纯白背景,阴影柔和,产品占画面70%"
- "黑色羽绒服正面平铺,浅灰背景,拉链细节清晰可见"

❌ 反例:
- "运动鞋穿在模特脚上" → single_display
- "产品放在复杂场景中(如桌面杂物)" → still_display 或 creative_still
- "非主推款的旧产品" → draft_regular 或 other
```

**判定优先级**:
1. **产品为主体且背景极简** (必须)
2. **属于核心主推款** (必须,需结合业务上下文判断)
3. **拍摄专业度高** (辅助判断)

---

### 3. 空镜草稿(常规款) (Draft - Regular Product)

**定义**: 
**非核心款**产品的空镜拍摄图,特征与核心款类似,但属于**常规补充款、基础款或过季款**。

**与核心款的区别**:
| 维度 | 核心款 | 常规款 |
|------|--------|--------|
| **推广力度** | 强(广告+首页) | 弱(分类页) |
| **拍摄质量** | 极高(多角度) | 中等(1-2角度) |
| **更新频率** | 季度新品 | 常年在线 |
| **分辨率** | >2000px | 1000-2000px |
| **数量占比** | 20-30% | 40-50% |

**典型场景**:
- 基础款产品图(T恤、基础色系)
- 常年销售的经典款
- 补充性的颜色/尺码变体
- 过季但仍在线销售的产品

**示例描述**:
```
✅ 正例:
- "基础款白色T恤平铺图,浅灰背景,单角度"
- "经典牛仔裤正面照,中灰背景,常规光效"

❌ 反例:
- "当季新款限量版" → draft_core
- "产品有模特展示" → single_display
```

**判定难点**:
- 需要业务知识区分核心款vs常规款
- **建议**: 如果无法确定,默认归类为 `draft_regular`(保守策略)

---

### 4. 单品展示(上脚) (Single Display - On-foot)

**定义**: 
**单一商品**被**穿戴/使用**在实际场景中的展示图,重点展示商品的**上身效果、搭配效果或使用状态**。

**核心特征**:
- ✅ **仅展示一件主要商品**(非整套搭配)
- ✅ 商品被**实际穿戴/使用**(鞋子穿脚、衣服上身、包袋肩背)
- ✅ 展示**真实比例和效果**(非摆拍)
- ✅ 背景可以是**实景/影棚模拟场景**

**典型场景**:
- 运动鞋上脚图(跑步/走路姿态)
- 服装穿搭效果图(半身/全身)
- 配饰佩戴图(手表/眼镜/帽子)
- 户外装备使用演示

**与"创意静物"的区别**:
| 特征 | 单品展示 | 创意静物 |
|------|----------|----------|
| **是否有人** | 有(至少局部) | 无 |
| **展示目的** | 上身效果/功能性 | 艺术美感/氛围 |
| **产品状态** | 使用中 | 静止摆放 |
| **背景复杂度** | 中等(场景化) | 高(艺术化) |

**示例描述**:
```
✅ 正例:
- "模特腿部穿着跑鞋,在跑道上跑步姿态,动态模糊背景"
- "女性上半身穿羽绒服,双手插兜,城市街景背景"

❌ 反例:
- "鞋子和衣服全套搭配" → 可能是 other(多品类)
- "产品静止在桌面上" → still_display
- "只有产品没有人" → draft_core/regular
```

**特殊子类型**:

#### 4.1 局部特写(Local Close-up)
- 仅展示身体局部(手/脚/脸)
- 重点展示产品细节(如手表佩戴、戒指佩戴)
- **仍归为此类**

#### 4.2 动作演示(Action Shot)
- 展示产品在使用过程中的动作
- 如: 跑步跳跃(鞋)、挥拍(球拍)、打字(键盘)
- **归为此类**

---

### 5. 创意静物 (Creative Still Life)

**定义**: 
产品以**艺术化的方式摆放**,配合精心设计的**光影、构图、道具和背景**,营造特定的**氛围感或故事性**,超越单纯的产品展示。

**核心特征**:
- ✅ **无人出现**(或人仅为极次要背景元素)
- ✅ **构图讲究**(遵循摄影美学原则)
- ✅ **氛围感强**(通过光影/色彩/道具传达情绪)
- ✅ **可能包含抽象/超现实元素**
- ✅ 用于**品牌形象传播**而非直接转化

**典型场景**:
- 节日主题拍摄(圣诞/双十一)
- 艺术概念片(超现实主义)
- 材质对比实验(金属/织物/液体)
- 微距摄影(细节艺术化)
- 光影艺术(长曝光/剪影)

**示例描述**:
```
✅ 正例:
- "运动鞋放置在冰块上,周围有水花飞溅,蓝色冷调光线"
- "香水瓶与干花组合,暖黄色逆光,复古胶片质感"
- "手表悬浮在空中,背景是星轨长曝光照片"

❌ 反例:
- "产品白底图,无任何装饰" → still_display
- "产品简单放在桌面上" → still_display
- "有人使用产品" → single_display
```

**创意程度分级**:

| 级别 | 描述 | 判定依据 |
|------|------|----------|
| **轻度创意** | 简单道具+基本布光 | 1-2个道具,标准三点布光 |
| **中度创意** | 复杂构图+特殊光影 | 多层布光,非常规角度 |
| **高度创意** | 概念性/超现实 | 数字合成,抽象表达 |

**所有级别均归为此类**,无需细分。

---

### 6. 静物展示 (Standard Still Display)

**定义**: 
产品以**标准、直观的方式**静止展示,背景相对简单,主要用于**清晰呈现产品全貌和细节**,偏向**功能性和信息性**。

**核心特征**:
- ✅ **无人出现**
- ✅ **摆放方式标准化**(平铺/悬挂/立式)
- ✅ **背景简洁但不要求纯色**(可以是木纹/水泥/简单场景)
- ✅ **目的是让用户看清产品**(非艺术表达)
- ✅ **构图相对传统**(中心对称/三分法)**

**典型场景**:
- 电商详情页辅图(尺寸/材质说明)
- 产品细节图(拉链/缝线/Logo)
- 组合展示(套装配件一览)
- 包装盒/吊牌展示
- 多颜色/尺码对比图

**与"空镜草稿"的区别**:
| 特征 | 空镜草稿 | 静物展示 |
|------|----------|----------|
| **背景** | 纯色/极简 | 允许简单纹理(木/石/布) |
| **拍摄角度** | 标准(正/侧/俯) | 可更多样(鸟瞰/微距) |
| **附加元素** | 几乎无 | 允许少量道具(标尺/参照物) |
| **用途** | 主图/广告 | 详情页/说明书 |

**示例描述**:
```
✅ 正例:
- "运动鞋三视图(左/右/顶),浅木纹桌面,旁边放卷尺"
- "羽绒服内部绒毛细节特写,黑色背景,针缝清晰"
- "全部配色一字排开,白色背景,每双下方标注色号"

❌ 反例:
- "纯白背景的产品图" → draft_core/regular
- "艺术化光影布置" → creative_still
- "有人穿戴" → single_display
```

---

### 7. 性能测试 (Performance Test)

**定义**: 
展示产品**功能性测试过程或结果**的画面,通常出现在**实验室环境或受控测试场景**,强调产品的**技术参数和性能表现**。

**核心特征**:
- ✅ **明显的测试行为/设备**(如仪器/测量工具)
- ✅ **数据可视化**(图表/数字/对比)
- ✅ **极端条件展示**(防水/耐磨/抗摔测试)
- ✅ **科学/技术风格**的视觉语言
- ✅ 通常配有**文字说明**(测试项目/结果数值)

**典型场景**:
- 防水测试(喷淋/浸泡)
- 耐磨测试(机器摩擦)
- 抗压测试(重物压迫)
- 透气性测试(蒸汽透过)
- 温控测试(热成像仪显示)

**示例描述**:
```
✅ 正例:
- "运动鞋在耐磨测试机上,计数器显示50000次,鞋底磨损情况特写"
- "羽绒服在低温舱内,-30°C显示,旁边有温度计读数"
- "面料防水测试,水珠滚落慢动作截图"

❌ 反例:
- "普通产品展示" → still_display/draft
- "运动员使用产品比赛" → single_display 或 other
- "实验室环境但没有明确测试行为" → still_display
```

**注意**: 此类素材占比较少(1-3%),如果不确定,宁可归为`other`并添加备注。

---

### 8. 其他 (Other / Uncategorized)

**定义**: 
**无法归入上述7个类别**的素材,包括:
- 边界案例(模糊不清)
- 新出现的素材类型(标签体系尚未覆盖)
- 低质量/损坏的素材
- 复合型素材(同时符合多个类别特征)

**何时使用此标签**:

✅ **合理使用场景**:
- 素材内容确实特殊,现有标签无法覆盖
- 图片模糊/损坏,无法准确判断
- 多种产品混杂,无法识别主体
- 包含大量文字/图形,非产品展示

❌ **避免滥用**:
- 因为"懒得仔细判断"而归为此类
- 对新标签体系不熟悉时的默认选择
- 占比超过20%(说明标签体系需要更新)

**处理流程**:

当AI模型将素材标记为"other"时:

```python
def handle_other_label(material_id, result):
    """处理'其他'标签的特殊逻辑"""
    
    if result["label"] == "other":
        # 1. 记录到待审核队列
        review_queue.enqueue({
            "material_id": material_id,
            "ai_confidence": result["confidence"],
            "reason": result.get("description", ""),
            "priority": "high" if result["confidence"] < 0.5 else "medium",
        })
        
        # 2. 触发人工审核任务(如果集成主动学习系统)
        if active_learning_enabled:
            active_learning.request_human_review(material_id)
        
        # 3. 统计监控
        metrics.increment("other_label_count")
        
        logger.warning(
            f'Material {material_id} labeled as "other" '
            f'(confidence: {result["confidence"]:.2f})'
        )
    
    return result
```

**定期审查机制**:

建议**每周**执行一次"其他"标签审查:

```bash
# 生成"其他"标签报告
python run_pipeline.py analyze-other-labels \
  --cache-file labeling_cache.json \
  --output other_labels_report.md \
  --threshold 0.20  # 占比超过20%则告警
```

**报告内容应包括**:
1. 本周新增"其他"标签数量及占比
2. 抽样的"其他"标签素材列表(附图片缩略图)
3. 是否发现新的潜在类别
4. 标签体系优化建议

---

## 边界案例处理指南

### 案例1: 明星 + 产品共存

**场景**: 明星手持或穿着产品,但产品不是绝对主体。

**判定规则**:
- **产品占比<30%** → `celebrity_empty`(明星仍是主体)
- **产品占比30-60%** → `single_display`(视为上脚/上身展示)
- **产品占比>60%** → `single_display` 或 `other`(取决于是否有其他特征)

**示例**:
```
"明星手持运动鞋,面部占画面50%,鞋子占30%,背景简洁"
→ celebrity_empty (明星主体,产品点缀)

"明星脚穿运动鞋特写,腿部占60%,鞋子占35%,正在跑步"
→ single_display (产品使用展示,动作导向)
```

---

### 案例2: 多产品共存

**场景**: 同一画面中出现多个不同的产品。

**判定规则**:
- **同一品类多件**(如3双不同颜色的鞋) → 归为对应的最相关类(通常是`still_display`)
- **不同品类混搭**(如鞋+衣+包) → `other`(复合型,需人工拆分)
- **系列产品组合**(如全套护肤品的套装图) → `still_display`

**示例**:
```
"桌面上整齐排列5双不同配色的同款运动鞋"
→ still_display (多色展示)

"模特身穿外套+裤子+鞋子+戴帽子+背包,全套搭配"
→ other (多品类复合,超出单品范围)
```

---

### 案例3: 人 + 产品但非"使用"状态

**场景**: 人在画面中,但并未真正"使用"产品。

**判定规则**:
- **人与产品有明显互动**(触摸/注视/指向) → `single_display`(广义的使用意图)
- **人仅作为背景/比例参考** → 归为产品对应的类(`draft_core`等)
- **人与产品无任何关系**(恰好同框) → `other`(特殊情况)

**示例**:
```
"运动鞋放在前景,背景中有模糊的人影走动"
→ draft_core (人是无关背景)

"手即将触碰鞋面,悬停在上方2cm处"
→ single_display (互动意图明显)

"产品在桌上,远处窗户反射出摄影师影子"
→ still_display (忽略无关倒影)
```

---

### 案例4: 创意 vs 静态的模糊地带

**场景**: 介于艺术化和功能性之间的素材。

**判定规则**:
- **有明确的信息传递目的**(展示细节/尺寸/材质) → `still_display`
- **纯粹的美学表达**(引发情感共鸣) → `creative_still`
- **两者兼有** → 选择**主导目的**更强的那个

**决策树**:
```
这图片的主要用途是什么?
├─ 让用户看清产品细节/参数? → still_display
├─ 品牌形象/情感营销? → creative_still
└─ 不确定? → 检查以下指标:
   - 是否有文字说明/数据图表? → still_display (+1分)
   - 是否使用非常规光影/色调? → creative_still (+1分)
   - 是否有象征性道具(非产品本身)? → creative_still (+1分)
   - 构图是否打破常规(倾斜/裁切)? → creative_still (+1分)
   
   得分更高者胜出
```

---

## 质量保证机制

### AI标注质量评估

#### 1. 自动化指标

**置信度分析**:
```python
def evaluate_confidence_distribution(cache_file):
    """分析置信度分布"""
    cache = CacheManager(cache_file)
    confidences = [r["confidence"] for r in cache.cache.values()]
    
    stats = {
        "mean": np.mean(confidences),
        "median": np.median(confidences),
        "std": np.std(confidences),
        "high_confidence_ratio": sum(1 for c in confidences if c >= 0.8) / len(confidences),
        "low_confidence_ratio": sum(1 for c in confidences if c < 0.4) / len(confidences),
    }
    
    # 健康基准
    assert stats["mean"] >= 0.7, f"平均置信度过低: {stats['mean']}"
    assert stats["low_confidence_ratio"] <= 0.1, f"低置信度占比过高: {stats['low_confidence_ratio']}"
    
    return stats
```

**标签一致性检查**:
- 相似素材(同一产品不同角度)应具有相同或相近标签
- 时间序列素材(视频帧)的标签应保持稳定

#### 2. 人工抽检流程

**抽样策略**:
- **随机抽样**: 每周抽取5%的标注结果
- **分层抽样**: 确保每个标签都有样本被抽检
- **高风险抽样**: 重点抽查"其他"标签和低置信度(<0.5)样本

**审核标准**:
```python
REVIEW_CRITERIA = {
    "accuracy": {  # 准确性
        "exact_match": 3,      # 完全一致
        "acceptable": 2,       # 可接受(相邻/相似类别)
        "wrong": 0,            # 错误
    },
    "confidence_calibration": {  # 置信度校准
        "well_calibrated": 2,   # 置信度与准确性匹配
        "overconfident": 1,     # 过于自信(实际错误但置信度高)
        "underconfident": 1,    # 过于保守(实际正确但置信度低)
    },
}

# 目标: 平均得分 ≥ 2.5 / 3.0
```

**反馈闭环**:
```python
def incorporate_review_results(review_results):
    """将审核结果反馈给系统"""
    
    for item in review_results:
        if item["reviewer_label"] != item["ai_label"]:
            # 记录错误案例
            error_db.insert({
                "material_id": item["material_id"],
                "ai_prediction": item["ai_label"],
                "human_correction": item["reviewer_label"],
                "confidence": item["ai_confidence"],
                "reason": item.get("reason", ""),
                "reviewer": item["reviewer"],
                "timestamp": datetime.now(),
            })
            
            # 更新缓存
            cache.update(item["material_id"], {
                "label": item["reviewer_label"],
                "corrected_by_human": True,
                "original_ai_label": item["ai_label"],
            })
    
    # 分析错误模式
    error_patterns = analyze_errors(error_db)
    
    if error_patterns["should_update_prompt"]:
        optimize_prompt(error_patterns["suggestions"])
```

---

### 标签体系迭代流程

#### 触发条件

满足以下任一条件时应考虑更新标签体系:
1. **"其他"标签占比连续2周>25%**
2. **人工审核准确率<85%**
3. **业务方提出新的素材类型需求**
4. **错误案例分析发现系统性偏差**

#### 更新流程

```mermaid
graph TD
    A[触发标签体系评审] --> B{数据收集}
    B --> C[统计分析]
    C --> D{是否需要变更?}
    
    D -->|否| E[维持现状,加强培训]
    D -->|是| F[设计新标签/修改旧标签]
    
    F --> G[起草判定规则]
    G --> H[小规模测试(100样本)]
    H --> I{测试结果满意?}
    
    I -->|否| J[调整规则]
    J --> H
    
    I -->|是| K[全员培训]
    K --> L[正式发布新版本]
    L --> M[监控系统指标]
    M --> N{稳定运行2周?}
    
    N -->|否| A
    N -->|是| O[完成迭代]
```

#### 版本管理

```yaml
# labeling_criteria_version.yaml

current_version: "v2.3"
last_updated: "2026-07-11"
changelog:
  - version: "v2.3"
    date: "2026-07-11"
    changes:
      - type: "modification"
        label: "creative_still"
        description: "放宽对背景复杂度的要求,允许中等复杂度的场景"
        reason: "实际业务中发现很多营销素材被误判为still_display"
      
      - type: "clarification"
        label: "single_display"
        description: "明确'局部特写'(如手部佩戴手表)也归为此类"
        reason: "边缘case争议较多,统一标准"
    
  - version: "v2.2"
    date: "2026-06-15"
    changes:
      - type: "addition"
        label: "N/A"
        description: "暂无新增标签"
        reason: "维护性更新,修复文档错误"
```

---

## 常见误区与纠正

### ❌ 误区1: "只要有人就是single_display"

**纠正**:
- 关键看**人的角色**:
  - 人作为**使用者** → single_display
  - 人作为**背景/装饰** → 其他类(按产品特征判断)
  - 人作为**绝对主体** → celebrity_empty

**反例**:
- "远处的行人剪影,前景是产品静物" → 不是single_display,而是still_display

---

### ❌ 误区2: "背景复杂就是creative_still"

**纠正**:
- 复杂背景 + **无艺术意图** = still_display(可能是实景拍摄)
- 复杂背景 + **明显艺术设计** = creative_still

**判断线索**:
- 是否使用了**非常规光影**(如霓虹灯/多重曝光)?
- 是否有**超现实元素**(悬浮/变形/拼贴)?
- 整体氛围是否**刻意营造某种情绪**?

---

### ❌ 误区3: "测试图一定是performance_test"

**纠正**:
- 必须有**明确的测试行为或数据**
- 仅有"看起来像实验室"的环境不够
- 需要看到**仪器/测量工具/对比图表**

**反例**:
- "产品放在看似实验室的台面上,但没有进行任何操作" → still_display

---

### ❌ 误区4: "其他标签是无能的表现"

**纠正**:
- **合理使用"其他"是负责任的做法**
- 强行归入不合适的类别会污染数据
- 关键是要**定期审查"其他"样本**,推动标签体系进化

**最佳实践**:
- 设置"其他"占比**硬阈值**(如20%)
- 超过阈值**自动触发审查流程**
- 将审查结果**反馈给标签体系优化**

---

## 工具与资源

### 标注辅助工具

1. **快速参考卡片** (Quick Reference Card):
   - 打印成A4卡片,供标注员随时查阅
   - 包含每个标签的关键特征和正/反例

2. **交互式判定树** (Interactive Decision Tree):
   - Web应用形式,通过点击选择逐步引导至最终标签
   - 集成到审核界面(review_app)

3. **批量预标注** (Pre-labeling with AI):
   - 先用AI批量初筛
   - 人工只需审核**低置信度**和**"其他"标签**样本
   - 提升效率3-5倍

### 培训材料

1. **新人入职培训PPT** (`training-slides.pptx`):
   - 标签体系概述
   - 大量正/反例图片对比
   - 常见误区讲解
   - 实操练习(50个测试样本)

2. **定期复训测验** (Monthly Quiz):
   - 每月20道选择题,测试标签判断能力
   - 成绩低于80%需重新培训
   - 记录个人准确率趋势

3. **案例库** (Case Library):
   - 收集历史争议案例及最终裁定
   - 按**标签**和**难度等级**分类
   - 支持搜索和筛选

---

## 附录

### A. 完整标签ID映射表

```json
{
  "celebrity_empty": {
    "name_zh": "明星空镜",
    "name_en": "Celebrity Empty Shot",
    "priority": "P0",
    "parent_category": "people_focused",
    "typical_percentage_range": [2, 5],
    "quality_threshold": ">90%"
  },
  "draft_core": {
    "name_zh": "空镜草稿(核心款)",
    "name_en": "Draft - Core Product",
    "priority": "P0",
    "parent_category": "product_focused",
    "typical_percentage_range": [25, 35],
    "quality_threshold": ">95%"
  },
  "draft_regular": {
    "name_zh": "空镜草稿(常规款)",
    "name_en": "Draft - Regular Product",
    "priority": "P1",
    "parent_category": "product_focused",
    "typical_percentage_range": [5, 10],
    "quality_threshold": ">90%"
  },
  "single_display": {
    "name_zh": "单品展示(上脚)",
    "name_en": "Single Display (On-foot)",
    "priority": "P0",
    "parent_category": "usage_demo",
    "typical_percentage_range": [10, 20],
    "quality_threshold": ">92%"
  },
  "creative_still": {
    "name_zh": "创意静物",
    "name_en": "Creative Still Life",
    "priority": "P1",
    "parent_category": "artistic",
    "typical_percentage_range": [3, 8],
    "quality_threshold": ">88%"
  },
  "still_display": {
    "name_zh": "静物展示",
    "name_en": "Standard Still Display",
    "priority": "P1",
    "parent_category": "product_focused",
    "typical_percentage_range": [5, 15],
    "quality_threshold": ">93%"
  },
  "performance_test": {
    "name_zh": "性能测试",
    "name_en": "Performance Test",
    "priority": "P2",
    "parent_category": "technical",
    "typical_percentage_range": [1, 3],
    "quality_threshold": ">95%"
  },
  "other": {
    "name_zh": "其他",
    "name_en": "Other / Uncategorized",
    "priority": "P3",
    "parent_category": "uncategorized",
    "typical_percentage_range": [0, 20],
    "quality_threshold": "N/A (需人工审核)"
  }
}
```

### B. 历史版本变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-06-29 | 初始版本,定义8大标签 | AI Content Team |
| v2.0 | 2026-07-01 | 细化边界案例,增加判定优先级 | Labeling Lead |
| v2.1 | 2026-07-05 | 新增"性能测试"标签,从"其他"中分离 | Product Manager |
| v2.2 | 2026-07-08 | 修正"创意静物"的判定标准,降低误判率 | QA Team |
| v2.3 | 2026-07-11 | 完善"单品展示"子类型,增加质量保证章节 | AI Content Team |

### C. 反馈渠道

- **标签问题反馈**: [GitHub Issue](https://github.com/your-org/ecommerce-multimodal-material-processor/issues/new?labels=labeling-issue)
- **边界案例讨论**: [Slack频道](https://yourcompany.slack.com/channels/labeling-discussions)
- **紧急问题联系**: labeling-team@company.com

---

**维护者**: AI Content Realize Team - 标注标准工作组  
**最后审核**: 2026-07-11  
**下次计划审核**: 2026-07-25  
**适用版本**: v2.3+
