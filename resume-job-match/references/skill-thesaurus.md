# 技能同义词词库（skill-thesaurus）

> 供 `scripts/match.py` 做技能词归一与匹配。左侧为「规范名」，右侧为同义/别名/版本变体，命中任一即归一为规范名。
> 本词库聚焦 IT/互联网/数据方向（赛题主场景），可按需扩展。扩展时保持「规范名小写、别名穷举常见写法」。

## 一、编程语言

| 规范名 | 同义/别名 |
|--------|----------|
| python | py、python3、python2、cpython |
| java | java8、java11、java17、jdk、j2ee |
| javascript | js、ecmascript、es6、node.js、nodejs、node |
| typescript | ts |
| go | golang |
| c | c语言 |
| c++ | cpp、c plus plus |
| c# | csharp、.net、dotnet |
| php | php7、php8 |
| sql | mysql、postgresql、postgres、oracle sql、t-sql |
| r | r语言 |
| scala | |
| rust | rs |
| kotlin | kt |
| swift | |
| shell | bash、sh、shell脚本、linux脚本 |

## 二、前端

| 规范名 | 同义/别名 |
|--------|----------|
| html | html5 |
| css | css3、样式 |
| vue | vue.js、vuejs、vue2、vue3 |
| react | react.js、reactjs |
| angular | angularjs、ng |
| jquery | jq |
| webpack | |
| 小程序 | 微信小程序、weapp、miniprogram |

## 三、后端框架/中间件

| 规范名 | 同义/别名 |
|--------|----------|
| spring | spring framework、springframework |
| spring boot | springboot |
| spring cloud | springcloud |
| mybatis | mybatis-plus |
| django | |
| flask | |
| fastapi | |
| express | express.js |
| redis | |
| kafka | |
| rabbitmq | |
| elasticsearch | es、elastic |
| nginx | |
| docker | 容器 |
| kubernetes | k8s |
| 微服务 | microservice、micro-service |

## 四、数据/算法

| 规范名 | 同义/别名 |
|--------|----------|
| mysql | |
| postgresql | pg、postgres |
| mongodb | mongo |
| hadoop | |
| spark | |
| flink | |
| hive | |
| 机器学习 | ml、machine learning |
| 深度学习 | dl、deep learning |
| 自然语言处理 | nlp、自然语言 |
| 计算机视觉 | cv、图像识别 |
| pytorch | |
| tensorflow | tf |
| pandas | |
| numpy | |
| 数据分析 | 数据挖掘、data analysis |

## 五、工程/运维/工具

| 规范名 | 同义/别名 |
|--------|----------|
| git | |
| linux | unix |
| ci/cd | 持续集成、持续交付、jenkins、gitlab ci |
| aws | |
| 阿里云 | aliyun、acs |
| 腾讯云 | |
| 华为云 | |

## 六、证书/资质（用于硬性证书匹配）

| 规范名 | 同义/别名 |
|--------|----------|
| cpa | 注册会计师 |
| pmp | 项目管理专业人士资格 |
| 软考 | 计算机技术与软件专业技术资格 |
| 六西格玛 | six sigma |
| cfa | 特许金融分析师 |

> **匹配规则**：简历/JD 文本小写化后，对词库每个规范名的所有别名做子串包含匹配；命中即记该规范名为已具备。别名匹配优先于规范名本身（别名更具体）。空别名的，仅匹配规范名。
